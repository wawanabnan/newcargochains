# sales/wizard_v2.py
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
DEBUG_WIZ = True  # tampilkan info tombol & management form di halaman

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
    keys = ["origin","destination","description","weight_kg","volume_cbm","price","qty"]
    return any((post.get(pre+k) not in (None,"")) for k in keys)

def _row_from_cleaned(cd):
    # Pastikan TIDAK ada Decimal di session:
    # qty -> int, harga/berat/volume/amount -> float, lokasi -> nama (str)
    def _to_float(x):
        if x in (None, ""):
            return None
        try:
            return float(x)
        except Exception:
            return None

    qty = cd.get("qty")
    try:
        qty = int(qty) if qty not in (None, "") else 1
    except Exception:
        qty = 1

    price = _to_float(cd.get("price")) or 0.0
    weight = _to_float(cd.get("weight_kg"))
    volume = _to_float(cd.get("volume_cbm"))

    amount = float(qty) * float(price)

    return {
        "description": (cd.get("description") or ""),
        "qty": qty,                        # int
        "weight_kg": weight,               # float or None
        "volume_cbm": volume,              # float or None
        "price": float(price),             # float
        "amount": float(amount),           # float
        "origin": (cd.get("origin").name if cd.get("origin") else None),           # str
        "destination": (cd.get("destination").name if cd.get("destination") else None),
    }


