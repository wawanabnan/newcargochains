# ensure_freightorder_models.py
# Menambahkan definisi minimal FreightOrder & FreightOrderLine kalau belum ada,
# supaya import from .models tidak gagal.

from pathlib import Path
import re, sys

p = Path("sales/models.py")
if not p.exists():
    sys.exit("ERROR: sales/models.py tidak ditemukan.")

src = p.read_text(encoding="utf-8")
orig = src

# Pastikan import models ada
if "from django.db import models" not in src:
    src = "from django.db import models\n" + src

# Hapus sisa dekorator pdf yang bisa menghambat import
src = re.sub(
    r"(?ms)^[ \t]*@pdf_file\.setter[^\n]*\n^[ \t]*def[ \t]+pdf_file\([^\n]*\):\s*\n(?:(?:^[ \t]+.*\n))+",
    "", src)
src = re.sub(
    r"(?ms)^[ \t]*@property[^\n]*\n^[ \t]*def[ \t]+pdf_file\([^\n]*\):\s*\n(?:(?:^[ \t]+.*\n))+",
    "", src)

# Cek apakah FreightOrder & FreightOrderLine sudah ada
has_order = re.search(r"^\s*class\s+FreightOrder\s*\(", src, flags=re.M) is not None
has_line  = re.search(r"^\s*class\s+FreightOrderLine\s*\(", src, flags=re.M) is not None

append_blocks = []

if not has_order:
    append_blocks.append("""
class FreightOrder(models.Model):
    quotation = models.ForeignKey("sales.FreightQuotation", on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    number = models.CharField(max_length=50, blank=True, default="")
    date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")

    def __str__(self):
        return self.number or f"Order #{self.pk}"

    class Meta:
        ordering = ('id',)
""")

if not has_line:
    append_blocks.append("""
class FreightOrderLine(models.Model):
    order = models.ForeignKey("sales.FreightOrder", on_delete=models.CASCADE, related_name="lines")
    cargo = models.ForeignKey("sales.FreightCargo", on_delete=models.SET_NULL, null=True, blank=True, related_name="order_lines")

    description = models.CharField(max_length=255, blank=True, default="")
    qty = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    origin = models.ForeignKey("geo.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="fo_origins")
    destination = models.ForeignKey("geo.Location", on_delete=models.PROTECT, null=True, blank=True, related_name="fo_destinations")

    def __str__(self):
        return self.description or f"OrderLine #{self.pk}"

    class Meta:
        ordering = ('id',)
""")

if append_blocks:
    if not src.endswith("\n"):
        src += "\n"
    src += "\n".join(append_blocks)
    p.write_text(src, encoding="utf-8")
    print("Patched: menambahkan definisi minimal untuk:",
          "FreightOrder " if not has_order else "",
          "FreightOrderLine" if not has_line else "")
else:
    # tetap simpan kalau hanya membersihkan dekorator pdf
    if src != orig:
        p.write_text(src, encoding="utf-8")
        print("Patched: membersihkan sisa dekorator pdf di sales/models.py.")
    else:
        print("Tidak ada perubahan: FreightOrder & FreightOrderLine sudah ada.")

print("\nSekarang bersihkan cache .pyc dan jalankan server:")
print(r"  del /s /q *.pyc")
print(r"  for /d /r %d in (__pycache__) do @rd /s /q ""%d""")
print("  python manage.py check")
print("  python manage.py runserver")
