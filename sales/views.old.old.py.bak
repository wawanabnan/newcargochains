# sales/views.py

from django.template.loader import render_to_string
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.forms import modelformset_factory
from django.utils.dateparse import parse_date
from django.db.models import Q, Prefetch
import datetime
import json

from playwright.sync_api import sync_playwright

from geo.models import Location
from .models import FreightQuotation, FreightCargo, FreightCharge
from .forms import (
    FreightHeaderForm, FreightCargoForm, FreightChargeForm,
    CargoFormSet, ChargeFormSet
)

# ==== Customer proxy / fallback ====
try:
    from partners.models import CustomerProxy as CustomerModel
except Exception:
    from partners.models import Partner as CustomerModel

import os
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

# ==== Mapping service berdasarkan mode transport ====
SERVICE_BY_MODE = {
    "SEA": [
        ("DOOR_TO_DOOR", "Door to door"),
        ("DOOR_TO_PORT", "Door to port"),
        ("PORT_TO_PORT", "Port to port"),
    ],
    "AIR": [
        ("DOOR_TO_AIRPORT", "Door to airport"),
        ("AIRPORT_TO_AIRPORT", "Airport to airport"),
    ],
    "LAND": [
        ("TRUCKING", "Trucking"),
    ],
}


def get_customer_queryset():
    qs = CustomerModel.objects.all()
    if hasattr(CustomerModel, "is_customer"):
        try:
            qs = qs.filter(is_customer=True)
        except Exception:
            pass
    return qs.order_by("name", "id")


# =============================================================================
# LIST & FILTER
# =============================================================================

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


def freight_service_options(request):
    mode = (request.GET.get("mode") or "").upper()
    options = [{"value": v, "label": l} for v, l in SERVICE_BY_MODE.get(mode, [])]
    return JsonResponse({"mode": mode, "options": options})


# =============================================================================
# WIZARD CREATE (Header -> Lines)
# =============================================================================

WKEY = "freight_wizard"

def _wiz_get(request):
    return request.session.get(WKEY, {"step": "header", "header": {}})

def _wiz_set(request, data):
    request.session[WKEY] = data
    request.session.modified = True

def _wiz_clear(request):
    if WKEY in request.session:
        del request.session[WKEY]


