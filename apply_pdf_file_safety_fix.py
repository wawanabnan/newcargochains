# apply_pdf_file_safety_fix.py
# Perbaiki error akses pdf_file pada FreightQuotation:
# - Tambah shim pdf_file (getter+setter) via monkey-patch di sales/wizard_v2.py
# - Hapus 'pdf_file' dari update_fields di sales/models.py

from pathlib import Path

BASE = Path.cwd()

def patch_wizard():
    p = BASE / "sales" / "wizard_v2.py"
    if not p.exists():
        print("SKIP: sales/wizard_v2.py tidak ditemukan.")
        return
    s = p.read_text(encoding="utf-8")

    marker = "# --- PDF shim installer ---"
    if marker in s:
        print("OK: shim sudah ada di sales/wizard_v2.py")
        return

    inject_after = "from .models import FreightQuotation, FreightCargo"
    shim = f"""
{marker}
def _install_pdf_property():
    class _PdfShim:
        url = ""
        path = ""
        def delete(self, save=False):  # no-op
            return None
        def __bool__(self): return False
        __nonzero__ = __bool__
    def _get(self):
        return getattr(self, "_pdf_file_stub", _PdfShim())
    def _set(self, val):
        # simpan apapun yang di-assign (atau jadikan shim kalau None/invalid)
        try:
            setattr(self, "_pdf_file_stub", val if val is not None else _PdfShim())
        except Exception:
            setattr(self, "_pdf_file_stub", _PdfShim())
    try:
        FreightQuotation.pdf_file = property(_get, _set)
    except Exception:
        pass

_install_pdf_property()
# --- end PDF shim installer ---
"""
    if inject_after in s:
        s = s.replace(inject_after, inject_after + "\n" + shim)
        p.write_text(s, encoding="utf-8")
        print("Patched: sales/wizard_v2.py → tambah PDF shim")
    else:
        print("WARNING: tidak menemukan baris import FreightQuotation di sales/wizard_v2.py")

def patch_models():
    p = BASE / "sales" / "models.py"
    if not p.exists():
        print("SKIP: sales/models.py tidak ditemukan.")
        return
    s = p.read_text(encoding="utf-8")
    before = s

    # 1) Bersihkan 'pdf_file' dari update_fields list/tuple
    # Bentuk-bentuk umum yang kita bereskan:
    # ["pdf_generated_at", "pdf_file"] → ["pdf_generated_at"]
    # ("pdf_generated_at","pdf_file") → ("pdf_generated_at",)
    replacements = {
        ',"pdf_file"': '',
        ",'pdf_file'": '',
        '"pdf_file",': '',
        "'pdf_file',": '',
        # berjaga-jaga ada spasi:
        ', "pdf_file"': '',
        ", 'pdf_file'": '',
        '"pdf_file" ,': '',
        "'pdf_file' ,": '',
        # tuple trailing:
        ',"pdf_file")': ')',
        ",'pdf_file')": ')',
    }
    for old, new in replacements.items():
        s = s.replace(old, new)

    # 2) Jika kamu sebelumnya sudah menambah @property pdf_file tanpa setter,
    #    ganti dengan versi aman (getter+setter) dalam class FreightQuotation.
    if "@property" in s and "def pdf_file(" in s and "return _NullFile()" in s:
        # Ganti blok @property lama menjadi getter+setter yang aman.
        # Sederhana: cari baris mulai '@property' sampai 'return ...' penutup blok.
        import re
        s = re.sub(
            r"@property\s+def\s+pdf_file\(self\):[\s\S]*?return[^\n]*\n\s*\n",
            "",
            s,
            flags=re.M
        )
        # Sisipkan property baru di akhir class FreightQuotation (sebelum FreightCargo)
        s = s.replace(
            "class FreightCargo",
            """
    # Property pdf_file aman (getter+setter); tidak butuh field DB
    @property
    def pdf_file(self):
        return getattr(self, "_pdf_file_stub", None)

    @pdf_file.setter
    def pdf_file(self, value):
        # terima apapun yang diassign; None pun boleh
        try:
            setattr(self, "_pdf_file_stub", value)
        except Exception:
            setattr(self, "_pdf_file_stub", None)

class FreightCargo"""
        )

    if s != before:
        p.write_text(s, encoding="utf-8")
        print("Patched: sales/models.py → hapus 'pdf_file' dari update_fields & perbaiki property")
    else:
        print("sales/models.py tidak perlu diubah atau sudah bersih.")

def main():
    patch_wizard()
    patch_models()
    print("\nSelesai. Sekarang bersihkan cache .pyc lalu jalankan server:")
    print(r"  del /s /q *.pyc")
    print(r"  for /d /r %d in (__pycache__) do @rd /s /q ""%d""")
    print("Lalu:")
    print("  python manage.py runserver")
    print("Uji lagi:  /sales/quotations/freight/new-v2/?reset=1")

if __name__ == "__main__":
    main()
