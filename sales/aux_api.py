# sales/aux_api.py
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.contrib.auth.decorators import login_required

from .location_helper import compute_location_types
from .models import Location  # asumsi model ini sudah ada

@login_required
@require_GET
def wizard_state(request):
    # Ambil dari session wizard Anda (nama key disesuaikan; di banyak wizard kita pakai 'freight_wizard')
    wiz = request.session.get("freight_wizard", {}) or {}
    header = wiz.get("header", {}) or {}
    mode = (header.get("transport_mode") or "").upper()
    service = (header.get("service_option") or "").upper()
    return JsonResponse({"mode": mode, "service": service})

@login_required
@require_GET
def location_options(request):
    """
    Querystring:
      role=origin|destination  (wajib)
      mode=SEA|AIR|LAND|TRUCK|ROAD (opsional; kalau kosong baca dari session)
      service=P2P|D2P|P2D|D2D     (opsional; kalau kosong baca dari session)
      q=keyword (opsional filter name__icontains)
    Return: { "items": ["Jakarta", "Surabaya", ...] }  -> nama saja (tanpa ID)
    """
    role = (request.GET.get("role") or "").lower()
    mode = (request.GET.get("mode") or "").upper()
    service = (request.GET.get("service") or "").upper()
    q = (request.GET.get("q") or "").strip()

    if not role in ("origin", "destination"):
        return JsonResponse({"items": []})

    # fallback: kalau mode/service kosong, baca dari session wizard
    if not (mode and service):
        wiz = request.session.get("freight_wizard", {}) or {}
        header = wiz.get("header", {}) or {}
        mode = mode or (header.get("transport_mode") or "").upper()
        service = service or (header.get("service_option") or "").upper()

    # Tentukan tipe yg dibutuhkan
    origin_t, dest_t = compute_location_types(mode, service)
    need_type = origin_t if role == "origin" else dest_t

    # Untuk moda darat, Anda dulu pakai "CITY" atau "JETTY".
    # Di sini kita ambil keduanya agar dropdown tidak kosong.
    qs = Location.objects.all()
    if need_type == "CITY":
        qs = qs.filter(type__in=["CITY", "JETTY"])
    else:
        qs = qs.filter(type=need_type)

    if q:
        qs = qs.filter(name__icontains=q)

    # Hanya nama yang dikembalikan (sesuai catatan "simpan sebagai nama location")
    names = list(qs.order_by("name").values_list("name", flat=True)[:200])  # batas atas biar ringan
    return JsonResponse({"items": names})
