# sales/utils_quo.py
from __future__ import annotations
import re
from typing import Tuple
from django.core.cache import cache
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

# === MODEL SETTING ===
# Asumsi field-nya: Setting(key: CharField, value: Text/CharField)
from sales.models import Setting

def _get_setting(key: str, default=None):
    ck = f"setting:{key}"
    cached = cache.get(ck)
    if cached is not None:
        return cached
    row = Setting.objects.filter(key=key).only("value").first()
    val = row.value if row else default
    cache.set(ck, val, 300)  # cache 5 menit
    return val

def _get_str(key: str, default: str) -> str:
    v = _get_setting(key, default)
    return str(v) if v is not None else default

def _get_int(key: str, default: int) -> int:
    v = _get_setting(key, default)
    try:
        return int(v)
    except Exception:
        return default

# === Parser format nomor ===
# Contoh format: FRQ-%m%y-%4d
# %Y = 2025, %y = 25, %m = 09, %Nd = urutan dengan padding N
_SEQ_RE = re.compile(r"%(\d+)d")

def _render_head_and_padding(fmt: str, today) -> Tuple[str, int]:
    head = fmt.replace("%Y", f"{today:%Y}") \
              .replace("%y", f"{today:%y}") \
              .replace("%m", f"{today:%m}")
    m = _SEQ_RE.search(head)
    pad = 4
    if m:
        pad = int(m.group(1))
        head = head[:m.start()] + head[m.end():]
    head = re.sub(r"-{2,}", "-", head).strip("-")
    if not head.endswith("-"):
        head += "-"
    return head, pad

# === Generator nomor fleksibel per “jenis bisnis” ===
def generate_quotation_number(model_cls, kind: str) -> str:
    """
    model_cls: model Django yang punya field 'number'
    kind: mis. 'FREIGHT' → baca QUO_FORMAT_FREIGHT, QUO_RESET_FREIGHT
    Reset diarahkan oleh 'head' (prefix waktu) dari format.
    """
    today = timezone.localdate()
    fmt   = _get_str(f"QUO_FORMAT_{kind}", "FRQ-%Y%m-%4d")
    # QUO_RESET_* disediakan untuk dokumentasi/guard, tapi implementasi resetnya
    # efektif karena prefix head menyertakan %m atau %Y. Tetap kita baca kalau dibutuhkan.
    _reset = _get_str(f"QUO_RESET_{kind}", "MONTH").upper()

    head, pad = _render_head_and_padding(fmt, today)

    from django.db.models.functions import Length  # optional, aman untuk DB yang tidak suka MAX textual
    with transaction.atomic():
        # Kunci dengan select_for_update agar aman concurrency
        last = (model_cls.objects
                .select_for_update()
                .filter(number__startswith=head)
                .aggregate(mx=Max("number"))
                .get("mx"))
        if last and last.startswith(head):
            tail = last[len(head):]
            try:
                seq = int(tail) + 1
            except Exception:
                seq = 1
        else:
            seq = 1
        return f"{head}{seq:0{pad}d}"

def get_default_valid_days(kind: str = "FREIGHT") -> int:
    # kalau ingin per jenis: QUO_VALID_DAYS_FREIGHT, dsb.
    return _get_int("QUO_VALID_DAYS", 7)
