# upgrade_wizard_v2_single_form.py
# Jalankan dari root project:  python upgrade_wizard_v2_single_form.py
import os, io

BASE = os.getcwd()

def write(path, content):
    abspath = os.path.join(BASE, path)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with io.open(abspath, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print("Wrote:", path)

WIZARD_V2 = u'''# sales/wizard_v2.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils.dateparse import parse_date
import datetime

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
    # Periksa apakah form cargo "aktif" punya input (untuk blok Finish/Back)
    pre = "cargo-0-"
    keys = ["origin", "destination", "description", "weight_kg", "volume_cbm", "price", "amount"]
    for k in keys:
        v = post.get(pre + k)
        if v not in (None, ""):
            return True
    return False

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

        # Daftar cargo yang sudah ditambahkan (dari session)
        added_lines = list(wiz.get("lines") or [])

        if request.method == "POST":
            # Pakai FormSet tapi hanya 1 form (index 0) sebagai "current form"
            cargo_fs = CargoFormSet(request.POST, prefix="cargo")
            # Pasang queryset filter
            for f in cargo_fs.forms:
                if "origin" in f.fields:      f.fields["origin"].queryset = origin_qs
                if "destination" in f.fields: f.fields["destination"].queryset = dest_qs

            action = (request.POST.get("action") or "finish").lower()

            # Kembali ke header: hanya jika form kosong (tidak ada input aktif)
            if action == "back":
                if _cargo_post_has_any_input(request.POST):
                    messages.error(request, "Form cargo masih berisi. Simpan (Tambah Cargo) atau kosongkan sebelum kembali ke Header.")
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                wiz["step"] = "header"
                _wiz_set(request, wiz)
                return redirect("{}?step=header".format(request.path))

            # Cancel seluruh wizard
            if action == "cancel":
                _wiz_clear(request)
                return redirect("sales:freight_list")

            # Tambah cargo saat ini ke session
            if action == "add":
                if cargo_fs.is_valid():
                    f = cargo_fs.forms[0]
                    cd = f.cleaned_data or {}
                    # Wajib ada minimal salah satu field utama (origin/destination/description)
                    meaningful = any(cd.get(k) for k in ("origin","destination","description","weight_kg","volume_cbm","price","amount"))
                    if not meaningful:
                        messages.error(request, "Isi data cargo terlebih dahulu sebelum Tambah.")
                        return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                    added_lines.append({
                        "description": cd.get("description") or "",
                        "qty": cd.get("qty") or 1,
                        "weight_kg": cd.get("weight_kg"),
                        "volume_cbm": cd.get("volume_cbm"),
                        "price": cd.get("price"),
                        "amount": cd.get("amount"),
                        "origin": cd.get("origin").id if cd.get("origin") else None,
                        "destination": cd.get("destination").id if cd.get("destination") else None,
                    })
                    wiz["lines"] = added_lines
                    _wiz_set(request, wiz)
                    messages.success(request, "Cargo ditambahkan.")
                    # render ulang form kosong
                    cargo_fs = CargoFormSet(prefix="cargo", initial=[{}])
                    for f in cargo_fs.forms:
                        if "origin" in f.fields:      f.fields["origin"].queryset = origin_qs
                        if "destination" in f.fields: f.fields["destination"].queryset = dest_qs
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                else:
                    messages.error(request, "Periksa isian cargo.")
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

            # Finish/Simpan semua cargo yg sudah ditambahkan
            if action == "finish" or action == "save":
                # Blok kalau form aktif ada input (belum di-Add)
                if _cargo_post_has_any_input(request.POST):
                    messages.error(request, "Masih ada isian cargo yang belum disimpan. Klik 'Tambah Cargo' atau kosongkan semua field sebelum Finish.")
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})
                if not added_lines:
                    messages.error(request, "Minimal satu Cargo wajib diisi sebelum Finish.")
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

                # Simpan quotation + semua cargo dari session
                date_val = parse_date(hdr.get("date") or "")
                if not date_val:
                    date_val = datetime.date.today()
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

                created = 0
                for row in added_lines:
                    qty = row.get("qty") or 1
                    price = row.get("price") or 0
                    amount = row.get("amount") or (qty * price)
                    FreightCargo.objects.create(
                        quotation=q,
                        description=row.get("description") or "",
                        qty=qty,
                        weight_kg=row.get("weight_kg") or None,
                        volume_cbm=row.get("volume_cbm") or None,
                        price=price,
                        amount=amount,
                        origin_id=row.get("origin"),
                        destination_id=row.get("destination"),
                    )
                    created += 1

                _wiz_clear(request)
                messages.success(request, "Freight Quotation {} berhasil dibuat.".format(q.number))
                return redirect("sales:freight_view", pk=q.pk)

            # Aksi tak dikenal
            messages.info(request, "Aksi tidak dikenali.")
            return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

        # GET Step-2 (tampilkan 1 form kosong + daftar cargo yang sudah ditambah)
        cargo_fs = CargoFormSet(prefix="cargo", initial=[{}])
        for f in cargo_fs.forms:
            if "origin" in f.fields:      f.fields["origin"].queryset = origin_qs
            if "destination" in f.fields: f.fields["destination"].queryset = dest_qs

        return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs, "lines": added_lines})

    # fallback -> header
    wiz["step"] = "header"
    _wiz_set(request, wiz)
    form = FreightHeaderForm(initial={"transport_mode": "SEA", "service_option": "PORT_TO_PORT"})
    form.fields["service_option"].choices = service_options_for_mode("SEA")
    return render(request, "sales/freight/wizard_v2.html", {"step": "header", "form_header": form})
'''

WIZARD_TPL = u'''{% extends "base.html" %}
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
          <div class="col-md-3">
            <label class="form-label">Date</label>
            {{ form_header.date }} <div class="text-danger small">{{ form_header.date.errors }}</div>
          </div>
          <div class="col-md-3">
            <label class="form-label">Payment Term</label>
            {{ form_header.payment_term }} <div class="text-danger small">{{ form_header.payment_term.errors }}</div>
          </div>
          <div class="col-md-6">
            <label class="form-label">Customer</label>
            {{ form_header.customer }} <div class="text-danger small">{{ form_header.customer.errors }}</div>
          </div>
          <div class="col-md-3">
            <label class="form-label">Transport Mode</label>
            {{ form_header.transport_mode }} <div class="text-danger small">{{ form_header.transport_mode.errors }}</div>
          </div>
          <div class="col-md-3">
            <label class="form-label">Service Option</label>
            {{ form_header.service_option }} <div class="text-danger small">{{ form_header.service_option.errors }}</div>
          </div>
          <div class="col-md-3">
            <label class="form-label">Currency</label>
            {{ form_header.currency }} <div class="text-danger small">{{ form_header.currency.errors }}</div>
          </div>
          <div class="col-md-12">
            <label class="form-label">Notes</label>
            {{ form_header.notes }} <div class="text-danger small">{{ form_header.notes.errors }}</div>
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
    var modeEl = document.getElementById('id_transport_mode');
    var svcEl  = document.getElementById('id_service_option');
    if(!modeEl || !svcEl) return;
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
    setOptionsFor(modeEl.value);
    modeEl.addEventListener('change', function(){ setOptionsFor(this.value); });
  })();
  </script>
  {% endif %}

  {% if step == "lines" %}
  <div class="row g-3">
    <div class="col-lg-5">
      <div class="card shadow-sm h-100">
        <div class="card-header"><strong>Tambah Cargo</strong></div>
        <div class="card-body">
          <form method="post" id="cargo-form" novalidate>
            {% csrf_token %}
            {{ cargo_fs.management_form }}
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
                {{ f.description }} <div class="text-danger small">{{ f.description.errors }}</div>
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
                  <label class="form-label">Price</label>
                  {{ f.price }} <div class="text-danger small">{{ f.price.errors }}</div>
                </div>
                <div class="col">
                  <label class="form-label">Amount</label>
                  {{ f.amount }} <div class="text-danger small">{{ f.amount.errors }}</div>
                </div>
              </div>
            {% endwith %}

            <div class="d-flex flex-wrap gap-2 mt-3">
              <button class="btn btn-outline-secondary" type="submit" name="action" value="back">← Kembali ke Header</button>
              <button class="btn btn-outline-danger ms-auto" type="submit" name="action" value="cancel">Cancel</button>
              <button class="btn btn-outline-primary" type="submit" name="action" value="add">+ Tambah Cargo</button>
              <button class="btn btn-primary" type="submit" name="action" value="finish">Finish / Simpan</button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <div class="col-lg-7">
      <div class="card shadow-sm h-100">
        <div class="card-header"><strong>Daftar Cargo (tersimpan)</strong></div>
        <div class="card-body">
          {% if lines and lines|length > 0 %}
          <div class="table-responsive">
            <table class="table table-sm table-bordered align-middle">
              <thead class="table-light">
                <tr>
                  <th style="width:20%">Origin</th>
                  <th style="width:20%">Destination</th>
                  <th>Description</th>
                  <th class="text-end" style="width:10%">Qty</th>
                  <th class="text-end" style="width:12%">Weight</th>
                  <th class="text-end" style="width:12%">Volume</th>
                  <th class="text-end" style="width:12%">Amount</th>
                </tr>
              </thead>
              <tbody>
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
          <p class="text-muted mb-0">Belum ada cargo yang ditambahkan. Isi form di kiri lalu tekan <b>Tambah Cargo</b>.</p>
          {% endif %}
        </div>
      </div>
    </div>
  </div>
  {% endif %}
</div>
{% endblock %}
'''

def main():
    write("sales/wizard_v2.py", WIZARD_V2)
    write("templates/sales/freight/wizard_v2.html", WIZARD_TPL)
    print("\nSelesai. Jalankan server dan buka: /sales/quotations/freight/new-v2/\n")

if __name__ == "__main__":
    main()
