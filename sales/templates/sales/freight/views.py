# sales/views.py
from __future__ import annotations
import datetime, re
from datetime import timedelta

from django.apps import apps
from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import render, redirect
from django.urls import reverse

from .forms import FreightHeaderForm, CargoFormSet
from .models import (
    FreightQuotation, FreightCargo,
    TransportMode, ModeService, LocationRule, Setting
)

WZ_SESSION_KEY = "fq_wizard"

# -------- settings helpers --------
def _get_setting(key: str, default=None):
    row = Setting.objects.filter(key=key).only("value").first()
    return row.value if row and row.value not in (None, "") else default

def _get_int_setting(key: str, default: int) -> int:
    try:
        return int(_get_setting(key, default))
    except Exception:
        return default

# -------- mode/service helpers --------
def _to_mode_code(value) -> str:
    if value is None:
        return ""
    code = getattr(value, "code", None)
    if code:
        return str(code).strip()
    s = str(value).strip()
    if s.isdigit():
        try:
            return TransportMode.objects.only("code").get(pk=int(s)).code
        except TransportMode.DoesNotExist:
            return ""
    return s

def _service_choices_for_mode(mode_code: str):
    mode = (mode_code or "").strip().upper()
    rows = list(
        ModeService.objects
        .filter(mode__code__iexact=mode)
        .select_related("service")
        .order_by("service__name")
        .values_list("service__code", "service__name")
    )
    # Fallback aman untuk moda darat
    if not rows and mode in {"INLAND", "LAND", "TRUCK", "TRUCKING"}:
        rows = [("TRUCKING", "Trucking")]
    return rows

def _default_mode_code():
    if TransportMode.objects.filter(code__iexact="SEA").exists():
        return "SEA"
    first = TransportMode.objects.order_by("name").first()
    return first.code if first else ""

def _get_location_qs_by_type(type_code: str):
    Location = apps.get_model("geo", "Location")
    if hasattr(Location, "loc_type"):
        return Location.objects.filter(loc_type=type_code).order_by("name")
    return Location.objects.filter(type=type_code).order_by("name")

# -------- numbering (format dari Setting) --------
_SEQ_RE = re.compile(r"%(\d+)d")
def _render_head_and_padding(fmt: str, today: datetime.date) -> tuple[str, int]:
    head = fmt.replace("%Y", f"{today:%Y}").replace("%y", f"{today:%y}").replace("%m", f"{today:%m}")
    m = _SEQ_RE.search(head)
    pad = 4
    if m:
        pad = int(m.group(1)); head = head[:m.start()] + head[m.end():]
    head = re.sub(r"-{2,}", "-", head).strip("-")
    if not head.endswith("-"): head += "-"
    return head, pad

def generate_freight_number() -> str:
    fmt = _get_setting("QUO_FORMAT_FREIGHT", "FRQ-%Y%m-%4d")
    head, pad = _render_head_and_padding(fmt, datetime.date.today())
    with transaction.atomic():
        last = (FreightQuotation.objects
                .select_for_update()
                .filter(number__startswith=head)
                .aggregate(mx=Max("number"))
                .get("mx"))
        seq = 1
        if last and last.startswith(head):
            try: seq = int(last[len(head):]) + 1
            except Exception: seq = 1
        return f"{head}{seq:0{pad}d}"

# -------- AJAX: service options (terima mode pk *atau* code) --------
def freight_service_options(request: HttpRequest) -> JsonResponse:
    raw = (request.GET.get("mode") or "").strip()
    mode_code = _to_mode_code(raw)
    data = [{"id": c, "text": n} for c, n in _service_choices_for_mode(mode_code)]
    return JsonResponse({"results": data})

# -------- reset & debug --------
def freight_wizard_reset(request: HttpRequest) -> HttpResponse:
    request.session.pop(WZ_SESSION_KEY, None); request.session.modified = True
    return redirect("sales:freight_new")

def freight_wizard_debug(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"wizard": request.session.get(WZ_SESSION_KEY)}, json_dumps_params={"indent": 2})

