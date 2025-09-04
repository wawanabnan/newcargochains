# sales/wizard_clean.py
from datetime import date, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.forms import formset_factory
from django.contrib import messages
from django.db import transaction

from .forms import FreightHeaderForm, FreightCargoForm
from .models import FreightQuotation, FreightCargo

SESSION_KEY = "fq_wizard_clean"


# -----------------------------
# Helpers (session-safe values)
# -----------------------------
def _to_session_value(v):
    """
    Pastikan semua nilai yang disimpan ke session adalah JSON-serializable.
    - date/datetime -> ISO string
    - Decimal -> float
    - Model instance -> pk
    - Lainnya -> apa adanya
    """
    if isinstance(v, (date, datetime)):
        return v.isoformat()

    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return float(v)
    except Exception:
        pass

    if hasattr(v, "pk"):
        return v.pk

    return v


def _get_session(request):
    data = request.session.get(SESSION_KEY)
    if not data:
        data = {"step": "header", "header": {}, "lines": []}
        request.session[SESSION_KEY] = data
    return data


def _save_session(request, data):
    # Safety: jangan sampai ada tipe non-JSON
    import json
    json.dumps(data)
    request.session[SESSION_KEY] = data
    request.session.modified = True


# -----------------------------
# Utilities / sanity
# -----------------------------
def ping_wizard(request):
    return HttpResponse("PING WIZARD CLEAN")


