# hotfix_wizard_v2_finish_back.py
# Jalankan dari root project. Menimpa sales/wizard_v2.py dengan logika:
# - Back selalu boleh (abaikan input aktif).
# - Finish menyertakan baris aktif bila valid (tanpa wajib klik "Tambah Cargo").
# - Dropdown lokasi tampil nama; Port-to-Port SEA => SEAPORT only (via helpers yang sudah ada).
import os, io
from pathlib import Path

BASE = Path.cwd()
TARGET = BASE / "sales" / "wizard_v2.py"

CODE = r'''# sales/wizard_v2.py
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
    keys = ["origin", "destination", "description", "weight_kg", "volume_cbm", "price", "amount", "qty"]
    for k in keys:
        v = post.get(pre + k)
        if v not in (None, ""):
            return True
    return False

def _row_from_cleaned(cd):
    # Simpan nama lokasi, bukan ID
    return {
        "description": cd.get("description") or "",
        "qty": cd.get("qty") or 1,
        "weight_kg": cd.get("weight_kg"),
        "volume_cbm": cd.get("volume_cbm"),
        "price": cd.get("price"),
        "amount": cd.get("amount"),
        "origin": (cd.get("origin").name if cd.get("origin") else None),
        "destination": (cd.get("destination").name if cd.get("destination") else None),
    }

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

        # filter lokasi sesuai header
        origin_types, dest_types = origin_dest_types(mode, opt)
        origin_qs = qs_for_types(origin_types)
        dest_qs   = qs_for_types(dest_types)

        added_lines = list(wiz.get("lines") or [])

        if request.method == "POST":
            cargo_fs = CargoFormSet(request.POST, prefix="cargo")
            for f in cargo_fs.forms:
                if "origin" in f.fields:
                    f.fields["origin"].queryset = origin_qs
                    f.fields["origin"].label_from_instance = (lambda o: o.name)
                if "destination" in f.fields:
                    f.fields["destination"].queryset = dest_qs
                    f.fields["destination"].label_from_instance = (lambda o: o.name)

            action = (request.POST.get("action") or "finish").lower()

            # ← Kembali ke Header: sekarang SELALU boleh (input aktif diabaikan)
            if action == "back":
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
                    has_any = any(cd.get(k) for k in ("origin","destination","description","weight_kg","volume_cbm","price","amount","qty"))
                    if not has_any:
                        messages.error(request, "Isi data cargo terlebih dahulu sebelum Tambah.")
                        return render(request, "sales/freight/wizard_v2.html",
                                      {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                    added_lines.append(_row_from_cleaned(cd))
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
                    return render(request, "sales/freight/wizard_v2.html",
                                  {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                else:
                    messages.error(request, "Periksa isian cargo.")
                    return render(request, "sales/freight/wizard_v2.html",
                                  {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

            if action in ("finish", "save"):
                lines_for_save = list(added_lines)
                if _cargo_post_has_any_input(request.POST):
                    # Validasi baris aktif; jika valid, ikutkan ke saving tanpa perlu klik "Tambah"
                    if cargo_fs.is_valid():
                        cd = cargo_fs.forms[0].cleaned_data or {}
                        lines_for_save.append(_row_from_cleaned(cd))
                    else:
                        messages.error(request, "Periksa isian cargo yang aktif sebelum Finish.")
                        return render(request, "sales/freight/wizard_v2.html",
                                      {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                else:
                    if not lines_for_save:
                        messages.error(request, "Minimal satu Cargo wajib diisi sebelum Finish.")
                        return render(request, "sales/freight/wizard_v2.html",
                                      {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

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

                # Map nama -> Location berdasar tipe yang diizinkan
                for row in lines_for_save:
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

            # aksi tak dikenal
            messages.info(request, "Aksi tidak dikenali.")
            return render(request, "sales/freight/wizard_v2.html",
                          {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

        # GET Step-2 (form kosong + daftar cargo)
        cargo_fs = CargoFormSet(prefix="cargo", initial=[{}])
        for f in cargo_fs.forms:
            if "origin" in f.fields:
                f.fields["origin"].queryset = origin_qs
                f.fields["origin"].label_from_instance = (lambda o: o.name)
            if "destination" in f.fields:
                f.fields["destination"].queryset = dest_qs
                f.fields["destination"].label_from_instance = (lambda o: o.name)
        return render(request, "sales/freight/wizard_v2.html",
                      {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

    # fallback -> header
    wiz["step"] = "header"
    _wiz_set(request, wiz)
    form = FreightHeaderForm(initial={"transport_mode": "SEA", "service_option": "PORT_TO_PORT"})
    form.fields["service_option"].choices = service_options_for_mode("SEA")
    return render(request, "sales/freight/wizard_v2.html", {"step": "header", "form_header": form})
'''

def main():
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(CODE, encoding="utf-8")
    print("Wrote:", TARGET)

if __name__ == "__main__":
    main()