# -------- WIZARD --------
def freight_create_wizard(request: HttpRequest) -> HttpResponse:
    state = request.session.get(WZ_SESSION_KEY)
    step = request.GET.get("step") or ("lines" if state else "header")

    # ======= HEADER =======
    if step == "header":
        if request.method == "POST":
            form = FreightHeaderForm(request.POST)
            if form.is_valid():
                cd = form.cleaned_data
                mode_code = _to_mode_code(cd["transport_mode"])
                svc_code = (cd["service_option"] or "").strip()

                # validasi service-option
                if not ModeService.objects.filter(mode__code__iexact=mode_code, service__code=svc_code).exists():
                    choices = _service_choices_for_mode(mode_code)
                    if not choices:
                        messages.error(request, "Service Option untuk mode ini belum tersedia.")
                        return render(request, "sales/wizard_header.html", {
                            "form": form, "service_choices": [], "current_service": ""
                        })
                    preferred = {"TRUCKING", "P2P"}
                    svc_code = next((c for c, _ in choices if c in preferred), choices[0][0])

                # location rule
                try:
                    lr = LocationRule.objects.get(mode__code__iexact=mode_code, service__code=svc_code)
                except LocationRule.DoesNotExist:
                    messages.error(request, "Location rule Mode+Service belum tersedia.")
                    svc_choices = _service_choices_for_mode(mode_code)
                    return render(request, "sales/wizard_header.html", {
                        "form": form, "service_choices": svc_choices, "current_service": svc_code
                    })

                # simpan session
                request.session[WZ_SESSION_KEY] = {
                    "valid_until": str(cd["valid_until"]),
                    "customer_id": cd["customer"].pk,
                    "currency": cd["currency"],           # konstanta (choices)
                    "payment_term": cd["payment_term"],   # konstanta (choices)
                    "transport_mode": mode_code,
                    "service_option": svc_code,
                    "origin_type": lr.origin_type,
                    "destination_type": lr.destination_type,
                    "notes": cd.get("notes", ""),
                }
                request.session.modified = True
                return redirect(reverse("sales:freight_new") + "?step=lines")

            # invalid → render ulang dgn service sesuai mode yang dipost
            posted_mode_code = _to_mode_code(request.POST.get("transport_mode")) or _default_mode_code()
            svc_choices = _service_choices_for_mode(posted_mode_code)
            
            preferred = {"TRUCKING", "P2P"}
            current_svc = request.POST.get("service_option") or next(
                (c for c, _ in svc_choices if c in preferred),
                (svc_choices[0][0] if svc_choices else "")
            )            
            
            return render(request, "sales/wizard_header.html", {
                "form": form, "service_choices": svc_choices, "current_service": current_svc
            })

        # GET: initial dari Setting (konstanta)
        days = _get_int_setting("QUO_VALID_DAYS", 7)
        initial = {"valid_until": datetime.date.today() + timedelta(days=days)}
        initial["currency"] = _get_setting("DEFAULT_CURRENCY", "IDR") or "IDR"
        initial["payment_term"] = _get_setting("DEFAULT_PAYMENT_TERM", "CASH") or "CASH"

        mode_code = _default_mode_code()  # "SEA" jika ada
        initial["transport_mode"] = mode_code
        svc_choices = _service_choices_for_mode(mode_code)

        preferred = {"TRUCKING", "P2P"}
        current_svc = next((c for c, _ in svc_choices if c in preferred),
                       (svc_choices[0][0] if svc_choices else ""))
        initial["service_option"] = current_svc

        form = FreightHeaderForm(initial=initial)
        return render(request, "sales/wizard_header.html", {
            "form": form, "service_choices": svc_choices, "current_service": current_svc
        })

    # ======= LINES =======
    if not state:
        return redirect(reverse("sales:freight_new") + "?step=header")

    origin_qs = _get_location_qs_by_type(state.get("origin_type") or "CITY")
    dest_qs   = _get_location_qs_by_type(state.get("destination_type") or "CITY")

    if request.method == "POST":
        if "cargo-TOTAL_FORMS" not in request.POST:
            messages.error(request, "Form tidak lengkap: TOTAL_FORMS/INITIAL_FORMS tidak terkirim.")
            formset = CargoFormSet(prefix="cargo", form_kwargs={"origin_qs": origin_qs, "dest_qs": dest_qs})
            return render(request, "sales/wizard_lines.html", {"formset": formset})

        formset = CargoFormSet(request.POST, prefix="cargo", form_kwargs={"origin_qs": origin_qs, "dest_qs": dest_qs})
        if formset.is_valid():
            with transaction.atomic():
             fq_payload = {
                "number": generate_freight_number(),
                "date": timezone.now().date(),   # <<< penting: isi field 'date' non-null
                "valid_until": state["valid_until"],
                "customer_id": state["customer_id"],
                "currency": state["currency"],
                "payment_term": state["payment_term"],
                "transport_mode": state["transport_mode"],
                "service_option": state["service_option"],
                "notes": state.get("notes", ""),
                "status": "DRAFT",
            }
            fq = FreightQuotation.objects.create(**fq_payload)

            items = []
            for row in formset.cleaned_data:
                    if not row or row.get("DELETE"): continue
                    items.append(FreightCargo(
                        quotation=fq,
                        origin=row["origin"], destination=row["destination"],
                        description=row.get("description",""),
                        qty=row.get("qty") or 1,
                        weight_kg=row.get("weight_kg") or 0,
                        volume_cbm=row.get("volume_cbm") or 0,
                        price=row.get("price") or 0,
                        amount=row.get("amount") or 0,
                    ))
            if items:
                    FreightCargo.objects.bulk_create(items)

            request.session.pop(WZ_SESSION_KEY, None); request.session.modified = True
            try:
                return redirect("sales:freight_view", pk=fq.pk)
            except Exception:
                messages.success(request, f"Quotation #{fq.number} berhasil dibuat.")
                return redirect("sales:freight_list")
        else:
            messages.error(request, "Periksa isian cargo.")
    else:
        formset = CargoFormSet(prefix="cargo", form_kwargs={"origin_qs": origin_qs, "dest_qs": dest_qs})

    return render(request, "sales/wizard_lines.html", {"formset": formset})

