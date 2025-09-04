# fix_pdf_property_models.py
# Hapus setter yatim @pdf_file.setter dan pastikan FreightQuotation punya property pdf_file (getter+setter)
from pathlib import Path
import re, sys

p = Path("sales/models.py")
if not p.exists():
    sys.exit("ERROR: sales/models.py tidak ditemukan.")

src = p.read_text(encoding="utf-8")

# Tangkap blok class FreightQuotation
m = re.search(r"(^class\s+FreightQuotation\s*\([^)]*\)\s*:\s*\n)(?P<body>[\s\S]*?)(?=^\s*class\s+\w|\Z)",
              src, flags=re.M)
if not m:
    sys.exit("ERROR: Tidak menemukan class FreightQuotation di sales/models.py")

hdr = m.group(1)
body = m.group("body")

# 1) Hapus setter yatim: @pdf_file.setter + def pdf_file(...)
body = re.sub(
    r"^\s*@pdf_file\.setter\s*\n^\s*def\s+pdf_file\s*\([^\)]*\):[\s\S]*?(?=^\s*@|^\s*def\s|\Z)",
    "", body, flags=re.M)

# 2) Hapus getter lama (kalau ada) untuk diganti versi aman
body = re.sub(
    r"^\s*@property\s*\n^\s*def\s+pdf_file\s*\(\s*self\s*\):[\s\S]*?(?=^\s*@|^\s*def\s|\Z)",
    "", body, flags=re.M)

# 3) Tambahkan property aman (getter+setter)
indent = "    "
safe_prop = (
    f"{indent}@property\n"
    f"{indent}def pdf_file(self):\n"
    f"{indent*2}# BUKAN field DB — hanya stub agar akses di template/view aman\n"
    f"{indent*2}return getattr(self, '_pdf_file_stub', None)\n\n"
    f"{indent}@pdf_file.setter\n"
    f"{indent}def pdf_file(self, value):\n"
    f"{indent*2}try:\n"
    f"{indent*3}setattr(self, '_pdf_file_stub', value)\n"
    f"{indent*2}except Exception:\n"
    f"{indent*3}setattr(self, '_pdf_file_stub', None)\n"
)

# Sisipkan di akhir body kelas
if not body.endswith("\n"):
    body += "\n"
body += "\n" + safe_prop + "\n"

# Rekonstruksi file
new_src = src[:m.start("body")] + body + src[m.end("body"):]
p.write_text(new_src, encoding="utf-8")
print("OK: pdf_file getter+setter diset ulang di FreightQuotation, setter yatim dihapus.")