@require_http_methods(["GET", "POST"])
def freight_create_wizard(request):
    wiz = _wiz_get(request)
    step = (request.GET.get("step") or wiz.get("step") or "header").lower()

    # Reset state saat GET pertama tanpa parameter step
    if request.method == "GET" and "step" not in request.GET:
        _wiz_clear(request)
        wiz = {"step": "header", "header": {}}
        _wiz_set(request, wiz)
        form = FreightHeaderForm()
        return render(request, "sales/freight/wizard.html", {"step": "header", "form_header": form})

    # STEP: HEADER
    if step == "header":
        if request.method == "POST":
            form = FreightHeaderForm(request.POST)
            if form.is_valid():
                cd = form.cleaned_data
                wiz["header"] = {
                    "date": cd["date"].isoformat(),
                    "customer_id": cd["customer"].pk,
                    "currency": cd["currency"],
                    "payment_term": cd.get("payment_term") or "",
                    "notes": cd.get("notes") or "",
                    "transport_mode": cd["transport_mode"],
                    "service_option": cd["service_option"],
                }
                wiz["step"] = "lines"
                _wiz_set(request, wiz)
                return redirect(f"{request.path}?step=lines")
            messages.error(request, "Periksa Header Information.")
        else:
            form = FreightHeaderForm()
        return render(request, "sales/freight/wizard.html", {"step": "header", "form_header": form})

    # Guard: tidak boleh ke lines tanpa header
    if step == "lines" and not wiz.get("header"):
        wiz["step"] = "header"
        _wiz_set(request, wiz)
        form = FreightHeaderForm()
        return render(request, "sales/freight/wizard.html", {"step": "header", "form_header": form})

    # STEP: LINES
    if step == "lines":
        hdr = wiz["header"]
        CargoFS = CargoFormSet

        if request.method == "POST":
            cargo_fs = CargoFS(request.POST, prefix="cargo")

            # Filter dropdown lokasi sesuai mode
            mode = (hdr.get("transport_mode") or "SEA").upper()
            if mode == "SEA":
                loc_types = [Location.SEAPORT, Location.JETTY]
            elif mode == "AIR":
                loc_types = [Location.AIRPORT]
            else:
                loc_types = [Location.CITY, Location.JETTY]
            loc_qs = Location.objects.filter(type__in=loc_types).order_by("name")
            for f in cargo_fs.forms:
                if "origin" in f.fields:
                    f.fields["origin"].queryset = loc_qs
                if "destination" in f.fields:
                    f.fields["destination"].queryset = loc_qs

            if cargo_fs.is_valid():
                # create quotation header
                q = FreightQuotation.objects.create(
                    date=datetime.date.fromisoformat(hdr["date"]),
                    customer_id=hdr["customer_id"],
                    currency=hdr.get("currency") or "IDR",
                    payment_term=hdr.get("payment_term") or "",
                    transport_mode=hdr["transport_mode"],
                    service_option=hdr["service_option"],
                    notes=hdr.get("notes") or "",
                    multi_destination=False,
                )

                cargos_created = 0
                for f in cargo_fs:
                    cd = f.cleaned_data or {}
                    # skip blank rows
                    if not any(cd.get(k) for k in (
                        "description", "qty", "weight_kg", "volume_cbm", "price", "amount", "origin", "destination"
                    )):
                        continue
                    qty = cd.get("qty") or 1
                    price = cd.get("price") or 0
                    amount = cd.get("amount") or (qty * price)
                    FreightCargo.objects.create(
                        quotation=q,
                        description=cd.get("description") or "",
                        qty=qty,
                        weight_kg=cd.get("weight_kg") or 0,
                        volume_cbm=cd.get("volume_cbm") or 0,
                        price=price,
                        amount=amount,
                        origin=cd.get("origin"),
                        destination=cd.get("destination"),
                    )
                    cargos_created += 1

                if cargos_created < 1:
                    q.delete()
                    messages.error(request, "Minimal satu Cargo wajib diisi.")
                    return render(request, "sales/freight/wizard.html", {
                        "step": "lines", "cargo_fs": cargo_fs
                    })

                _wiz_clear(request)

                # redirect sesuai tombol
                if "manage_charges" in request.POST:
                    return redirect("sales:freight_charges", pk=q.pk)
                messages.success(request, f"Freight Quotation {q.number} berhasil dibuat.")
                return redirect("sales:freight_list")

            # invalid cargo formset
            messages.error(request, "Periksa isian Cargo.")
            return render(request, "sales/freight/wizard.html", {
                "step": "lines", "cargo_fs": cargo_fs
            })

        # GET: tampilkan formset kosong
        cargo_fs = CargoFormSet(prefix="cargo")

        mode = (hdr.get("transport_mode") or "SEA").upper()
        if mode == "SEA":
            loc_types = [Location.SEAPORT, Location.JETTY]
        elif mode == "AIR":
            loc_types = [Location.AIRPORT]
        else:
            loc_types = [Location.CITY, Location.JETTY]
        loc_qs = Location.objects.filter(type__in=loc_types).order_by("name")
        for f in cargo_fs.forms:
            if "origin" in f.fields:
                f.fields["origin"].queryset = loc_qs
            if "destination" in f.fields:
                f.fields["destination"].queryset = loc_qs

        return render(request, "sales/freight/wizard.html", {
            "step": "lines", "cargo_fs": cargo_fs
        })

    # fallback aman
    wiz["step"] = "header"
    _wiz_set(request, wiz)
    form = FreightHeaderForm()
    return render(request, "sales/freight/wizard.html", {"step": "header", "form_header": form})


# =============================================================================
# EDIT / CHARGES / BULK
# =============================================================================

