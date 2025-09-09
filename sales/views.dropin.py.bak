# sales/views.py
from django.template.loader import render_to_string
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils.dateparse import parse_date
from django.db.models import Prefetch, Q
from django.conf import settings

import datetime
import json

# App imports
from geo.models import Location
from .models import (
    FreightQuotation, FreightCargo, FreightCharge,
    # Optional: kalau ada modul order, aktifkan:
    # FreightOrder, FreightOrderLine,
)
from .forms import (
    FreightHeaderForm, FreightCargoForm, FreightChargeForm,
    CargoFormSet, ChargeFormSet
)

# ============================================================================
# Customer model fallback
# ============================================================================
try:
    from partners.models import CustomerProxy as CustomerModel
except Exception:
    try:
        from partners.models import Partner as CustomerModel
    except Exception:  # very last fallback
        CustomerModel = None

def get_customer_queryset():
    if CustomerModel is None:
        return None
    qs = CustomerModel.objects.all()
    if hasattr(CustomerModel, "is_customer"):
        try:
            qs = qs.filter(is_customer=True)
        except Exception:
            pass
    return qs.order_by("name", "id")

# ============================================================================
# Wizard helpers & service/transport mapping
# ============================================================================
WKEY = "freight_quote_wizard_v1"

def _wiz_get(request):
    return request.session.get(WKEY, {"step": "header", "header": {}, "lines": []})

def _wiz_set(request, data):
    request.session[WKEY] = data
    request.session.modified = True

def _wiz_clear(request):
    if WKEY in request.session:
        del request.session[WKEY]

def _normalize_opt(val: str) -> str:
    return (val or "").upper().replace("-", "_").replace(" ", "_")

def _origin_dest_types(transport_mode: str, service_option: str):
    """
    Tentukan tipe Location untuk origin & destination berdasarkan
    transport_mode + service_option.
    Return: (origin_type_set, destination_type_set)
    """
    mode = _normalize_opt(transport_mode)
    opt  = _normalize_opt(service_option)

    # LAND / TRUCK → CITY <-> CITY apapun option-nya
    if mode in ("LAND", "TRUCK", "ROAD", "TRUCKING"):
        return ({Location.CITY}, {Location.CITY})

    # Definisi 'port' per mode
    if mode == "AIR":
        port_types = {Location.AIRPORT}
    else:  # SEA default
        port_types = {Location.SEAPORT, Location.JETTY}
    city = {Location.CITY}

    # Mapping umum
    if opt in ("DOOR_TO_DOOR", "D2D"):
        return (city, city)
    if opt in ("DOOR_TO_PORT", "D2P", "DOOR_TO_AIRPORT"):
        return (city, port_types)
    if opt in ("PORT_TO_DOOR", "P2D", "AIRPORT_TO_DOOR"):
        return (port_types, city)
    if opt in ("PORT_TO_PORT", "P2P", "AIRPORT_TO_AIRPORT"):
        return (port_types, port_types)
    if opt in ("TRUCKING",):
        return (city, city)

    # Fallback by mode
    return (port_types, port_types) if mode in ("SEA", "AIR") else (city, city)

def _qs_for_types(type_set):
    return Location.objects.filter(type__in=list(type_set)).order_by("name")

# ============================================================================
# LIST
# ============================================================================
def freight_list(request):
    qs = (FreightQuotation.objects
          .select_related("customer")
          .order_by("-date", "-id"))

    # Filters
    number      = (request.GET.get("number") or "").strip()
    customer_id = (request.GET.get("customer_id") or "").strip()
    mode        = (request.GET.get("mode") or "").strip()      # SEA/AIR/LAND
    status      = (request.GET.get("status") or "").strip()
    service     = (request.GET.get("service") or "").strip()   # e.g. PORT_TO_PORT
    date_from   = parse_date(request.GET.get("date_from") or "")
    date_to     = parse_date(request.GET.get("date_to") or "")

    if number:
        qs = qs.filter(number__icontains=number)
    if customer_id.isdigit():
        qs = qs.filter(customer_id=int(customer_id))
    if mode:
        qs = qs.filter(transport_mode=mode.upper())
    if status:
        qs = qs.filter(status=status.upper())
    if service:
        qs = qs.filter(service_option=service.upper())
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    return render(request, "sales/freight/list.html", {
        "quotations": qs,
    })

