# apply_notes_patch_v2.py
# Jalankan dari root project:  python apply_notes_patch_v2.py
# Menulis/menimpa:
# - sales/helpers_freight_overlay.py
# - sales/wizard_v2.py
# (Tidak menyentuh sales/views.py lama)

import os, io
from pathlib import Path

BASE = Path.cwd()

def write(path, content):
    p = BASE / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print("Wrote:", path)

HELPERS = """# sales/helpers_freight_overlay.py
from geo.models import Location

def normalize_opt(val):
    return (val or "").upper().replace("-", "_").replace(" ", "_")

def origin_dest_types(transport_mode, service_option):
    '''
    Return (origin_types, dest_types) berupa SET tipe Location yang dibolehkan.
    - TRUCK/LAND/ROAD/TRUCKING -> CITY <-> CITY
    - SEA: 'port' = SEAPORT (tanpa JETTY)
    - AIR: 'port' = AIRPORT
    - DOOR<->DOOR = CITY<->CITY
    - DOOR->PORT = CITY->PORT
    - PORT->DOOR = PORT->CITY
    - PORT<->PORT = PORT<->PORT
    '''
    mode = normalize_opt(transport_mode)
    opt  = normalize_opt(service_option)

    if mode in ("LAND", "TRUCK", "ROAD", "TRUCKING"):
        return ({Location.CITY}, {Location.CITY})

    # NOTE: SEA port = SEAPORT saja (tanpa JETTY), AIR port = AIRPORT
    port_types = {Location.AIRPORT} if mode == "AIR" else {Location.SEAPORT}
    city = {Location.CITY}

    if opt in ("DOOR_TO_DOOR", "D2D"):
        return (city, city)
    if opt in ("DOOR_TO_PORT", "D2P", "DOOR_TO_AIRPORT"):
        return (city, port_types)
    if opt in ("PORT_TO_DOOR", "P2D", "AIRPORT_TO_DOOR"):
        return (port_types, city)
    if opt in ("PORT_TO_PORT", "P2P", "AIRPORT_TO_AIRPORT"):
        return (port_types, port_types)

    # fallback
    return (port_types, port_types) if mode in ("SEA", "AIR") else (city, city)

def qs_for_types(type_set):
    return Location.objects.filter(type__in=list(type_set)).order_by("name")

def service_options_for_mode(mode):
    m = (mode or '').upper()
    if m in ('LAND', 'TRUCK', 'ROAD', 'TRUCKING'):
        return [('DOOR_TO_DOOR', 'Door to Door')]
    elif m == 'AIR':
        return [
            ('PORT_TO_PORT', 'Airport to Airport'),
            ('DOOR_TO_PORT', 'Door to Airport'),
            ('PORT_TO_DOOR', 'Airport to Door'),
            ('DOOR_TO_DOOR', 'Door to Door'),
        ]
    else:  # SEA default
        return [
            ('PORT_TO_PORT', 'Port to Port'),
            ('DOOR_TO_PORT', 'Door to Port'),
            ('PORT_TO_DOOR', 'Port to Door'),
            ('DOOR_TO_DOOR', 'Door to Door'),
        ]
"""

