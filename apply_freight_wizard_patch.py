# apply_freight_wizard_patch_v3.py
# Jalankan: python apply_freight_wizard_patch_v3.py
# Menimpa / membuat file:
# - sales/helpers_freight_overlay.py
# - sales/wizard_v2.py
# - templates/sales/freight/wizard_v2.html
# Serta menambahi route new-v2 di sales/urls.py bila belum ada.

import io, re
from pathlib import Path

BASE = Path.cwd()

def write(path, content):
    p = BASE / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print("Wrote:", path)

def patch_urls():
    upath = BASE / "sales" / "urls.py"
    if not upath.exists():
        print("WARNING: sales/urls.py tidak ditemukan. Tambahkan route manual.")
        return
    txt = upath.read_text(encoding="utf-8")

    if "from django.urls import path" not in txt:
        txt = "from django.urls import path\n" + txt

    if "from .wizard_v2 import freight_create_wizard_v2" not in txt:
        txt = txt.replace(
            "from django.urls import path",
            "from django.urls import path\nfrom .wizard_v2 import freight_create_wizard_v2"
        )

    if "freight_create_v2" not in txt:
        # sisipkan route
        if "urlpatterns" not in txt:
            txt += "\nurlpatterns = []\n"
        txt = re.sub(
            r"urlpatterns\s*=\s*\[",
            'urlpatterns = [\n    path("quotations/freight/new-v2/", freight_create_wizard_v2, name="freight_create_v2"),',
            txt,
            count=1
        )

    upath.write_text(txt, encoding="utf-8")
    print("Patched: sales/urls.py (route /sales/quotations/freight/new-v2/)")

HELPERS = r'''# sales/helpers_freight_overlay.py
from geo.models import Location

def normalize_opt(val):
    return (val or "").upper().replace("-", "_").replace(" ", "_")

def origin_dest_types(transport_mode, service_option):
    """
    Return (origin_types, dest_types) berupa SET tipe Location yang dibolehkan.
    - TRUCK/LAND/ROAD/TRUCKING -> CITY <-> CITY
    - SEA 'port' = SEAPORT (TANPA JETTY)
    - AIR 'port' = AIRPORT
    - DOOR<->DOOR = CITY<->CITY
    - DOOR->PORT = CITY->PORT
    - PORT->DOOR = PORT->CITY
    - PORT<->PORT = PORT<->PORT
    """
    mode = normalize_opt(transport_mode)
    opt  = normalize_opt(service_option)

    if mode in ("LAND", "TRUCK", "ROAD", "TRUCKING"):
        return ({Location.CITY}, {Location.CITY})

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
'''

WIZARD = r'''# sales/wizard_v2.py
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
    qty   = cd.get("qty") or 1
    price = cd.get("price") or 0
    return {
        "description": cd.get("description") or "",
        "qty": qty,
        "weight_kg": cd.get("weight_kg"),
        "volume_cbm": cd.get("volume_cbm"),
        "price": price,
        "amount": qty * price,  # amount selalu dihitung
        "origin": (cd.get("origin").name if cd.get("origin") else None),
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
            return render(request, "sales/freight/wizard_v2.html", {"step":"header","form_header":form,"__WIZ_VER":"R8"})

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
        return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"__WIZ_VER":"R8"})

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
            return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"__WIZ_VER":"R8"})
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
        return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"__WIZ_VER":"R8"})

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
            return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"__WIZ_VER":"R8"})

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
        return redirect("sales:freight_view", pk=q.pk)

    # aksi tak dikenal → render lagi
    messages.info(request, "Aksi tidak dikenali.")
    return render(request, "sales/freight/wizard_v2.html", {"step":"lines","cargo_fs":cargo_fs,"lines":added_lines,"__WIZ_VER":"R8"})
'''