# ============================================================================
# CREATE WIZARD
# ============================================================================
@require_http_methods(["GET", "POST"])
def freight_create_wizard(request):
    """
    Step-1: Header (FreightHeaderForm)
    Step-2: Cargo (CargoFormSet) dengan Back / Add / Cancel / Save
    Setelah Save: redirect ke halaman detail (one-page view).
    """
    wiz = _wiz_get(request)
    step = (request.GET.get("step") or wiz.get("step") or "header").lower()

    # GET pertama → reset wizard
    if request.method == "GET" and "step" not in request.GET:
        _wiz_clear(request)
        wiz = {"step": "header", "header": {}, "lines": []}
        _wiz_set(request, wiz)
        form = FreightHeaderForm()
        return render(request, "sales/freight/wizard.html", {"step": "header", "form_header": form})

    # ---------------------- STEP 1: HEADER ----------------------
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
            # Prefill bila ada di session
            initial = {}
            if wiz.get("header"):
                h = wiz["header"]
                initial = {
                    "date": datetime.date.fromisoformat(h["date"]),
                    "customer": h["customer_id"],
                    "currency": h.get("currency") or "IDR",
                    "payment_term": h.get("payment_term") or "",
                    "notes": h.get("notes") or "",
                    "transport_mode": h.get("transport_mode") or "SEA",
                    "service_option": h.get("service_option") or "PORT_TO_PORT",
                }
            form = FreightHeaderForm(initial=initial)
        return render(request, "sales/freight/wizard.html", {"step": "header", "form_header": form})

    # Tidak boleh ke lines tanpa header
    if step == "lines" and not wiz.get("header"):
        wiz["step"] = "header"
        _wiz_set(request, wiz)
        form = FreightHeaderForm()
        return render(request, "sales/freight/wizard.html", {"step": "header", "form_header": form})

    # ---------------------- STEP 2: LINES ----------------------
    if step == "lines":
        hdr = wiz["header"]
        mode = hdr.get("transport_mode")
        opt  = hdr.get("service_option")

        origin_types, dest_types = _origin_dest_types(mode, opt)
        origin_qs = _qs_for_types(origin_types)
        dest_qs   = _qs_for_types(dest_types)

        if request.method == "POST":
            cargo_fs = CargoFormSet(request.POST, prefix="cargo")
            # pasang queryset sesuai opsi
            for f in cargo_fs.forms:
                if "origin" in f.fields:      f.fields["origin"].queryset = origin_qs
                if "destination" in f.fields: f.fields["destination"].queryset = dest_qs

            action = (request.POST.get("action") or "").lower()

            # Back: simpan ke session lalu balik ke header
            if action == "back":
                if cargo_fs.is_valid():
                    tmp = []
                    for f in cargo_fs.forms:
                        cd = f.cleaned_data or {}
                        if any(cd.get(k) for k in ("description","qty","weight_kg","volume_cbm","price","amount","origin","destination")):
                            tmp.append({
                                "description": cd.get("description") or "",
                                "qty": cd.get("qty") or 1,
                                "weight_kg": cd.get("weight_kg"),
                                "volume_cbm": cd.get("volume_cbm"),
                                "price": cd.get("price"),
                                "amount": cd.get("amount"),
                                "origin": cd.get("origin").id if cd.get("origin") else None,
                                "destination": cd.get("destination").id if cd.get("destination") else None,
                            })
                    wiz["lines"] = tmp
                    wiz["step"] = "header"
                    _wiz_set(request, wiz)
                    return redirect(f"{request.path}?step=header")
                messages.error(request, "Periksa isian Cargo sebelum kembali.")
                return render(request, "sales/freight/wizard.html", {"step": "lines", "cargo_fs": cargo_fs})

            # Cancel: bersihkan → kembali ke list
            if action == "cancel":
                _wiz_clear(request)
                return redirect("sales:freight_list")

            # Save: validasi & simpan
            if action == "save":
                if cargo_fs.is_valid():
                    # Validasi tipe lokasi (server-side)
                    has_type_error = False
                    for f in cargo_fs:
                        cd = getattr(f, "cleaned_data", {}) or {}
                        if not cd:
                            continue
                        o = cd.get("origin")
                        d = cd.get("destination")
                        if o and o.type not in origin_types:
                            f.add_error("origin", "Origin harus sesuai Service Option (City/Port/Airport).")
                            has_type_error = True
                        if d and d.type not in dest_types:
                            f.add_error("destination", "Destination harus sesuai Service Option (City/Port/Airport).")
                            has_type_error = True
                    if has_type_error:
                        for f in cargo_fs.forms:
                            if "origin" in f.fields:      f.fields["origin"].queryset = origin_qs
                            if "destination" in f.fields: f.fields["destination"].queryset = dest_qs
                        return render(request, "sales/freight/wizard.html", {"step": "lines", "cargo_fs": cargo_fs})

                    # Simpan quotation
                    q = FreightQuotation.objects.create(
                        date=datetime.date.fromisoformat(hdr["date"]),
                        customer_id=hdr["customer_id"],
                        currency=hdr.get("currency") or "IDR",
                        payment_term=hdr.get("payment_term") or "",
                        transport_mode=hdr.get("transport_mode") or "SEA",
                        service_option=hdr.get("service_option") or "PORT_TO_PORT",
                        notes=hdr.get("notes") or "",
                        multi_destination=False,
                    )

                    # Simpan cargo lines
                    created = 0
                    for f in cargo_fs:
                        cd = f.cleaned_data or {}
                        if not any(cd.get(k) for k in ("description","qty","weight_kg","volume_cbm","price","amount","origin","destination")):
                            continue
                        qty = cd.get("qty") or 1
                        price = cd.get("price") or 0
                        amount = cd.get("amount") or (qty * price)
                        FreightCargo.objects.create(
                            quotation=q,
                            description=cd.get("description") or "",
                            qty=qty,
                            weight_kg=cd.get("weight_kg") or None,
                            volume_cbm=cd.get("volume_cbm") or None,
                            price=price,
                            amount=amount,
                            origin=cd.get("origin"),
                            destination=cd.get("destination"),
                        )
                        created += 1

                    if created < 1:
                        q.delete()
                        messages.error(request, "Minimal satu Cargo wajib diisi.")
                        return render(request, "sales/freight/wizard.html", {"step": "lines", "cargo_fs": cargo_fs})

                    _wiz_clear(request)
                    messages.success(request, f"Freight Quotation {q.number} berhasil dibuat.")
                    return redirect("sales:freight_view", pk=q.pk)

                # invalid → tampilkan lagi
                messages.error(request, "Periksa isian Cargo.")
                return render(request, "sales/freight/wizard.html", {"step": "lines", "cargo_fs": cargo_fs})

        # GET: render formset dengan initial dari session (jika ada)
        initial_lines = []
        for row in (wiz.get("lines") or []):
            initial_lines.append({
                "description": row.get("description", ""),
                "qty": row.get("qty", 1),
                "weight_kg": row.get("weight_kg"),
                "volume_cbm": row.get("volume_cbm"),
                "price": row.get("price"),
                "amount": row.get("amount"),
                "origin": row.get("origin"),
                "destination": row.get("destination"),
            })
        cargo_fs = CargoFormSet(prefix="cargo", initial=initial_lines or [{}])
        for f in cargo_fs.forms:
            if "origin" in f.fields:      f.fields["origin"].queryset = origin_qs
            if "destination" in f.fields: f.fields["destination"].queryset = dest_qs

        return render(request, "sales/freight/wizard.html", {"step": "lines", "cargo_fs": cargo_fs})

    # Fallback → header
    wiz["step"] = "header"
    _wiz_set(request, wiz)
    form = FreightHeaderForm()
    return render(request, "sales/freight/wizard.html", {"step": "header", "form_header": form})

