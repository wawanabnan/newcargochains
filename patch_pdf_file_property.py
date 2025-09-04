# patch_pdf_file_property.py
# Bersihkan setter yatim @pdf_file.setter dan pasang property pdf_file (getter+setter) yang aman
from pathlib import Path
import re, sys

P = Path("sales/models.py")
if not P.exists():
    sys.exit("ERROR: sales/models.py tidak ditemukan.")

src = P.read_text(encoding="utf-8")

# Tangkap blok class FreightQuotation
m = re.search(
    r"(^class\s+FreightQuotation\s*\([^)]*\)\s*:\s*\n)(?P<body>[\s\S]*?)(?=^\s*class\s+\w|\Z)",
    src, flags=re.M
)
if not m:
    sys.exit("ERROR: Tidak menemukan class FreightQuotation di sales/models.py")

hdr = m.group(1)
body = m.group("body")

# 1) Hapus semua definisi lama yang berkaitan dengan pdf_file (getter & setter)
#    - @property ... def pdf_file(self): ...
#    - @pdf_file.setter ... def pdf_file(self, ...): ...
body = re.sub(
    r"^\s*@pdf_file\.setter\s*\n^\s*def\s+pdf_file\s*\([^\)]*\):[\s\S]*?(?=^\s*@|^\s*def\s|\Z)",
    "", body, flags=re.M
)
body = re.sub(
    r"^\s*@property\s*\n^\s*def\s+pdf_file\s*\(\s*self\s*\):[\s\S]*?(?=^\s*@|^\s*def\s|\Z)",
    "", body, flags=re.M
)

# 2) Tambahkan property baru (getter + setter) yang sederhana & aman
indent = "    "
prop_block = (
    f"\n{indent}@property\n"
    f"{indent}def pdf_file(self):\n"
    f"{indent*2}# BUKAN field DB — hanya stub agar akses/pengecekan aman\n"
    f"{indent*2}return getattr(self, '_pdf_file_stub', None)\n"
    f"\n{indent}@pdf_file.setter\n"
    f"{indent}def pdf_file(self, value):\n"
    f"{indent*2}# izinkan assign apa pun; None juga boleh\n"
    f"{indent*2}try:\n"
    f"{indent*3}setattr(self, '_pdf_file_stub', value)\n"
    f"{indent*2}except Exception:\n"
    f"{indent*3}setattr(self, '_pdf_file_stub', None)\n"
)

if not body.endswith("\n"):
    body += "\n"
body = body + prop_block + "\n"

# 3) Tulis kembali file
new_src = src[:m.start("body")] + body + src[m.end("body"):]
P.write_text(new_src, encoding="utf-8")
print("OK: pdf_file getter+setter disetel ulang di FreightQuotation; definisi lama dihapus.")
print("Sekarang bersihkan cache .pyc lalu jalankan server:")
print(r"  del /s /q *.pyc")
print(r"  for /d /r %d in (__pycache__) do @rd /s /q ""%d""")
print("  python manage.py runserver")