def freight_view(request, pk: int):
    q = get_object_or_404(
        FreightQuotation.objects.select_related("customer").prefetch_related(
            Prefetch("cargos", queryset=FreightCargo.objects.all())
        ),
        pk=pk
    )
    cargo_rows, subtotal, vat, grand_total = _compute_totals(q)

    ctx = {
        "q": q,
        "cargo_rows": cargo_rows,
        "subtotal": subtotal,
        "vat": vat,
        "grand_total": grand_total,
    }
    return render(request, "sales/freight/view.html", ctx)


def freight_edit(request, pk):
    q = get_object_or_404(FreightQuotation, pk=pk)
    if request.method == "POST":
        form = FreightHeaderForm(request.POST, instance=q)
        if form.is_valid():
            cd = form.cleaned_data
            q.date = cd["date"]
            q.customer = cd["customer"]
            q.currency = cd.get("currency") or q.currency
            q.payment_term = cd.get("payment_term") or ""
            q.transport_mode = cd["transport_mode"]
            q.service_option = cd["service_option"]
            q.notes = cd.get("notes") or ""
            q.save()
            messages.success(request, "Quotation updated.")
            return redirect("sales:freight_view", pk=q.pk)
    else:
        form = FreightHeaderForm(instance=q)

    return render(request, "sales/freight/edit.html", {"form": form, "q": q})


def freight_manage_charges(request, pk):
    q = get_object_or_404(FreightQuotation, pk=pk)
    cargos = q.cargos.all().order_by("id")
    if not cargos.exists():
        return redirect("sales:freight_view", pk=q.pk)

    # pilih cargo aktif via ?cargo=
    cid = request.GET.get("cargo")
    try:
        cargo_id = int(cid) if cid else cargos.first().id
    except (TypeError, ValueError):
        cargo_id = cargos.first().id

    current = get_object_or_404(FreightCargo, pk=cargo_id, quotation=q)

    ChargeFS = modelformset_factory(
        FreightCharge, form=FreightChargeForm, extra=2, can_delete=True
    )
    queryset = FreightCharge.objects.filter(cargo=current).order_by("id")

    if request.method == "POST":
        formset = ChargeFS(request.POST, queryset=queryset, prefix="chg")
        if formset.is_valid():
            objs = formset.save(commit=False)
            for obj in objs:
                obj.cargo = current
                if obj.qty and obj.rate and not obj.amount:
                    try:
                        obj.amount = obj.qty * obj.rate
                    except Exception:
                        pass
                obj.save()
            for obj in formset.deleted_objects:
                obj.delete()
            return redirect(f"{request.path}?cargo={current.id}")
    else:
        formset = ChargeFS(queryset=queryset, prefix="chg")

    return render(request, "sales/freight/charges.html", {
        "q": q,
        "cargos": cargos,
        "current": current,
        "formset": formset,
    })


@require_POST
def freight_bulk_action(request):
    action = request.POST.get("action")
    ids = request.POST.get("ids", "").strip()
    id_list = [int(x) for x in ids.split(",") if x.isdigit()]

    if not id_list:
        messages.warning(request, "Tidak ada quotation yang dipilih.")
        return redirect("sales:freight_list")

    qs = FreightQuotation.objects.filter(id__in=id_list)

    if action == "email":
        messages.success(request, f"Send Email: {qs.count()} quotation (dummy).")
        return redirect("sales:freight_list")

    if action == "manage_charges":
        first_id = id_list[0]
        return redirect("sales:freight_charges", pk=first_id)

    if action == "delete":
        count = qs.count()
        # hati-hati: hapus child dulu
        FreightCharge.objects.filter(cargo__quotation_id__in=id_list).delete()
        FreightCargo.objects.filter(quotation_id__in=id_list).delete()
        qs.delete()
        messages.success(request, f"Deleted {count} quotation(s).")
        return redirect("sales:freight_list")

    messages.error(request, "Aksi tidak dikenal.")
    return redirect("sales:freight_list")


