# sales/aux_api.py
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.apps import apps

# Import model dari app sales (pastikan model-model ini ada)
from .models import ModeService, LocationRule

WZ_SESSION_KEY = "fq_wizard"

def _resolve_location_model_and_type_field():
    """
    Prefer geo.Location; fallback ke sales.Location.
    Deteksi field tipe: 'loc_type' atau 'type'.
    """
    Location = apps.get_model("geo", "Location") or apps.get_model("sales", "Location")
    if Location is None:
        raise RuntimeError("Model Location tidak ditemukan (geo.Location atau sales.Location).")
    field_names = {f.name for f in Location._meta.fields}
    type_field = "loc_type" if "loc_type" in field_names else ("type" if "type" in field_names else None)
    if not type_field:
        raise RuntimeError("Field tipe lokasi tidak ditemukan (harus 'loc_type' atau 'type').")
    return Location, type_field

def _choices(qs):
    return [{"id": x.pk, "text": getattr(x, "name", str(x))} for x in qs]

@require_GET
def wizard_state(request):
    """
    Kembalikan status wizard dari session + daftar service options (jika mode ada)
    + rule origin/destination (jika mode+service ada).
    """
    state = request.session.get(WZ_SESSION_KEY) or {}
    step = "header" if not state else "lines"
    resp = {"ok": True, "step": step, "state": state}

    mode = state.get("transport_mode")
    service = state.get("service_option")

    if mode:
        opts = (ModeService.objects
                .filter(mode__code=mode)
                .select_related("service")
                .order_by("service__name"))
        resp["service_options"] = [{"id": ms.service.code, "text": ms.service.name} for ms in opts]

    if mode and service:
        try:
            rule = LocationRule.objects.only("origin_type", "destination_type").get(
                mode__code=mode, service__code=service
            )
            resp["origin_type"] = rule.origin_type
            resp["destination_type"] = rule.destination_type
        except LocationRule.DoesNotExist:
            resp["origin_type"] = None
            resp["destination_type"] = None

    return JsonResponse(resp)

@require_GET
def location_options(request):
    """
    /sales/quotations/freight/api/locations/?mode=SEA&service=D2P&side=origin|destination
    - Jika side=origin       -> {"items":[...origin...]}
    - Jika side=destination  -> {"items":[...destination...]}
    - Jika tanpa side        -> {"ok":true,"origin_type":"CITY","destination_type":"SEAPORT",
                                 "items_origin":[...],"items_destination":[...]}
    """
    mode = request.GET.get("mode")
    service = request.GET.get("service")
    side = (request.GET.get("side") or "").lower().strip()

    if not mode or not service:
        return JsonResponse({"ok": False, "message": "mode & service wajib diisi", "items": []}, status=400)

    try:
        rule = LocationRule.objects.only("origin_type", "destination_type").get(
            mode__code=mode, service__code=service
        )
    except LocationRule.DoesNotExist:
        return JsonResponse({"ok": False, "message": "Rule belum tersedia", "items": []}, status=404)

    origin_type, destination_type = rule.origin_type, rule.destination_type
    Location, type_field = _resolve_location_model_and_type_field()

    origins_qs = Location.objects.filter(**{type_field: origin_type}).order_by("name")
    dests_qs   = Location.objects.filter(**{type_field: destination_type}).order_by("name")

    if side in ("origin", "destination"):
        qs = origins_qs if side == "origin" else dests_qs
        return JsonResponse({"items": _choices(qs)})

    return JsonResponse({
        "ok": True,
        "origin_type": origin_type,
        "destination_type": destination_type,
        "items_origin": _choices(origins_qs),
        "items_destination": _choices(dests_qs),
    })