# -----------------------------
# Main Wizard (2-step, no redirects between steps)
# -----------------------------
def freight_create_wizard_clean(request):
    data = _get_session(request)

    # Optional reset via querystring
    if request.GET.get("reset") == "1":
        data = {"step": "header", "header": {}, "lines": []}
        _save_session(request, data)

    # ----- STEP 1: HEADER -----
    if data["step"] == "header":
        if request.method == "POST":
            form = FreightHeaderForm(request.POST)
            if form.is_valid():
                # Kumpulkan header bersih untuk session (skip 'date')
                header_clean = {}
                for k, v in form.cleaned_data.items():
                    if k == "date":
                        continue  # JANGAN simpan date ke session
                    header_clean[k] = _to_session_value(v)

                # Safety: buang 'date' lama jika ada
                data.get("header", {}).pop("date", None)

                data["header"] = header_clean
                data["step"] = "lines"
                _save_session(request, data)

                # Lanjut render STEP 2 tanpa redirect
                return render(request, "sales/freight/wizard_clean.html", {
                    "step": "lines",
                    "header_form": FreightHeaderForm(initial=data["header"]),
                    "cargo_form": FreightCargoForm(prefix="left"),
                    "lines": data["lines"],
                })
            else:
                return render(request, "sales/freight/wizard_clean.html", {
                    "step": "header",
                    "header_form": form,
                    "cargo_form": None,
                    "lines": data["lines"],
                })
        else:
            form = FreightHeaderForm(initial=data.get("header"))
            return render(request, "sales/freight/wizard_clean.html", {
                "step": "header",
                "header_form": form,
                "cargo_form": None,
                "lines": data["lines"],
            })

    # ----- STEP 2: LINES -----
    # Catatan: kita pakai satu form kiri (prefix="left") bukan formset penuh, biar simpel.
    if request.method == "POST":
        action = request.POST.get("action")

        # Back -> kembali ke header
        if action == "back":
            data["step"] = "header"
            _save_session(request, data)
            return render(request, "sales/freight/wizard_clean.html", {
                "step": "header",
                "header_form": FreightHeaderForm(initial=data.get("header")),
                "cargo_form": None,
                "lines": data["lines"],
            })

        # Tambah cargo (kiri -> kanan/list)
        if action == "add_line":
            left_form = FreightCargoForm(request.POST, prefix="left")
            if left_form.is_valid():
                row = {}
                for k, v in left_form.cleaned_data.items():
                    # Simpan ke session dalam bentuk primitive
                    row[k] = _to_session_value(v)

                # Normalisasi angka spesifik (pastikan float atau int)
                for f in ("qty", "price", "weight_kg", "volume_cbm", "amount"):
                    if f in row and row[f] is not None:
                        try:
                            row[f] = float(row[f])
                        except Exception:
                            pass

                data["lines"].append(row)
                _save_session(request, data)
                messages.success(request, "Cargo ditambahkan.")

                # Reset form kiri
                return render(request, "sales/freight/wizard_clean.html", {
                    "step": "lines",
                    "header_form": FreightHeaderForm(initial=data["header"]),
                    "cargo_form": FreightCargoForm(prefix="left"),
                    "lines": data["lines"],
                })
            else:
                return render(request, "sales/freight/wizard_clean.html", {
                    "step": "lines",
                    "header_form": FreightHeaderForm(initial=data["header"]),
                    "cargo_form": left_form,
                    "lines": data["lines"],
                })

        # Hapus cargo dari panel kanan
        if action == "remove_line":
            idx = request.POST.get("idx")
            try:
                idx = int(idx)
                if 0 <= idx < len(data["lines"]):
                    data["lines"].pop(idx)
                    _save_session(request, data)
            except Exception:
                pass
            return render(request, "sales/freight/wizard_clean.html", {
                "step": "lines",
                "header_form": FreightHeaderForm(initial=data["header"]),
                "cargo_form": FreightCargoForm(prefix="left"),
                "lines": data["lines"],
            })

        # Finish -> simpan ke DB
        if action == "finish":
            if not data["lines"]:
                messages.error(request, "Tambahkan minimal 1 cargo sebelum Finish.")
                return render(request, "sales/freight/wizard_clean.html", {
                    "step": "lines",
                    "header_form": FreightHeaderForm(initial=data["header"]),
                    "cargo_form": FreightCargoForm(prefix="left"),
                    "lines": data["lines"],
                })

            # Validasi ulang header menggunakan form asli kamu
            header_form = FreightHeaderForm(data["header"])
            if not header_form.is_valid():
                messages.error(request, "Header tidak valid, periksa kembali.")
                data["step"] = "header"
                _save_session(request, data)
                return render(request, "sales/freight/wizard_clean.html", {
                    "step": "header",
                    "header_form": header_form,
                    "cargo_form": None,
                    "lines": data["lines"],
                })

            # Commit ke DB
            with transaction.atomic():
                fq = FreightQuotation.objects.create(
                    # Ambil field persis seperti di form header
                    **{f: header_form.cleaned_data.get(f) for f in header_form.fields.keys()},
                    # Set hari ini; TIDAK ambil dari session
                    date=date.today(),
                )

                # Simpan tiap cargo line
                for row in data["lines"]:
                    FreightCargo.objects.create(
                        quotation=fq,
                        origin_id=row.get("origin"),
                        destination_id=row.get("destination"),
                        description=row.get("description"),
                        qty=int(row.get("qty") or 1),
                        weight_kg=row.get("weight_kg") or None,
                        volume_cbm=row.get("volume_cbm") or None,
                        price=row.get("price") or 0,
                        amount=row.get("amount") or 0,
                    )

            # Bersihkan session
            try:
                request.session.pop(SESSION_KEY, None)
            except KeyError:
                pass

            messages.success(request, "Freight Quotation berhasil dibuat.")
            return redirect("sales:freight_view_clean", pk=fq.pk)

    # GET step lines
    return render(request, "sales/freight/wizard_clean.html", {
        "step": "lines",
        "header_form": FreightHeaderForm(initial=data["header"]),
        "cargo_form": FreightCargoForm(prefix="left"),
        "lines": data["lines"],
    })


# -----------------------------
# Simple Detail Page
# -----------------------------
def freight_detail_clean(request, pk):
    fq = get_object_or_404(FreightQuotation, pk=pk)
    lines = FreightCargo.objects.filter(quotation=fq).select_related("origin", "destination")
    return render(request, "sales/freight/detail_clean.html", {"fq": fq, "lines": lines})