TPL = r'''{% extends "base.html" %}
{% load static %}
{% block title %}Freight Wizard (V2){% endblock %}
{% block content %}
<div class="container-fluid py-3">
  {% if messages %}
    {% for message in messages %}
      <div class="alert alert-{{ message.tags|default:'info' }} mb-2" role="alert">{{ message }}</div>
    {% endfor %}
  {% endif %}

  {% if step == "header" %}
  <div class="card shadow-sm">
    <div class="card-header"><h5 class="card-title mb-0">Step 1 — Quotation Header</h5></div>
    <div class="card-body">
      <form method="post" novalidate>
        {% csrf_token %}
        {% if form_header.non_field_errors %}
          <div class="alert alert-danger">{{ form_header.non_field_errors }}</div>
        {% endif %}

        <div class="row g-3">
          {# 'date' tidak ditampilkan (auto today di server) #}

          <div class="col-md-3">
            <label class="form-label">Valid Until</label>
            {% if form_header.valid_until %}
              {{ form_header.valid_until }}
              <div class="text-danger small">{{ form_header.valid_until.errors }}</div>
            {% else %}
              <input type="date" name="valid_until" class="form-control"/>
            {% endif %}
          </div>

          <div class="col-md-6">
            <label class="form-label">Customer</label>
            {{ form_header.customer }}
            <div class="text-danger small">{{ form_header.customer.errors }}</div>
          </div>

          <div class="col-md-3">
            <label class="form-label">Transport Mode</label>
            {{ form_header.transport_mode }}
            <div class="text-danger small">{{ form_header.transport_mode.errors }}</div>
          </div>

          <div class="col-md-3">
            <label class="form-label">Service Option</label>
            {{ form_header.service_option }}
            <div class="text-danger small">{{ form_header.service_option.errors }}</div>
          </div>

          <div class="col-md-3">
            <label class="form-label">Currency</label>
            {{ form_header.currency }}
            <div class="text-danger small">{{ form_header.currency.errors }}</div>
          </div>

          <div class="col-md-12">
            <label class="form-label">Notes</label>
            {{ form_header.notes }}
            <div class="text-danger small">{{ form_header.notes.errors }}</div>
          </div>
        </div>

        <div class="d-flex justify-content-end mt-3">
          <button class="btn btn-primary" type="submit">Next →</button>
        </div>
      </form>
    </div>
  </div>

  <script>
  (function(){
    // service option mengikuti mode
    var modeEl = document.getElementById('id_transport_mode');
    var svcEl  = document.getElementById('id_service_option');
    if(modeEl && svcEl){
      var OPTIONS = {
        'SEA': [['PORT_TO_PORT','Port to Port'],['DOOR_TO_PORT','Door to Port'],['PORT_TO_DOOR','Port to Door'],['DOOR_TO_DOOR','Door to Door']],
        'AIR': [['PORT_TO_PORT','Airport to Airport'],['DOOR_TO_PORT','Door to Airport'],['PORT_TO_DOOR','Airport to Door'],['DOOR_TO_DOOR','Door to Door']],
        'TRUCK': [['DOOR_TO_DOOR','Door to Door']],
        'LAND':  [['DOOR_TO_DOOR','Door to Door']],
        'ROAD':  [['DOOR_TO_DOOR','Door to Door']],
        'TRUCKING': [['DOOR_TO_DOOR','Door to Door']]
      };
      function setOptionsFor(mode){
        var m = (mode || '').toUpperCase();
        var opts = OPTIONS[m] || OPTIONS['SEA'];
        var cur = svcEl.value;
        while (svcEl.firstChild) svcEl.removeChild(svcEl.firstChild);
        for (var i=0;i<opts.length;i++){
          var o = document.createElement('option');
          o.value = opts[i][0]; o.text = opts[i][1];
          svcEl.appendChild(o);
        }
        var found=false; for (var j=0;j<svcEl.options.length;j++){ if (svcEl.options[j].value===cur){found=true;break;} }
        svcEl.value = found?cur:(svcEl.options[0]?svcEl.options[0].value:'');
      }
      if(modeEl && svcEl){ setOptionsFor(modeEl.value); modeEl.addEventListener('change', function(){ setOptionsFor(this.value); }); }

      // date picker auto-open saat fokus
      var vu = document.querySelector('input[name="valid_until"], #id_valid_until');
      if (vu && vu.showPicker) { vu.addEventListener('focus', function(){ try{ this.showPicker(); }catch(e){} }); }
    }
  })();
  </script>
  {% endif %}

  {% if step == "lines" %}
  {# SATU form membungkus kiri + kanan → tombol Finish ikut POST FormSet #}
  <form method="post" id="cargo-form" novalidate>
    {% csrf_token %}
    {{ cargo_fs.management_form }}

    <div class="row g-3">
      <div class="col-lg-7">
        <div class="card shadow-sm h-100">
          <div class="card-header"><strong>Tambah Cargo</strong></div>
          <div class="card-body">
            {% with f=cargo_fs.forms.0 %}
              <div class="mb-2">
                <label class="form-label">Origin</label>
                {{ f.origin }} <div class="text-danger small">{{ f.origin.errors }}</div>
              </div>
              <div class="mb-2">
                <label class="form-label">Destination</label>
                {{ f.destination }} <div class="text-danger small">{{ f.destination.errors }}</div>
              </div>

              <div class="mb-2">
                <label class="form-label">Description</label>
                {{ f.description }}
                <div class="text-danger small">{{ f.description.errors }}</div>
              </div>

              <div class="row g-2">
                <div class="col">
                  <label class="form-label">Weight (KG)</label>
                  {{ f.weight_kg }} <div class="text-danger small">{{ f.weight_kg.errors }}</div>
                </div>
                <div class="col">
                  <label class="form-label">Volume (CBM)</label>
                  {{ f.volume_cbm }} <div class="text-danger small">{{ f.volume_cbm.errors }}</div>
                </div>
              </div>

              <div class="row g-2 mt-1">
                <div class="col">
                  <label class="form-label">Qty</label>
                  {{ f.qty }} <div class="text-danger small">{{ f.qty.errors }}</div>
                </div>
                <div class="col">
                  <label class="form-label">Price</label>
                  {{ f.price }} <div class="text-danger small">{{ f.price.errors }}</div>
                </div>
              </div>

              <div class="mt-2">
                <label class="form-label">Amount (Qty × Price)</label>
                {{ f.amount }}
                <div class="text-muted small">Otomatis dihitung dari Qty × Price.</div>
              </div>
            {% endwith %}

            <style> textarea[name="cargo-0-description"]{ min-height: 96px; } </style>

            <div class="d-flex flex-wrap gap-2 mt-3">
              <button class="btn btn-outline-secondary" type="submit" name="btn_back"   value="1">← Kembali ke Header</button>
              <button class="btn btn-outline-danger"    type="submit" name="btn_cancel" value="1">Cancel</button>
              <button class="btn btn-outline-primary ms-auto" type="submit" name="btn_add"    value="1">+ Tambah Cargo</button>
            </div>
          </div>
        </div>
      </div>

      <div class="col-lg-5">
        <div class="card shadow-sm h-100">
          <div class="card-header d-flex align-items-center justify-content-between">
            <strong>Daftar Cargo (siap disimpan) — <span class="text-muted">Wizard V2 {{ __WIZ_VER|default:"" }}</span></strong>
            <button id="finishBtn" class="btn btn-primary btn-sm"
                    type="submit" name="btn_finish" value="1"
                    {% if not lines or lines|length == 0 %}disabled{% endif %}>
              Finish / Simpan
            </button>
          </div>
          <div class="card-body">
            {% if lines and lines|length > 0 %}
            <div class="table-responsive">
              <table class="table table-sm table-bordered align-middle">
                <thead class="table-light">
                  <tr>
                    <th style="width:22%">Origin</th>
                    <th style="width:22%">Destination</th>
                    <th>Description</th>
                    <th class="text-end" style="width:10%">Qty</th>
                    <th class="text-end" style="width:12%">Weight</th>
                    <th class="text-end" style="width:12%">Volume</th>
                    <th class="text-end" style="width:12%">Amount</th>
                  </tr>
                </thead>
                <tbody id="saved-lines">
                  {% for row in lines %}
                  <tr>
                    <td>{{ row.origin }}</td>
                    <td>{{ row.destination }}</td>
                    <td>{{ row.description }}</td>
                    <td class="text-end">{{ row.qty|default:1 }}</td>
                    <td class="text-end">{{ row.weight_kg }}</td>
                    <td class="text-end">{{ row.volume_cbm }}</td>
                    <td class="text-end">{{ row.amount }}</td>
                  </tr>
                  {% endfor %}
                </tbody>
              </table>
            </div>
            {% else %}
            <p class="text-muted mb-0">Belum ada cargo. Tambahkan cargo di panel kiri, lalu tombol <b>Finish</b> akan aktif.</p>
            {% endif %}
          </div>
        </div>
      </div>
    </div>
  </form>

  <script>
  (function(){
    // Hitung amount = qty * price real-time
    var qty = document.getElementById('id_cargo-0-qty');
    var price = document.getElementById('id_cargo-0-price');
    var amount = document.getElementById('id_cargo-0-amount');
    function recalc(){
      var q = parseFloat(qty && qty.value ? qty.value : 0);
      var p = parseFloat(price && price.value ? price.value : 0);
      var a = (isNaN(q)?0:q) * (isNaN(p)?0:p);
      if (amount) { amount.value = a.toFixed(2); }
    }
    if (qty) qty.addEventListener('input', recalc);
    if (price) price.addEventListener('input', recalc);
    recalc();
  })();
  </script>
  {% endif %}
</div>
{% endblock %}
'''

def main():
    write("sales/helpers_freight_overlay.py", HELPERS)
    write("sales/wizard_v2.py", WIZARD)
    write("templates/sales/freight/wizard_v2.html", TPL)
    patch_urls()
    print("\nDONE.\n- Jalankan server dan buka: /sales/quotations/freight/new-v2/?reset=1"
          "\n- Panel kanan akan menampilkan versi 'Wizard V2 R8' sebagai penanda template benar."
          "\n- Saat klik tombol, akan muncul pesan DEBUG (sementara) di atas untuk memastikan POST tertangkap.\n")

if __name__ == "__main__":
    main()
