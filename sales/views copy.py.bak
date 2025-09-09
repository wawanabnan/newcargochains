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

from django.contrib.auth.decorators import login_required, permission_required
from .services import generate_freight_order_from_quotation


from geo.models import Location
from .models import (
    FreightQuotation, FreightCargo, FreightCharge,
    FreightOrder, FreightOrderLine,   # ← tambahkan ini
)

from .forms import (
    FreightHeaderForm, FreightCargoForm, FreightChargeForm,
    CargoFormSet, ChargeFormSet
)
from utils.pdf import render_pdf_from_html

# ==== Customer proxy / fallback ====
try:
    from partners.models import CustomerProxy as CustomerModel
except Exception:
    from partners.models import Partner as CustomerModel

from django.conf import settings
from django.templatetags.static import static
from django.contrib.staticfiles import finders
from pathlib import Path
import os

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


# sales/views.py (tambahkan di atas fungsi freight_bulk_action)
ALLOWED_STATUS = {"DRAFT", "SENT", "CONFIRMED", "CLOSED", "CANCELLED"}

def _bulk_change_status(queryset, target_status: str):
    target_status = (target_status or "").upper()
    if target_status not in ALLOWED_STATUS:
        raise ValueError("Status tidak valid.")
    updated = 0
    for q in queryset:
        # aturan transisi sederhana (boleh diubah sesuai bisnis):
        # - tak boleh ubah dari CLOSED/CANCELLED ke status lain
        if q.status in ("CLOSED", "CANCELLED"):
            continue
        # set status
        q.status = target_status
        q.save(update_fields=["status"])
        updated += 1
    return updated


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
# PDF: wkhtmltopdf (via pdfkit)
# =============================================================================

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

    from django.contrib.staticfiles import finders
    from pathlib import Path

    abs_logo = finders.find("adminlte/img/cargochains.png")
    logo_file_uri = Path(abs_logo).as_uri() if abs_logo else None

    print("DEBUG LOGO FILE:", abs_logo)
    print("DEBUG LOGO URI :", logo_file_uri)


    ctx = {
        "q": q,
        "cargo_rows": cargo_rows,
        "subtotal": subtotal,
        "vat": vat,
        "grand_total": grand_total,
        "request": request,
        "COMPANY_LOGO_STATIC":logo_file_uri
    }

    html = render_to_string("sales/freight/pdf.html", ctx, request=request)

    pdf_bytes = render_pdf_from_html(html)

    filename = (q.number or f"Quotation-{q.pk}").replace("/", "-") + ".pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{filename}"'
    return resp

import base64, mimetypes
def _build_logo_data_uri():
    """
    Cari file logo via staticfiles finders, lalu embed sebagai data URI.
    Paling robust untuk wkhtmltopdf (tidak butuh akses http/file).
    """
    rel = getattr(settings, "COMPANY_LOGO_STATIC", "adminlte/img/company_logo.png")
    abs_path = finders.find(rel)
    if not abs_path:
        return None  # biar template aman tetap jalan

    mime, _ = mimetypes.guess_type(abs_path)
    if not mime:
        mime = "image/png"  # default aman

    with open(abs_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"




@login_required
@permission_required("sales.add_freightorder", raise_exception=True)
def freight_generate_order(request, pk: int):
    q = get_object_or_404(FreightQuotation, pk=pk)
    try:
        order = generate_freight_order_from_quotation(q.id, created_by=request.user)
        messages.success(request, f"Sales Order {order.number} berhasil dibuat dari {q.number}.")
        # TODO: ganti ke nama url detail order kamu (nanti kamu bisa buat view detailnya)
        return redirect("sales:freight_list")
    except Exception as e:
        messages.error(request, f"Gagal generate Sales Order: {e}")
        return redirect("sales:freight_view", pk=q.pk)


#Sale order area
# sales/views.py


@login_required
def freight_order_list(request):
    qs = (FreightOrder.objects
          .select_related("customer", "quotation")
          .order_by("-date", "-id"))
    return render(request, "sales/freight_order/list.html", {"orders": qs})

@login_required
def freight_order_view(request, pk: int):
    order = get_object_or_404(
        FreightOrder.objects.select_related("customer", "quotation").prefetch_related("lines"),
        pk=pk
    )
    return render(request, "sales/freight_order/view.html", {"order": order})

