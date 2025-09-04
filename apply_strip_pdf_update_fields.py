# apply_strip_pdf_update_fields.py
# Hapus 'pdf_generated_at' & 'pdf_file' dari update_fields di sales/models.py
from pathlib import Path
import re

p = Path("sales/models.py")
if not p.exists():
    raise SystemExit("sales/models.py tidak ditemukan.")

src = p.read_text(encoding="utf-8")

before = src

# 1) Hilangkan 'pdf_generated_at' & 'pdf_file' dari list/tuple update_fields
#    Tangani berbagai variasi spasi & urutan.
patterns_remove = [
    r'\s*,\s*"pdf_generated_at"\s*', r'\s*"pdf_generated_at"\s*,\s*',
    r'\s*,\s*\'pdf_generated_at\'\s*', r'\s*\'pdf_generated_at\'\s*,\s*',
    r'\s*,\s*"pdf_file"\s*', r'\s*"pdf_file"\s*,\s*',
    r'\s*,\s*\'pdf_file\'\s*', r'\s*\'pdf_file\'\s*,\s*',
]
for pat in patterns_remove:
    src = re.sub(pat, ',', src)

# Bersihkan koma dobel atau koma di tepi bracket/paren
src = re.sub(r'\[\s*,\s*\]', '[]', src)  # list kosong
src = re.sub(r'\(\s*,\s*\)', '()', src)  # tuple kosong
src = re.sub(r'\[\s*,', '[', src)
src = re.sub(r',\s*\]', ']', src)
src = re.sub(r'\(\s*,', '(', src)
src = re.sub(r',\s*\)', ')', src)

# 2) Jika tersisa update_fields=[] atau update_fields=(), ubah jadi save() biasa
src = re.sub(r'\.save\(\s*update_fields\s*=\s*\[\s*\]\s*\)', '.save()', src)
src = re.sub(r'\.save\(\s*update_fields\s*=\s*\(\s*\)\s*\)', '.save()', src)

# 3) Tangani pola spesifik yang langsung menyebut kedua field dalam satu list/tuple
src = re.sub(
    r'\.save\(\s*update_fields\s*=\s*\[(?:\s*[\'"]pdf_generated_at[\'"]\s*,\s*[\'"]pdf_file[\'"]\s*|'
    r'\s*[\'"]pdf_file[\'"]\s*,\s*[\'"]pdf_generated_at[\'"]\s*)\]\s*\)',
    '.save()',
    src
)
src = re.sub(
    r'\.save\(\s*update_fields\s*=\s*\((?:\s*[\'"]pdf_generated_at[\'"]\s*,\s*[\'"]pdf_file[\'"]\s*|'
    r'\s*[\'"]pdf_file[\'"]\s*,\s*[\'"]pdf_generated_at[\'"]\s*)\)\s*\)',
    '.save()',
    src
)

if src != before:
    p.write_text(src, encoding="utf-8")
    print("Patched sales/models.py: update_fields untuk pdf_* dibersihkan.")
else:
    print("Tidak ada perubahan pada sales/models.py (mungkin sudah bersih).")

print("\nSELESAI. Bersihkan cache dan restart server:")
print(r"  del /s /q *.pyc")
print(r"  for /d /r %d in (__pycache__) do @rd /s /q ""%d""")
print("Lalu:")
print("  python manage.py runserver")
print("Tes lagi: /sales/quotations/freight/new-v2/?reset=1")
