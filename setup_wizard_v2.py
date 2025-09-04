# setup_wizard_v2.py
# Jalankan dari root project:  python setup_wizard_v2.py
import os, io, re

BASE = os.getcwd()

def write(path, content):
    abspath = os.path.join(BASE, path)
    os.makedirs(os.path.dirname(abspath), exist_ok=True)
    with io.open(abspath, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print("Wrote:", path)

def append_once(path, snippet, marker=None):
    abspath = os.path.join(BASE, path)
    with io.open(abspath, "r", encoding="utf-8") as f:
        txt = f.read()
    if snippet in txt:
        print("Skip (exists):", snippet.strip().splitlines()[0][:80])
        return
    if marker and marker in txt:
        txt = txt.replace(marker, marker + "\n" + snippet)
    else:
        txt = txt + ("\n" if not txt.endswith("\n") else "") + snippet + "\n"
    with io.open(abspath, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    print("Patched:", path, " (+snippet)")

# ----------------------------
# 1) Helper overlay (baru)
# ----------------------------
HELPERS = u'''# sales/helpers_freight_overlay.py
from geo.models import Location

def normalize_opt(val):
    return (val or "").upper().replace("-", "_").replace(" ", "_")

def origin_dest_types(transport_mode, service_option):
    """
    Return (origin_types, dest_types) berupa SET tipe Location yang dibolehkan.
    TRUCK/LAND → CITY↔CITY, SEA 'port' = SEAPORT/JETTY, AIR 'port' = AIRPORT.
    DOOR↔DOOR=CITY↔CITY, DOOR→PORT=CITY→PORT, PORT→DOOR=PORT→CITY, PORT↔PORT=PORT↔PORT
    """
    mode = normalize_opt(transport_mode)
    opt  = normalize_opt(service_option)
    if mode in ("LAND", "TRUCK", "ROAD", "TRUCKING"):
        return ({Location.CITY}, {Location.CITY})
    port_types = {Location.AIRPORT} if mode == "AIR" else {Location.SEAPORT, Location.JETTY}
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

# ----------------------------
# 2) View wizard V2 (baru)
# ----------------------------
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
        # service choices dinamis saat GET
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

    # ---------------------- STEP 2: LINES ----------------------
    if step == "lines":
        hdr = wiz["header"]
        mode = hdr.get("transport_mode")
        opt  = hdr.get("service_option")

        origin_types, dest_types = origin_dest_types(mode, opt)
        origin_qs = qs_for_types(origin_types)
        dest_qs   = qs_for_types(dest_types)

        if request.method == "POST":
            cargo_fs = CargoFormSet(request.POST, prefix="cargo")
            for f in cargo_fs.forms:
                if "origin" in f.fields:
                    f.fields["origin"].queryset = origin_qs
                if "destination" in f.fields:
                    f.fields["destination"].queryset = dest_qs

            action = (request.POST.get("action") or "save").lower()

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
                    return redirect("{}?step=header".format(request.path))
                messages.error(request, "Periksa isian Cargo sebelum kembali.")
                return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs})

            if action == "cancel":
                _wiz_clear(request)
                return redirect("sales:freight_list")

            if cargo_fs.is_valid():
                # validasi tipe lokasi konsisten
                has_type_error = False
                for f in cargo_fs:
                    cd = getattr(f, "cleaned_data", {}) or {}
                    if not cd:
                        continue
                    o = cd.get("origin"); d = cd.get("destination")
                    if o and o.type not in origin_types:
                        f.add_error("origin", "Origin harus sesuai Service Option (City/Port/Airport).")
                        has_type_error = True
                    if d and d.type not in dest_types:
                        f.add_error("destination", "Destination harus sesuai Service Option (City/Port/Airport).")
                        has_type_error = True
                if has_type_error:
                    for f in cargo_fs.forms:
                        if "origin" in f.fields:
                            f.fields["origin"].queryset = origin_qs
                        if "destination" in f.fields:
                            f.fields["destination"].queryset = dest_qs
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs})

                # Simpan quotation
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
                    return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs})

                _wiz_clear(request)
                messages.success(request, "Freight Quotation {} berhasil dibuat.".format(q.number))
                return redirect("sales:freight_view", pk=q.pk)

            messages.error(request, "Periksa isian Cargo.")
            return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs})

        # GET Step-2
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
            if "origin" in f.fields:
                f.fields["origin"].queryset = origin_qs
            if "destination" in f.fields:
                f.fields["destination"].queryset = dest_qs

        return render(request, "sales/freight/wizard_v2.html", {"step": "lines", "cargo_fs": cargo_fs})

    # fallback -> header
    wiz["step"] = "header"
    _wiz_set(request, wiz)
    form = FreightHeaderForm(initial={"transport_mode": "SEA", "service_option": "PORT_TO_PORT"})
    form.fields["service_option"].choices = service_options_for_mode("SEA")
    return render(request, "sales/freight/wizard_v2.html", {"step": "header", "form_header": form})
'''

# ----------------------------
# 3) Template wizard V2 (baru)
# ----------------------------
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
  <div class="card shadow-sm">
    <div class="card-header"><h5 class="card-title mb-0">Step 2 — Cargo Lines</h5></div>
    <div class="card-body">
      <form method="post" id="cargo-form" novalidate>
        {% csrf_token %}
        {{ cargo_fs.management_form }}
        <div class="table-responsive">
          <table class="table table-sm table-bordered align-middle" id="lines-table">
            <thead class="table-light">
              <tr>
                <th style="width:16%">Origin</th>
                <th style="width:16%">Destination</th>
                <th>Description</th>
                <th style="width:10%" class="text-end">Weight (KG)</th>
                <th style="width:10%" class="text-end">Volume (CBM)</th>
                <th style="width:12%" class="text-end">Price</th>
                <th style="width:12%" class="text-end">Amount</th>
              </tr>
            </thead>
            <tbody id="lines-body">
              {% for f in cargo_fs.forms %}
              <tr class="line-row">
                <td>{{ f.origin }}</td>
                <td>{{ f.destination }}</td>
                <td>{{ f.description }}</td>
                <td class="text-end">{{ f.weight_kg }}</td>
                <td class="text-end">{{ f.volume_cbm }}</td>
                <td class="text-end">{{ f.price }}</td>
                <td class="text-end">{{ f.amount }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
        <div class="row g-2">
          <div class="col d-flex">
            <button class="btn btn-outline-secondary" type="submit" name="action" value="back">← Back</button>
          </div>
          <div class="col d-flex justify-content-center">
            <button class="btn btn-outline-primary" type="button" id="add-line">+ Add Cargo</button>
          </div>
          <div class="col d-flex justify-content-end gap-2">
            <button class="btn btn-outline-danger" type="submit" name="action" value="cancel">Cancel</button>
            <button class="btn btn-primary" type="submit" name="action" value="save">Save</button>
          </div>
        </div>
      </form>
    </div>
  </div>

  <script type="text/template" id="empty-row-template">
    <tr class="line-row">
      <td><select name="cargo-__prefix__-origin" class="form-select form-select-sm"></select></td>
      <td><select name="cargo-__prefix__-destination" class="form-select form-select-sm"></select></td>
      <td><input type="text" name="cargo-__prefix__-description" class="form-control form-control-sm"/></td>
      <td><input type="number" step="0.001" name="cargo-__prefix__-weight_kg" class="form-control form-control-sm text-end"/></td>
      <td><input type="number" step="0.001" name="cargo-__prefix__-volume_cbm" class="form-control form-control-sm text-end"/></td>
      <td><input type="number" step="0.01"  name="cargo-__prefix__-price" class="form-control form-control-sm text-end"/></td>
      <td><input type="number" step="0.01"  name="cargo-__prefix__-amount" class="form-control form-control-sm text-end"/></td>
    </tr>
  </script>
  <script>
  (function(){
    var addBtn = document.getElementById('add-line'); if(!addBtn) return;
    var tbody  = document.getElementById('lines-body');
    var tmpl   = document.getElementById('empty-row-template').innerHTML;
    var total  = document.getElementById('id_cargo-TOTAL_FORMS');
    function nextIndex(){ return parseInt(total.value||"0",10); }
    function cloneOptions(src, dst){ dst.innerHTML = src.innerHTML; }
    addBtn.addEventListener('click', function(){
      var idx = nextIndex();
      var html = tmpl.replace(/__prefix__/g, String(idx));
      var temp = document.createElement('tbody'); temp.innerHTML = html.trim();
      var row  = temp.firstElementChild;
      var first = tbody.querySelector('tr.line-row');
      if(first){
        var s1 = first.querySelectorAll('select')[0];
        var s2 = first.querySelectorAll('select')[1];
        var d1 = row.querySelectorAll('select')[0];
        var d2 = row.querySelectorAll('select')[1];
        if(s1&&d1) cloneOptions(s1,d1);
        if(s2&&d2) cloneOptions(s2,d2);
      }
      tbody.appendChild(row);
      total.value = String(idx+1);
    });
  })();
  </script>
  {% endif %}
</div>
{% endblock %}
'''

# ----------------------------
# 4) URL route (tambahkan tanpa ganggu yang lain)
# ----------------------------
def patch_urls():
    path = "sales/urls.py"
    abspath = os.path.join(BASE, path)
    if not os.path.exists(abspath):
        print("WARNING: sales/urls.py tidak ditemukan. Tambahkan route manual.")
        return
    with io.open(abspath, "r", encoding="utf-8") as f:
        txt = f.read()

    need_import_path = "from django.urls import path" not in txt
    need_import_view = "from .wizard_v2 import freight_create_wizard_v2" not in txt
    need_append_url  = "freight_create_v2" not in txt

    if need_import_path:
        txt = "from django.urls import path\n" + txt
    if need_import_view:
        # taruh setelah import path (kalau ada), else di atas file
        txt = txt.replace("from django.urls import path",
                          "from django.urls import path\nfrom .wizard_v2 import freight_create_wizard_v2")

    if need_append_url:
        # Jika ada urlpatterns = [ ... ]
        m = re.search(r"urlpatterns\s*=\s*\[", txt)
        if m:
            insert_at = txt.rfind("]")
            if insert_at != -1 and insert_at > m.end():
                snippet = '\n    path("quotations/freight/new-v2/", freight_create_wizard_v2, name="freight_create_v2"),\n'
                txt = txt[:insert_at] + snippet + txt[insert_at:]
            else:
                # fallback: tambahkan +=
                txt += '\nurlpatterns += [path("quotations/freight/new-v2/", freight_create_wizard_v2, name="freight_create_v2")]\n'
        else:
            # fallback: buat urlpatterns baru
            txt += '\nurlpatterns = [path("quotations/freight/new-v2/", freight_create_wizard_v2, name="freight_create_v2")]\n'

    with io.open(abspath, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    print("Patched: sales/urls.py (route /sales/quotations/freight/new-v2/)")

def main():
    write("sales/helpers_freight_overlay.py", HELPERS)
    write("sales/wizard_v2.py", WIZARD_V2)
    write("templates/sales/freight/wizard_v2.html", WIZARD_TPL)
    patch_urls()
    print("\nSelesai. Jalankan server dan buka: /sales/quotations/freight/new-v2/\n"
          "Perubahan ini TIDAK mengubah views lama atau filter list.\n")

if __name__ == "__main__":
    main()