def _compute_totals(quotation: FreightQuotation):
    # hitung subtotal dari cargo.amount + charges(amount)
    cargos = (FreightCargo.objects
              .filter(quotation=quotation)
              .prefetch_related(Prefetch("charges", queryset=FreightCharge.objects.all())))
    subtotal = 0
    cargo_rows = []
    for c in cargos:
        charge_total = sum(ch.amount or 0 for ch in c.charges.all())
        line_total = (c.amount or 0) + charge_total
        subtotal += line_total
        cargo_rows.append({
            "obj": c,
            "charge_total": charge_total,
            "line_total": line_total,
            "charges": list(c.charges.all()),
        })

    vat = quotation.vat or 0
    total = subtotal + vat
    return cargo_rows, subtotal, vat, total


def freight_send_email(request, pk: int):
    # dummy email action
    q = get_object_or_404(FreightQuotation, pk=pk)
    if q.status == "DRAFT":
        q.status = "SENT"
        q.save(update_fields=["status"])
    messages.success(request, f"Quotation {q.number} telah dikirim (dummy).")
    return redirect("sales:freight_view", pk=pk)


# =============================================================================
# PDF: Playwright SYNC pooling (cepat)
# =============================================================================

_PW = None
_BROWSER = None
_CONTEXT = None

def _ensure_sync_browser():
    """
    Start Playwright/Chromium sekali saja per process, reuse untuk semua request.
    """
    global _PW, _BROWSER, _CONTEXT
    if _BROWSER and _CONTEXT:
        return _BROWSER, _CONTEXT
    _PW = sync_playwright().start()
    _BROWSER = _PW.chromium.launch()   # headless default
    _CONTEXT = _BROWSER.new_context(
        java_script_enabled=False,     # cepat & deterministik (template statis)
        device_scale_factor=1.0,
    )
    return _BROWSER, _CONTEXT


def html_to_pdf_bytes(html: str, base_url: str) -> bytes:
    """
    Render HTML -> PDF dengan context yang di-reuse (super cepat).
    """
    # Sisipkan <base> agar asset relatif (static/img/css) resolve.
    if "<head>" in html:
        html = html.replace("<head>", f'<head><base href="{base_url}">', 1)
    else:
        html = f'<head><base href="{base_url}"></head>{html}'

    browser, context = _ensure_sync_browser()
    page = context.new_page()

    # Hanya izinkan host sendiri & /static/, block eksternal
    def _route(route, request):
        url = request.url
        if url.startswith(base_url) or "/static/" in url:
            route.continue_()
        else:
            route.abort()
    page.route("**/*", _route)

    # 'domcontentloaded' cukup untuk HTML statis kita (lebih cepat dari 'load')
    page.set_content(html, wait_until="domcontentloaded")
    page.emulate_media(media="print")

    pdf_bytes = page.pdf(
        format="A4",
        print_background=True,
        prefer_css_page_size=True,
        margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"},
    )

    page.unroute("**/*", _route)
    page.close()
    return pdf_bytes


def freight_pdf(request, pk: int):
    # ambil data + eager loading
    q = get_object_or_404(
        FreightQuotation.objects.select_related("customer").prefetch_related(
            Prefetch("cargos", queryset=FreightCargo.objects.prefetch_related("charges"))
        ),
        pk=pk
    )
    # hitung totals + rows yang dipakai template
    cargo_rows, subtotal, vat, grand_total = _compute_totals(q)

    ctx = {
        "q": q,
        "cargo_rows": cargo_rows,
        "subtotal": subtotal,
        "vat": vat,
        "grand_total": grand_total,
        "request": request,
    }
    html = render_to_string("sales/freight/pdf.html", ctx, request=request)
    base_url = request.build_absolute_uri("/")
    pdf_bytes = html_to_pdf_bytes(html, base_url)

    filename = (q.number or f"Quotation-{q.pk}").replace("/", "-") + ".pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp
