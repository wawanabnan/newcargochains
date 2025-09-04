# nuke_pdf_artifacts.py
# Hapus setter/getter pdf_file yang bikin NameError, komentari referensi pdf*, dan bersihkan update_fields.

from pathlib import Path
import re, sys

p = Path("sales/models.py")
if not p.exists():
    sys.exit("ERROR: sales/models.py tidak ditemukan.")

src = p.read_text(encoding="utf-8")
orig = src

# 1) Hapus blok @pdf_file.setter ... def pdf_file(...)
src = re.sub(
    r"(?ms)^[ \t]*@pdf_file\.setter[^\n]*\n^[ \t]*def[ \t]+pdf_file\([^\n]*\):\s*\n(?:(?:^[ \t]+.*\n))+",
    "",
    src,
)

# 2) Hapus blok @property ... def pdf_file(self): ...
src = re.sub(
    r"(?ms)^[ \t]*@property[^\n]*\n^[ \t]*def[ \t]+pdf_file\([^\n]*\):\s*\n(?:(?:^[ \t]+.*\n))+",
    "",
    src,
)

# 3) Komentari semua referensi ke self.pdf_file / self.pdf_generated_at (biar gak meledak)
lines = src.splitlines(True)
out = []
for ln in lines:
    if re.search(r"\bself\.pdf_file\b", ln) or re.search(r"\bself\.pdf_generated_at\b", ln):
        if not ln.lstrip().startswith("#"):
            out.append("# (disabled) " + ln)
        else:
            out.append(ln)
    else:
        out.append(ln)
src = "".join(out)

# 4) Bersihkan update_fields yang menyebut pdf_file / pdf_generated_at
#    - kasus khusus berdua langsung: jadikan save() biasa
src = re.sub(
    r"\.save\(\s*update_fields\s*=\s*\[(?:\s*['\"]pdf_generated_at['\"]\s*,\s*['\"]pdf_file['\"]|\s*['\"]pdf_file['\"]\s*,\s*['\"]pdf_generated_at['\"])\s*\]\s*\)",
    ".save()",
    src,
)
src = re.sub(
    r"\.save\(\s*update_fields\s*=\s*\((?:\s*['\"]pdf_generated_at['\"]\s*,\s*['\"]pdf_file['\"]|\s*['\"]pdf_file['\"]\s*,\s*['\"]pdf_generated_at['\"])\s*\)\s*\)",
    ".save()",
    src,
)
#    - hapus satu2 di list/tuple
src = re.sub(r"[,\s]*['\"]pdf_generated_at['\"]", "", src)
src = re.sub(r"[,\s]*['\"]pdf_file['\"]", "", src)
#    - rapikan list/tuple kosong → save() biasa
src = re.sub(r"\.save\(\s*update_fields\s*=\s*\[\s*\]\s*\)", ".save()", src)
src = re.sub(r"\.save\(\s*update_fields\s*=\s*\(\s*\)\s*\)", ".save()", src)
#    - rapikan koma gantung
src = re.sub(r"\[\s*,", "[", src)
src = re.sub(r",\s*\]", "]", src)
src = re.sub(r"\(\s*,", "(", src)
src = re.sub(r",\s*\)", ")", src)

if src != orig:
    p.write_text(src, encoding="utf-8")
    print("OK: pdf_file/pdf_generated_at dibersihkan dari sales/models.py")
else:
    print("Info: Tidak ada perubahan—mungkin sudah dibersihkan sebelumnya.")

print("\nSekarang bersihkan cache .pyc lalu jalankan server:")
print(r"  del /s /q *.pyc")
print(r"  for /d /r %d in (__pycache__) do @rd /s /q ""%d""")
print("  python manage.py check")
print("  python manage.py runserver")
