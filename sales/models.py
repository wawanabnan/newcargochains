from django.db import models
from django.conf import settings
from geo.models import Location
from partners.models import Partner
from settings.models import Setting  
from django.db import models, IntegrityError, transaction
from django.utils import timezone
from decimal import Decimal


class FreightQuotation(models.Model):
    BUSINESS_TYPE = "FREIGHT"

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SENT", "Sent"),
        ("CONFIRMED", "Confirmed"),
        ("CLOSED", "Closed"),
        ("CANCELLED", "Cancelled"),
    ]

    TRANSPORT_CHOICES = [
        ("SEA", "Sea"),
        ("AIR", "Air"),
        ("LAND", "Land"),
    ]

    SERVICE_CHOICES = [
        ("DOOR_TO_DOOR", "Door to door"),
        ("DOOR_TO_PORT", "Door to port"),
        ("PORT_TO_PORT", "Port to port"),
        ("DOOR_TO_AIRPORT", "Door to airport"),
        ("AIRPORT_TO_AIRPORT", "Airport to airport"),
        ("TRUCKING", "Trucking"),
    ]
   

    number = models.CharField(max_length=50, unique=True, blank=True)
    date = models.DateField()
    # TODO: Ganti ke model Customer/Partner Anda jika ada (mis. partners.Partner)
    customer = models.ForeignKey(Partner, on_delete=models.PROTECT)
    currency = models.CharField(max_length=10, default="IDR")
    transport_mode = models.CharField(max_length=20, choices=TRANSPORT_CHOICES)
    service_option = models.CharField(max_length=50, choices=SERVICE_CHOICES)
    notes = models.TextField(blank=True)

    # single-destination: isi di header; multi: kosong & isi per cargo
    multi_destination = models.BooleanField(default=False)
    payment_term = models.CharField(max_length=50, blank=True)

    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    vat = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="DRAFT")  # << NEW


    created_at = models.DateTimeField(default=timezone.now)  # ganti auto_now_add
    updated_at = models.DateTimeField(default=timezone.now)  # ganti auto_now
    
    def save(self, *args, **kwargs):
        # Saat create dan number kosong -> generate
        if not self.pk and not getattr(self, "number", None):
            # retry 3x kalau bentrok UNIQUE
            for _ in range(3):
                self.number = _generate_next_number(self.__class__)
                try:
                    with transaction.atomic():
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    # kemungkinan ada create paralel, coba ulang nomor
                    self.number = None
                    continue
            # kalau masih bentrok, biarkan IntegrityError dari save terakhir
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.number or f"FQ-{self.pk or ''}"
        
    class Meta:
        ordering = ("-date", "-id")

    #def mark_pdf_stale(self, *, save=True):
    #    self.pdf_generated_at = None
    #    if self.pdf_file:
    #        self.pdf_file.delete(save=False)
    #        self.pdf_file = None
    #    if save:
    #        self.save(update_fields=["pdf_generated_at", "pdf_file"])


