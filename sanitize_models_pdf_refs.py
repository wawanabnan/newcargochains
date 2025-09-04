# sanitize_models_pdf_refs.py
# - Buang 'pdf_generated_at' & 'pdf_file' dari update_fields apa pun.
# - Comment out baris yang mengakses/menetapkan self.pdf_file atau self.pdf_generated_at.
from pathlib import Path
import re

p = Path("sales/models.py")
src = p.read_text(encoding="utf-8")
orig = src

# 1) Hilangkan 'pdf_generated_at' dan 'pdf_file' dari update_fields
#    (kalau kosong, ubah jadi save() biasa)
def strip_update_fields(text: str) -> str:
    # kasus langsung keduanya -> jadi save()
    text = re.sub(
        r"\.save\(\s*update_fields\s*=\s*\[(?:\s*['\"]pdf_generated_at['\"]\s*,\s*['\"]pdf_file['\"]\s*|"
        r"\s*['\"]pdf_file['\"]\s*,\s*['\"]pdf_generated_at['\"]\s*)\]\s*\)",
        ".save()",
        text,
    )
    text = re.sub(
        r"\.save\(\s*update_fields\s*=\s*\((?:\s*['\"]pdf_generated_at['\"]\s*,\s*['\"]pdf_file['\"]\s*|"
        r"\s*['\"]pdf_file['\"]\s*,\s*['\"]pdf_generated_at['\"]\s*)\)\s*\)",
        ".save()",
        text,
    )
    # hapus satu-satu di list/tuple
    text = re.sub(r'[,\s]*["\']pdf_generated_at["\']', "", text)
    text = re.sub(r'[,\s]*["\']pdf_file["\']', "", text)
    # rapikan list/tuple kosong → save() biasa
    text = re.sub(r"\.save\(\s*update_fields\s*=\s*\[\s*\]\s*\)", ".save()", text)
    text = re.sub(r"\.save\(\s*update_fields\s*=\s*\(\s*\)\s*\)", ".save()", text)
    # rapikan koma gantung
    text = re.sub(r"\[\s*,", "[", text)
    text = re.sub(r",\s*\]", "]", text)
    text = re.sub(r"\(\s*,", "(", text)
    text = re.sub(r",\s*\)", ")", text)
    return text

src = strip_update_fields(src)

# 2) Comment out semua baris yang menyentuh pdf_file / pdf_generated_at
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

# 3) (Opsional) Hapus property pdf_file shim lama yang mungkin pernah ditambahkan
src = re.sub(
    r"\n\s*@property\s+def\s+pdf_file\(self\):[\s\S]*?\n\s*(?=@|class|\Z)",
    "\n",
    src,
    flags=re.M,
)

if src != orig:
    p.write_text(src, encoding="utf-8")
    print("Done: sales/models.py dibersihkan dari referensi PDF bermasalah.")
else:
    print("Info: sales/models.py sudah bersih, tidak ada perubahan.")
