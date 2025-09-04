# nuke_pdf_property_block.py
# Bersihkan seluruh definisi pdf_file (getter & setter) di FreightQuotation
# lalu pasang ulang property pdf_file (getter+setter) yang valid.

from pathlib import Path
import re, sys

P = Path("sales/models.py")
if not P.exists():
    sys.exit("ERROR: sales/models.py tidak ditemukan.")

src = P.read_text(encoding="utf-8")

# Tangkap blok class FreightQuotation, berhenti sebelum class berikutnya
m = re.search(
    r"(^class\s+FreightQuotation\s*\([^)]*\)\s*:\s*\n)(?P<body>[\s\S]*?)(?=^\s*class\s+\w|\Z)",
    src, flags=re.M
)
if not m:
    sys.exit("ERROR: Tidak menemukan class FreightQuotation di sales/models.py")

hdr = m.group(1)
body = m.group("body")

orig_body = body

# 1) Hapus SEMUA getter/setter lama yang berkaitan dengan pdf_file
#    (regex dibatasi hanya di dalam body FreightQuotation)
body = re.sub(
    r"^\s*@pdf_file\.setter\s*\n^\s*def\s+pdf_file\s*\([^\)]*\):[\s\S]*?(?=^\s*@|^\s*def\s|^\s*class\s|\Z)",
    "", body, flags=re.M
)
body = re.sub(
    r"^\s*@property\s*\n^\s*def\s+pdf_file\s*\(\s*self\s*\):[\s\S]*?(?=^\s*@|^\s*def\s|^\s*class\s|\Z)",
    "", body, flags=re.M
)

# 2) Sisipkan property baru (getter + setter) yang aman di AKHIR body class
indent = "    "
prop_block = (
    f"\n{indent}@property\n"
    f"{indent}def pdf_file(self):\n"
    f"{indent*2}# BUKAN field DB — hanya stub agar akses/pengecekan aman\n"
    f"{indent*2}return getattr(self, '_pdf_file_stub', None)\n"
    f"\n{indent}@pdf_file.setter\n"
    f"{indent}def pdf_file(self, value):\n"
    f"{indent*2}# Izinkan assign apa pun; None juga boleh\n"
    f"{indent*2}try:\n"
    f"{indent*3}setattr(self, '_pdf_file_stub', value)\n"
    f"{indent*2}except Exception:\n"
    f"{indent*3}setattr(self, '_pdf_file_stub', None)\n"
)

if not body.endswith("\n"):
    body += "\n"
body += prop_block + "\n"

# 3) Rekonstruksi file
new_src = src[:m.start("body")] + body + src[m.end("body"):]
P.write_text(new_src, encoding="utf-8")

print("OK: Semua definisi pdf_file lama dihapus & property baru dipasang di FreightQuotation.")

print("\nSekarang bersihkan cache & jalankan server:")
print(r"  del /s /q *.pyc")
print(r"  for /d /r %d in (__pycache__) do @rd /s /q ""%d""")
print("  python manage.py runserver")