class FreightCargo(models.Model):
    quotation = models.ForeignKey("sales.FreightQuotation", on_delete=models.CASCADE, related_name="cargos")

    description = models.CharField(max_length=255)
    qty = models.PositiveIntegerField(default=1)
    weight_kg = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    volume_cbm = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    # sekarang pakai master geo.Location
    origin = models.ForeignKey(
        "geo.Location", on_delete=models.PROTECT, null=True, 
        blank=True, related_name="cargo_origins")
        
    destination = models.ForeignKey("geo.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="cargo_destinations")

    def __str__(self):
        return self.description

class FreightCharge(models.Model):
    cargo = models.ForeignKey(FreightCargo, on_delete=models.CASCADE, related_name="charges")
    description = models.CharField(max_length=255, blank=True)
    qty = models.PositiveIntegerField(default=0)
    rate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    def __str__(self):
        return self.description or f"Charge-{self.pk}"

def get_app_setting(key, default=None):
    from settings.models import Setting  # app settings Anda
    try:
        row = Setting.objects.filter(key=key).only("value").first()
        return row.value if row and row.value not in ("", None) else default
    except Exception:
        return default

def _get_fmt(biz: str) -> str:
    # Prioritas: tipe-spesifik -> generic -> default
    fmt = get_app_setting(f"QUO_FORMAT_{biz}", None)
    if fmt: return fmt
    fmt = get_app_setting("QUO_FORMAT", None)
    return fmt or "QFR-%m%y-%04d"

def _get_scope(biz: str) -> str:
    scope = get_app_setting(f"QUO_SCOPE_{biz}", None)
    if scope: return scope.upper()
    scope = get_app_setting("QUO_SCOPE", "FMT")
    return (scope or "FMT").upper()

def _visible_prefix_from_format(fmt: str, today):
    if "%0" not in fmt or "d" not in fmt.split("%0")[-1]:
        fmt = fmt.rstrip("-") + "-%04d"
    return today.strftime(fmt.split("%0")[0])

# sebelum: def _generate_next_number(model_cls, biz: str) -> str:
def _generate_next_number(model_cls, biz: str | None = None) -> str:
    """
    Bangun nomor berdasar format. Reset per prefix (biasanya per bulan).
    biz opsional: jika None, ambil dari model_cls.BUSINESS_TYPE atau 'FREIGHT'
    """
    if biz is None:
        biz = getattr(model_cls, "BUSINESS_TYPE", "FREIGHT")
    biz = (biz or "FREIGHT").upper()

    from django.utils import timezone
    today = timezone.localdate()

    # --- ambil format & scope per bisnis type ---
    fmt   = _get_fmt(biz)      # gunakan helper per-type: QUO_FORMAT_<BIZ> → QUO_FORMAT → default
    scope = _get_scope(biz)    # QUO_SCOPE_<BIZ> → QUO_SCOPE → 'FMT'

    # pastikan ada placeholder sequence
    if "%0" not in fmt or "d" not in fmt.split("%0")[-1]:
        fmt = fmt.rstrip("-") + "-%04d"

    # prefix tampilan (sesuai format)
    visible_prefix = _visible_prefix_from_format(fmt, today)
    # pencarian reset (MONTH/YEAR/ GLOBAL / FMT) — praktik terbaik: selaraskan format dg scope
    search_prefix = visible_prefix

    last = (model_cls.objects
            .filter(number__startswith=search_prefix)
            .order_by("number")
            .last())
    if last:
        try:
            last_seq = int(last.number.replace(search_prefix, ""))
        except Exception:
            last_seq = 0
        next_seq = last_seq + 1
    else:
        next_seq = 1

    # width padding dari token %0Xd
    token = fmt.split("%0")[-1] if "%0" in fmt else "4d"
    try:
        width = int(token[:-1])
    except Exception:
        width = 4

    return f"{visible_prefix}{next_seq:0{width}d}"


# === Helpers khusus Sales Order (SO) ===

def _get_so_fmt(biz: str) -> str:
    """
    Ambil format nomor untuk Sales Order.
    Urutan prioritas:
      - SO_FORMAT_<BIZ>
      - SO_FORMAT
      - default "SO-%m%y-%04d"
    Contoh format: "SO-%Y%m-%05d", "SO-%m%y-%04d", dsb.
    """
    fmt = get_app_setting(f"SO_FORMAT_{biz}", None)
    if fmt:
        return fmt
    fmt = get_app_setting("SO_FORMAT", None)
    return fmt or "SO-%m%y-%04d"


def _get_so_scope(biz: str) -> str:
    """
    (Disiapkan kalau kamu ingin scope berbeda seperti MONTH/YEAR/FMT/…)
    Saat ini kita tidak pakai 'scope' khusus selain mengikuti prefix dari format,
    tetapi disediakan untuk konsistensi dengan quotation.
    """
    scope = get_app_setting(f"SO_SCOPE_{biz}", None)
    if scope:
        return scope.upper()
    scope = get_app_setting("SO_SCOPE", "FMT")
    return (scope or "FMT").upper()


def _generate_next_so_number(model_cls, biz: str | None = None) -> str:
    """
    Generator nomor Sales Order.
    Reset sequence-nya mengikuti perubahan prefix (yang dibentuk oleh format).
    """
    if biz is None:
        biz = getattr(model_cls, "BUSINESS_TYPE", "FREIGHT")
    biz = (biz or "FREIGHT").upper()

    from django.utils import timezone
    today = timezone.localdate()

    fmt   = _get_so_fmt(biz)
    _ = _get_so_scope(biz)  # disiapkan kalau nanti dipakai

    # pastikan ada placeholder sequence %0Xd
    if "%0" not in fmt or "d" not in fmt.split("%0")[-1]:
        fmt = fmt.rstrip("-") + "-%04d"

    # prefix tampilan dari format; ini yang dipakai untuk cari last sequence
    visible_prefix = _visible_prefix_from_format(fmt, today)
    search_prefix = visible_prefix

    last = (model_cls.objects
            .filter(number__startswith=search_prefix)
            .order_by("number")
            .last())
    if last:
        try:
            last_seq = int(last.number.replace(search_prefix, ""))
        except Exception:
            last_seq = 0
        next_seq = last_seq + 1
    else:
        next_seq = 1

    # ambil width dari token %0Xd
    token = fmt.split("%0")[-1] if "%0" in fmt else "4d"
    try:
        width = int(token[:-1])
    except Exception:
        width = 4

    return f"{visible_prefix}{next_seq:0{width}d}"












#Sales Order Area
# === Sales Order (header + lines) ===
from django.conf import settings

class FreightOrder(models.Model):
    BUSINESS_TYPE = "ORDER"

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("CONFIRMED", "Confirmed"),
        ("IN_PROGRESS", "In Progress"),
        ("DONE", "Done"),
        ("CANCELLED", "Cancelled"),
    ]

    number = models.CharField(max_length=50, unique=True, blank=True)
    date = models.DateField(default=timezone.localdate)

    customer = models.ForeignKey(Partner, on_delete=models.PROTECT)
    currency = models.CharField(max_length=10, default="IDR")

    # selaraskan pilihan dengan FreightQuotation
    transport_mode = models.CharField(max_length=20, choices=FreightQuotation.TRANSPORT_CHOICES)
    service_option = models.CharField(max_length=50, choices=FreightQuotation.SERVICE_CHOICES)

    payment_term = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")

    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    vat = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    # 1 SQ : 1 SO (OneToOne)
    quotation = models.OneToOneField(
        FreightQuotation, on_delete=models.PROTECT, related_name="order"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "freight_order"
        ordering = ("-date", "-id")

    def save(self, *args, **kwargs):
        # generate number saat create
        if not self.pk and not getattr(self, "number", None):
            for _ in range(3):
                self.number = _generate_next_so_number(self.__class__, getattr(self, "BUSINESS_TYPE", "FREIGHT"))
            
                try:
                    with transaction.atomic():
                        return super().save(*args, **kwargs)
                except IntegrityError:
                    self.number = None
                    continue
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.number or f"SO-{self.pk or ''}"


class FreightOrderLine(models.Model):
    order = models.ForeignKey(FreightOrder, on_delete=models.CASCADE, related_name="lines")

    description = models.CharField(max_length=255)
    qty = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    weight_kg = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    volume_cbm = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)

    origin = models.ForeignKey(
        Location, on_delete=models.PROTECT, null=True, blank=True, related_name="order_cargo_origins"
    )
    destination = models.ForeignKey(
        Location, on_delete=models.PROTECT, null=True, blank=True, related_name="order_cargo_destinations"
    )

    class Meta:
        db_table = "freight_order_line"
        ordering = ("id",)

    def __str__(self):
        return f"{self.description} ({self.qty} x {self.price})"
    