@require_http_methods(["GET","POST"])
def freight_create_wizard_v2(request):
    # Reset paksa bila ?reset=1
    if request.GET.get("reset") == "1":
        _wiz_clear(request)

    wiz = _wiz_get(request)
    step = wiz.get("step") or "header"

    # ---------- STEP 1: HEADER ----------
    if step == "header":
        if request.method == "GET":
            form = FreightHeaderForm(initial={
                "date": datetime.date.today(),  # auto (tidak ditampilkan di UI)
                "transport_mode": wiz["header"].get("transport_mode") or "SEA",
                "service_option": wiz["header"].get("service_option") or "PORT_TO_PORT",
                "customer": wiz["header"].get("customer_id"),
                "currency": wiz["header"].get("currency") or "IDR",
                "payment_term": wiz["header"].get("payment_term") or "",
                "notes": wiz["header"].get("notes") or "",
                "valid_until": parse_date(wiz["header"].get("valid_until") or "") or None,
            })
            tm = form.initial.get("transport_mode") or "SEA"
            form.fields["service_option"].choices = service_options_for_mode(tm)
            return render(request, "sales/freight/wizard_v2.html", {"step":"header","form_header":form,"WIZ_VER":"R8"})

        # POST header → simpan minimal & lanjut ke lines (session-only)
        post = request.POST.copy()
        post.setdefault("date", datetime.date.today().isoformat())
        form = FreightHeaderForm(post)
        tm = post.get("transport_mode") or "SEA"
        form.fields["service_option"].choices = service_options_for_mode(tm)

        hdr = wiz.get("header", {})
        if form.is_valid():
            cd = form.cleaned_data
            hdr.update({
                "date": datetime.date.today().isoformat(),
                "customer_id": cd["customer"].pk,
                "currency": cd.get("currency") or "IDR",
                "payment_term": cd.get("payment_term") or "",
                "notes": cd.get("notes") or "",
                "transport_mode": cd.get("transport_mode") or "SEA",
                "service_option": cd.get("service_option") or "PORT_TO_PORT",
            })
            if cd.get("valid_until"):
                hdr["valid_until"] = cd["valid_until"].isoformat()
        else:
            # simpan minimal agar filter origin/destination bisa jalan di Step 2
            hdr.update({
                "date": datetime.date.today().isoformat(),
                "currency": post.get("currency") or hdr.get("currency") or "IDR",
                "payment_term": post.get("payment_term") or hdr.get("payment_term") or "",
                "notes": post.get("notes") or hdr.get("notes") or "",
                "transport_mode": post.get("transport_mode") or hdr.get("transport_mode") or "SEA",
                "service_option": post.get("service_option") or hdr.get("service_option") or "PORT_TO_PORT",
            })
            if post.get("valid_until"):
                hdr["valid_until"] = post["valid_until"]
            messages.warning(request, "Header belum lengkap. Lengkapi Customer sebelum Finish.")

        wiz["header"] = hdr
        wiz["step"] = "lines"
        _wiz_set(request, wiz)
        return redirect(request.path)  # tanpa query → GET lines

    # ---------- STEP 2: LINES ----------
    if not wiz.get("header"):  # kalau header kosong, balik ke header
        wiz["step"] = "header"
        _wiz_set(request, wiz)
        return redirect(request.path)

    hdr = wiz["header"]
    mode = hdr.get("transport_mode")
    opt  = hdr.get("service_option")

    origin_types, dest_types = origin_dest_types(mode, opt)
    origin_qs = qs_for_types(origin_types)
    dest_qs   = qs_for_types(dest_types)
    added_lines = list(wiz.get("lines") or [])

    if request.method == "GET":
        cargo_fs = CargoFormSet(prefix="cargo", initial=[{}])
        for f in cargo_fs.forms:
            if "origin" in f.fields:
                f.fields["origin"].queryset = origin_qs
                f.fields["origin"].label_from_instance = (lambda o: o.name)
                f.fields["origin"].required = False
            if "destination" in f.fields:
                f.fields["destination"].queryset = dest_qs
                f.fields["destination"].label_from_instance = (lambda o: o.name)
                f.fields["destination"].required = False
            # matikan required HTML biar POST tidak ditahan browser/JS
            for nm in ("description","weight_kg","volume_cbm","price","qty","amount"):
                if nm in f.fields:
                    f.fields[nm].required = False
            if "description" in f.fields:
                try: f.fields["description"].widget.attrs.update({"rows": 4})
                except Exception: pass
            if "amount" in f.fields:
                try: f.fields["amount"].widget.attrs.update({"readonly":"readonly"})
                except Exception: pass
        if DEBUG_WIZ:
            messages.info(request, f"DEBUG R8 GET lines")
        return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"WIZ_VER":"R8"})

    # POST di step lines
    cargo_fs = CargoFormSet(request.POST, prefix="cargo", initial=[{}])
    for f in cargo_fs.forms:
        if "origin" in f.fields:
            f.fields["origin"].queryset = origin_qs
            f.fields["origin"].label_from_instance = (lambda o: o.name)
            f.fields["origin"].required = False
        if "destination" in f.fields:
            f.fields["destination"].queryset = dest_qs
            f.fields["destination"].label_from_instance = (lambda o: o.name)
            f.fields["destination"].required = False
        for nm in ("description","weight_kg","volume_cbm","price","qty","amount"):
            if nm in f.fields:
                f.fields[nm].required = False
        if "description" in f.fields:
            try: f.fields["description"].widget.attrs.update({"rows": 4})
            except Exception: pass
        if "amount" in f.fields:
            try: f.fields["amount"].widget.attrs.update({"readonly":"readonly"})
            except Exception: pass

    # tombol bernama unik (anti konflik)
    is_back   = ("btn_back"   in request.POST)
    is_cancel = ("btn_cancel" in request.POST)
    is_add    = ("btn_add"    in request.POST)
    is_finish = ("btn_finish" in request.POST)

    if DEBUG_WIZ:
        keys = list(request.POST.keys())
        messages.info(request, f"DEBUG R8 POST keys={keys[:12]}... add={is_add} finish={is_finish} total_forms={request.POST.get('cargo-TOTAL_FORMS')}")

    if is_back:
        wiz["step"] = "header"
        _wiz_set(request, wiz)
        return redirect(request.path)

    if is_cancel:
        _wiz_clear(request)
        return redirect("sales:freight_list")

    def _active_row_or_none():
        # kalau tidak ada input sama sekali
        if not _cargo_post_has_any_input(request.POST):
            return None
        # coba validasi formset
        if cargo_fs.is_valid():
            return _row_from_cleaned(cargo_fs.forms[0].cleaned_data or {})
        # fallback: rakit manual dari POST (untuk bypass kendala client JS)
        origin_id = request.POST.get("cargo-0-origin")
        dest_id   = request.POST.get("cargo-0-destination")
        origin_name = Location.objects.filter(pk=origin_id).values_list("name", flat=True).first() if origin_id else None
        dest_name   = Location.objects.filter(pk=dest_id).values_list("name", flat=True).first() if dest_id   else None
        desc  = request.POST.get("cargo-0-description") or ""
        qty   = request.POST.get("cargo-0-qty") or "1"
        price = request.POST.get("cargo-0-price") or "0"
        try:
            qty_i = int(float(qty))
        except:
            qty_i = 1
        try:
            price_f = float(price)
        except:
            price_f = 0.0
        row = {
            "description": desc,
            "qty": qty_i,
            "weight_kg": request.POST.get("cargo-0-weight_kg") or None,
            "volume_cbm": request.POST.get("cargo-0-volume_cbm") or None,
            "price": price_f,
            "amount": qty_i * price_f,
            "origin": origin_name,
            "destination": dest_name,
        }
        return row

    if is_add:
        row = _active_row_or_none()
        if row is None:
            messages.error(request, "Isi data cargo terlebih dahulu sebelum Tambah.")
            return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"WIZ_VER":"R8"})
        added_lines.append(row)
        wiz["lines"] = added_lines
        _wiz_set(request, wiz)
        messages.success(request, "Cargo ditambahkan.")
        # reset form kosong (agar bersih dari nilai lama)
        cargo_fs = CargoFormSet(prefix="cargo", initial=[{}])
        for f in cargo_fs.forms:
            if "origin" in f.fields:
                f.fields["origin"].queryset = origin_qs
                f.fields["origin"].label_from_instance = (lambda o: o.name)
                f.fields["origin"].required = False
            if "destination" in f.fields:
                f.fields["destination"].queryset = dest_qs
                f.fields["destination"].label_from_instance = (lambda o: o.name)
                f.fields["destination"].required = False
            for nm in ("description","weight_kg","volume_cbm","price","qty","amount"):
                if nm in f.fields:
                    f.fields[nm].required = False
            if "description" in f.fields:
                try: f.fields["description"].widget.attrs.update({"rows": 4})
                except Exception: pass
            if "amount" in f.fields:
                try: f.fields["amount"].widget.attrs.update({"readonly":"readonly"})
                except Exception: pass
        return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"WIZ_VER":"R8"})

    if is_finish:
        # header wajib: customer harus ada
        if not hdr.get("customer_id"):
            messages.error(request, "Customer belum diisi. Lengkapi Header terlebih dahulu.")
            wiz["step"] = "header"
            _wiz_set(request, wiz)
            return redirect(request.path)

        lines_for_save = list(added_lines)
        row = _active_row_or_none()
        if isinstance(row, dict):
            lines_for_save.append(row)
        if not lines_for_save:
            messages.error(request, "Minimal satu Cargo wajib diisi sebelum Finish.")
            return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"WIZ_VER":"R8"})

        # Simpan header
        date_val = parse_date(hdr.get("date") or "") or datetime.date.today()
        kwargs = dict(
            date=date_val,
            customer_id=hdr["customer_id"],
            currency=hdr.get("currency") or "IDR",
            payment_term=hdr.get("payment_term") or "",
            transport_mode=hdr.get("transport_mode") or "SEA",
            service_option=hdr.get("service_option") or "PORT_TO_PORT",
            notes=hdr.get("notes") or "",
            multi_destination=False,
        )
        vu = parse_date(hdr.get("valid_until") or "")
        if vu:
            kwargs["valid_until"] = vu
        try:
            q = FreightQuotation.objects.create(**kwargs)
        except TypeError:
            kwargs.pop("valid_until", None)
            q = FreightQuotation.objects.create(**kwargs)

        # Simpan cargo (lookup nama → Location sesuai tipe)
        for r in lines_for_save:
            qty = r.get("qty") or 1
            price = r.get("price") or 0
            amount = qty * price
            origin_name = r.get("origin")
            dest_name   = r.get("destination")
            origin_obj = Location.objects.filter(name=origin_name, type__in=list(origin_types)).first() if origin_name else None
            dest_obj   = Location.objects.filter(name=dest_name,   type__in=list(dest_types)).first()   if dest_name   else None

            FreightCargo.objects.create(
                quotation=q,
                description=r.get("description") or "",
                qty=qty,
                weight_kg=r.get("weight_kg") or None,
                volume_cbm=r.get("volume_cbm") or None,
                price=price,
                amount=amount,
                origin=origin_obj,
                destination=dest_obj,
            )

        _wiz_clear(request)
        messages.success(request, f"Freight Quotation {q.number} berhasil dibuat.")
        return redirect("sales:freight_list")

    # aksi tak dikenal → render lagi
    messages.info(request, "Aksi tidak dikenali.")
    return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"WIZ_VER":"R8"})