def freight_list(request):
    qs = (FreightQuotation.objects
          .select_related("customer")
          .order_by("-date", "-id"))

    # ---- filters (GET) ----
    number      = (request.GET.get("number") or "").strip()
    customer_id = (request.GET.get("customer_id") or "").strip()
    mode        = (request.GET.get("mode") or "").strip()      # "SEA"/"AIR"/"LAND"
    status      = (request.GET.get("status") or "").strip()
    service     = (request.GET.get("service") or "").strip()   # "PORT_TO_PORT", dst
    date_from   = parse_date(request.GET.get("date_from") or "")
    date_to     = parse_date(request.GET.get("date_to") or "")

    if number:
        qs = qs.filter(number__icontains=number)
    if customer_id.isdigit():
        qs = qs.filter(customer_id=int(customer_id))
    if mode:
        qs = qs.filter(transport_mode=mode)
    if status:
        qs = qs.filter(status=status)
    if service:
        qs = qs.filter(service_option=service)
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    from django.db.models import Sum, Value, DecimalField
    from django.db.models.functions import Coalesce
    qs = (FreightQuotation.objects
        .select_related("customer")
        .annotate(
            cargo_total=Coalesce(
                Sum("cargos__amount"),
                Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))
            )
        )
        .order_by("-date", "-id"))


    # === dropdown data ===
    customer_options = []
    for c in get_customer_queryset():
        label = (getattr(c, "name", None)
                 or getattr(c, "company_name", None)
                 or getattr(c, "code", None)
                 or f"Customer #{c.id}")
        customer_options.append((c.id, label))

    mode_choices = FreightQuotation._meta.get_field("transport_mode").choices or []

    model_service_choices = FreightQuotation._meta.get_field("service_option").choices or []
    if mode:
        service_choices = SERVICE_BY_MODE.get(mode, model_service_choices)
    else:
        seen = set()
        merged = []
        for k in ("SEA", "AIR", "LAND"):
            for code, label in SERVICE_BY_MODE.get(k, []):
                if code not in seen:
                    merged.append((code, label))
                    seen.add(code)
        service_choices = merged or model_service_choices

    ctx = {
        "quotations": qs,
        "filters": {
            "number": number,
            "customer_id": customer_id,
            "mode": mode,
            "status": status,
            "service": service,
            "date_from": request.GET.get("date_from", ""),
            "date_to": request.GET.get("date_to", ""),
        },
        "status_choices": FreightQuotation.STATUS_CHOICES,
        "customer_options": customer_options,
        "mode_choices": mode_choices,
        "service_choices": service_choices,
        "service_by_mode_json": json.dumps(SERVICE_BY_MODE),
    }
    return render(request, "sales/freight/list.html", ctx)

