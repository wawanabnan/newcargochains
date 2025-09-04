# repair_models_freightcargo.py
# Pastikan FreightCargo & FreightCharge ada di sales/models.py (tanpa urusan PDF).

from pathlib import Path
import re, sys

p = Path("sales/models.py")
if not p.exists():
    sys.exit("ERROR: sales/models.py tidak ditemukan.")

src = p.read_text(encoding="utf-8")
orig = src

# 0) Matikan jejak pdf property yang bikin import gagal
src = re.sub(
    r"(?ms)^[ \t]*@pdf_file\.setter[^\n]*\n^[ \t]*def[ \t]+pdf_file\([^\n]*\):\s*\n(?:(?:^[ \t]+.*\n))+",
    "",
    src,
)
src = re.sub(
    r"(?ms)^[ \t]*@property[^\n]*\n^[ \t]*def[ \t]+pdf_file\([^\n]*\):\s*\n(?:(?:^[ \t]+.*\n))+",
    "",
    src,
)

# 1) Cek FreightCargo
has_cargo = re.search(r"^\s*class\s+FreightCargo\s*\(", src, flags=re.M) is not None
# 2) Cek FreightCharge
has_charge = re.search(r"^\s*class\s+FreightCharge\s*\(", src, flags=re.M) is not None

append_blocks = []

if not has_cargo:
    append_blocks.append(
        """
class FreightCargo(models.Model):
    quotation = models.ForeignKey("sales.FreightQuotation", on_delete=models.CASCADE, related_name="cargos")

    description = models.CharField(max_length=255, blank=True)
    qty = models.PositiveIntegerField(default=1)
    weight_kg = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    volume_cbm = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    origin = models.ForeignKey("geo.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="cargo_origins")
    destination = models.ForeignKey("geo.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="cargo_destinations")

    def __str__(self):
        return self.description or f"Cargo #{self.pk}"

    class Meta:
        ordering = ('id',)
"""
    )

if not has_charge:
    append_blocks.append(
        """
class FreightCharge(models.Model):
    cargo = models.ForeignKey("sales.FreightCargo", on_delete=models.CASCADE, related_name="charges")
    description = models.CharField(max_length=255, blank=True)
    qty = models.PositiveIntegerField(default=0)
    rate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    def __str__(self):
        return self.description or f"Charge #{self.pk}"

    class Meta:
        ordering = ('id',)
"""
    )

if append_blocks:
    if not src.endswith("\n"):
        src += "\n"
    src += "\n".join(append_blocks)
    p.write_text(src, encoding="utf-8")
    print("Patched: menambahkan definisi minimal untuk:", end=" ")
    print(", ".join(["FreightCargo"] if not has_cargo else [] + ["FreightCharge"] if not has_charge else []))
else:
    # tetap tulis jika hanya membersihkan pdf_* di atas
    if src != orig:
        p.write_text(src, encoding="utf-8")
        print("Patched: membersihkan jejak pdf_* di sales/models.py (class sudah ada).")
    else:
        print("Tidak ada perubahan: FreightCargo & FreightCharge sudah ada dan tidak ada jejak pdf_*.")

print("\nSekarang bersihkan cache .pyc lalu jalankan server:")
print(r"  del /s /q *.pyc")
print(r"  for /d /r %d in (__pycache__) do @rd /s /q ""%d""")
print("  python manage.py runserver")
