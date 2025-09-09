# sales/context_processors.py
from django.conf import settings

def quotation_settings(request):
    """
    Inject QUO_VALID_DAYS agar bisa dipakai di template (window.__QUO_VALID_DAYS__)
    """
    val = getattr(settings, "QUO_VALID_DAYS", 7)
    try:
        from core.models import Setting  # SESUAIKAN kalau model Setting beda lokasi
        s = Setting.objects.filter(key="QUO_VALID_DAYS").values_list("value", flat=True).first()
        if s is not None:
            val = int(s)
    except Exception:
        pass
    return {"QUO_VALID_DAYS": val}