# ============================================================================
# DETAIL
# ============================================================================
def _compute_totals(quotation: FreightQuotation):
    # subtotal per cargo line + charges
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

    # VAT + TOTAL (kalau model punya field vat/total)
    vat_rate = float(getattr(quotation, "vat", 0) or 0)
    vat_amount = subtotal * (vat_rate / 100.0)
    grand_total = subtotal + vat_amount
    return {
        "rows": cargo_rows,
        "subtotal": subtotal,
        "vat": vat_amount,
        "grand_total": grand_total,
    }

def freight_view(request, pk: int):
    q = get_object_or_404(
        FreightQuotation.objects.select_related("customer"),
        pk=pk
    )
    totals = _compute_totals(q)
    return render(request, "sales/freight/view.html", {
        "q": q,
        "cargo_rows": totals["rows"],
        "subtotal": totals["subtotal"],
        "vat": totals["vat"],
        "grand_total": totals["grand_total"],
    })

@require_http_methods(["GET", "POST"])
def freight_manage_charges(request, pk: int):
    # Stub sementara—nanti bisa kita ganti dengan form ChargeFormSet
    messages.info(request, "Manage Charges belum diaktifkan. Dialihkan ke halaman detail quotation.")
    return redirect("sales:freight_view", pk=pk)

# Alias untuk kompatibilitas jika ada nama lama
freight_charges = freight_manage_charges



from django.http import JsonResponse

@require_http_methods(["GET"])
def freight_service_options(request):
    """
    Return JSON daftar service option berdasarkan transport mode.
    Value tetap konsisten: DOOR_TO_DOOR, DOOR_TO_PORT, PORT_TO_DOOR, PORT_TO_PORT
    (agar cocok dengan form/validasi yang sudah ada).
    """
    mode = (request.GET.get("mode") or "").upper()

    if mode in ("LAND", "TRUCK", "ROAD", "TRUCKING"):
        # Trucking: city ↔ city ⇒ cukup Door to Door
        opts = [
            {"value": "DOOR_TO_DOOR", "label": "Door to Door"},
        ]
    elif mode == "AIR":
        # Air: label disesuaikan, value tetap sama biar konsisten di backend
        opts = [
            {"value": "PORT_TO_PORT", "label": "Airport to Airport"},
            {"value": "DOOR_TO_PORT", "label": "Door to Airport"},
            {"value": "PORT_TO_DOOR", "label": "Airport to Door"},
            {"value": "DOOR_TO_DOOR", "label": "Door to Door"},
        ]
    else:
        # Default SEA
        opts = [
            {"value": "PORT_TO_PORT", "label": "Port to Port"},
            {"value": "DOOR_TO_PORT", "label": "Door to Port"},
            {"value": "PORT_TO_DOOR", "label": "Port to Door"},
            {"value": "DOOR_TO_DOOR", "label": "Door to Door"},
        ]

    return JsonResponse({"options": opts})