WIZARD = """# sales/wizard_v2.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_date
import datetime

from geo.models import Location
from .models import FreightQuotation, FreightCargo
from .forms import FreightHeaderForm, CargoFormSet
from .helpers_freight_overlay import (
    origin_dest_types, qs_for_types, service_options_for_mode
)

WKEY = "freight_quote_wizard_v2"

def _wiz_get(request):
    return request.session.get(WKEY, {"step": "header", "header": {}, "lines": []})

def _wiz_set(request, data):
    request.session[WKEY] = data
    request.session.modified = True

def _wiz_clear(request):
    if WKEY in request.session:
        del request.session[WKEY]

def _cargo_post_has_any_input(post):
    pre = "cargo-0-"
    keys = ["origin", "destination", "description", "weight_kg", "volume_cbm", "price", "amount"]
    return any((post.get(pre + k) not in (None, "")) for k in keys)

@require_http_methods(["GET", "POST"])
def freight_create_wizard_v2(request):
    wiz = _wiz_get(request)
    step = (request.GET.get("step") or wiz.get("step") or "header").lower()

    # GET pertama (tanpa step) -> reset
    if request.method == "GET" and "step" not in request.GET:
        _wiz_clear(request)
        wiz = {"step": "header", "header": {}, "lines": []}
        _wiz_set(request, wiz)
        form = FreightHeaderForm(initial={"transport_mode": "SEA", "service_option": "PORT_TO_PORT"})
        tm = "SEA"
        form.fields["service_option"].choices = service_options_for_mode(tm)
        return render(request, "sales/freight/wizard_v2.html", {"step": "header", "form_header": form})

    # ---------------------- STEP 1: HEADER ----------------------
    if step == "header":
        if request.method == "POST":
            form = FreightHeaderForm(request.POST)
            tm = request.POST.get("transport_mode") or "SEA"
            form.fields["service_option"].choices = service_options_for_mode(tm)
            if form.is_valid():
                cd = form.cleaned_data
                wiz["header"] = {
                    "date": cd["date"].isoformat(),
                    "customer_id": cd["customer"].pk,
                    "currency": cd.get("currency") or "IDR",
                    "payment_term": cd.get("payment_term") or "",
                    "notes": cd.get("notes") or "",
                    "transport_mode": cd.get("transport_mode") or "SEA",
                    "service_option": cd.get("service_option") or "PORT_TO_PORT",
                }
                wiz["step"] = "lines"
                _wiz_set(request, wiz)
                return redirect("{}?step=lines".format(request.path))
            else:
                messages.error(request, "Periksa Header Information.")
        else:
            if wiz.get("header"):
                h = wiz["header"]
                initial = {
                    "date": parse_date(h.get("date") or "") or None,
                    "customer": h.get("customer_id"),
                    "currency": h.get("currency") or "IDR",
                    "payment_term": h.get("payment_term") or "",
                    "notes": h.get("notes") or "",
                    "transport_mode": h.get("transport_mode") or "SEA",
                    "service_option": h.get("service_option") or "PORT_TO_PORT",
                }
            else:
                initial = {"transport_mode": "SEA", "service_option": "PORT_TO_PORT"}
            form = FreightHeaderForm(initial=initial)
            tm = initial.get("transport_mode") or "SEA"
            form.fields["service_option"].choices = service_options_for_mode(tm)
        return render(request, "sales/freight/wizard_v2.html", {"step": "header", "form_header": form})

    # Tidak boleh ke lines tanpa header
    if step == "lines" and not wiz.get("header"):
        wiz["step"] = "header"
        _wiz_set(request, wiz)
        form = FreightHeaderForm(initial={"transport_mode": "SEA", "service_option": "PORT_TO_PORT"})
        form.fields["service_option"].choices = service_options_for_mode("SEA")
        return render(request, "sales/freight/wizard_v2.html", {"step": "header", "form_header": form})

    # ---------------------- STEP 2: LINES (single cargo form) ----------------------
    if step == "lines":
        hdr = wiz["header"]
        mode = hdr.get("transport_mode")
        opt  = hdr.get("service_option")

        # filter lokasi sesuai header (Port-to-Port SEA -> SEAPORT only; Air -> AIRPORT; Door-to-Door -> CITY)
        origin_types, dest_types = origin_dest_types(mode, opt)
        origin_qs = qs_for_types(origin_types)
        dest_qs   = qs_for_types(dest_types)

        added_lines = list(wiz.get("lines") or [])

        if request.method == "POST":
            cargo_fs = CargoFormSet(request.POST, prefix="cargo")
            for f in cargo_fs.forms:
                if "origin" in f.fields:
                    f.fields["origin"].queryset = origin_qs
                    # tampilkan nama saja
                    f.fields["origin"].label_from_instance = (lambda o: o.name)
                if "destination" in f.fields:
                    f.fields["destination"].queryset = dest_qs
                    # tampilkan nama saja
                    f.fields["destination"].label_from_instance = (lambda o: o.name)

            action = (request.POST.get("action") or "finish").lower()

            # ← Kembali ke Header (form cargo boleh kosong; kalau ada isian, minta simpan dulu)
            if action == "back":
                if _cargo_post_has_any_input(request.POST):
                    messages.error(request, "Form cargo masih berisi. Klik 'Tambah Cargo' untuk menyimpan atau kosongkan semua field sebelum kembali.")
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                wiz["step"] = "header"
                _wiz_set(request, wiz)
                return redirect("{}?step=header".format(request.path))

            if action == "cancel":
                _wiz_clear(request)
                return redirect("sales:freight_list")

            if action == "add":
                if cargo_fs.is_valid():
                    f = cargo_fs.forms[0]
                    cd = f.cleaned_data or {}
                    has_any = any(cd.get(k) for k in ("origin","destination","description","weight_kg","volume_cbm","price","amount"))
                    if not has_any:
                        messages.error(request, "Isi data cargo terlebih dahulu sebelum Tambah.")
                        return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

                    # Simpan NAMA lokasi saja ke session (tanpa ID)
                    added_lines.append({
                        "description": cd.get("description") or "",
                        "qty": cd.get("qty") or 1,
                        "weight_kg": cd.get("weight_kg"),
                        "volume_cbm": cd.get("volume_cbm"),
                        "price": cd.get("price"),
                        "amount": cd.get("amount"),
                        "origin": (cd.get("origin").name if cd.get("origin") else None),
                        "destination": (cd.get("destination").name if cd.get("destination") else None),
                    })
                    wiz["lines"] = added_lines
                    _wiz_set(request, wiz)
                    messages.success(request, "Cargo ditambahkan.")
                    # reset form kosong
                    cargo_fs = CargoFormSet(prefix="cargo", initial=[{}])
                    for f in cargo_fs.forms:
                        if "origin" in f.fields:
                            f.fields["origin"].queryset = origin_qs
                            f.fields["origin"].label_from_instance = (lambda o: o.name)
                        if "destination" in f.fields:
                            f.fields["destination"].queryset = dest_qs
                            f.fields["destination"].label_from_instance = (lambda o: o.name)
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                else:
                    messages.error(request, "Periksa isian cargo.")
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

            if action in ("finish", "save"):
                # Tidak boleh finish kalau form aktif masih berisi (belum di-Tambah)
                if _cargo_post_has_any_input(request.POST):
                    messages.error(request, "Masih ada isian cargo yang belum disimpan. Klik 'Tambah Cargo' atau kosongkan semua field sebelum Finish.")
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                if not added_lines:
                    messages.error(request, "Minimal satu Cargo wajib diisi sebelum Finish.")
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

                # Simpan header
                date_val = parse_date(hdr.get("date") or "") or datetime.date.today()
                q = FreightQuotation.objects.create(
                    date=date_val,
                    customer_id=hdr["customer_id"],
                    currency=hdr.get("currency") or "IDR",
                    payment_term=hdr.get("payment_term") or "",
                    transport_mode=hdr.get("transport_mode") or "SEA",
                    service_option=hdr.get("service_option") or "PORT_TO_PORT",
                    notes=hdr.get("notes") or "",
                    multi_destination=False,
                )

                # Map nama -> Location (berdasar tipe yang diizinkan)
                for row in added_lines:
                    qty = row.get("qty") or 1
                    price = row.get("price") or 0
                    amount = row.get("amount") or (qty * price)
                    origin_name = row.get("origin")
                    dest_name   = row.get("destination")
                    origin_obj = None
                    dest_obj   = None
                    if origin_name:
                        origin_obj = Location.objects.filter(name=origin_name, type__in=list(origin_types)).order_by("id").first()
                    if dest_name:
                        dest_obj   = Location.objects.filter(name=dest_name, type__in=list(dest_types)).order_by("id").first()

                    FreightCargo.objects.create(
                        quotation=q,
                        description=row.get("description") or "",
                        qty=qty,
                        weight_kg=row.get("weight_kg") or None,
                        volume_cbm=row.get("volume_cbm") or None,
                        price=price,
                        amount=amount,
                        origin=origin_obj,
                        destination=dest_obj,
                    )

                _wiz_clear(request)
                messages.success(request, "Freight Quotation {} berhasil dibuat.".format(q.number))
                return redirect("sales:freight_view", pk=q.pk)

            messages.info(request, "Aksi tidak dikenali.")
            return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

        # GET Step-2 (1 form kosong + daftar cargo)
        cargo_fs = CargoFormSet(prefix="cargo", initial=[{}])
        for f in cargo_fs.forms:
            if "origin" in f.fields:
                f.fields["origin"].queryset = origin_qs
                f.fields["origin"].label_from_instance = (lambda o: o.name)
            if "destination" in f.fields:
                f.fields["destination"].queryset = dest_qs
                f.fields["destination"].label_from_instance = (lambda o: o.name)
        return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

    # fallback -> header
    wiz["step"] = "header"
    _wiz_set(request, wiz)
    form = FreightHeaderForm(initial={"transport_mode": "SEA", "service_option": "PORT_TO_PORT"})
    form.fields["service_option"].choices = service_options_for_mode("SEA")
    return render(request, "sales/freight/wizard_v2.html", {"step": "header", "form_header": form})
"""

def main():
    write("sales/helpers_freight_overlay.py", HELPERS)
    write("sales/wizard_v2.py", WIZARD)
    print("\\nSelesai. Jalankan server dan buka: /sales/quotations/freight/new-v2/\\n"
          "- SEA Port-to-Port: SEAPORT only\\n"
          "- Dropdown lokasi tampil nama saja\\n"
          "- Session menyimpan nama original; Finish akan map nama -> Location sesuai tipe.\\n")

if __name__ == "__main__":
    main()
