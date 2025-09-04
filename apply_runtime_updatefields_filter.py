# apply_runtime_updatefields_filter.py  (VERSI FIXED — tidak pakai f-string)
from pathlib import Path

BASE = Path.cwd()
wiz = BASE / "sales" / "wizard_v2.py"

if not wiz.exists():
    raise SystemExit("ERROR: sales/wizard_v2.py tidak ditemukan.")

src = wiz.read_text(encoding="utf-8")

needle = "from .models import FreightQuotation, FreightCargo"
if needle not in src:
    raise SystemExit("ERROR: Baris import FreightQuotation tidak ditemukan di sales/wizard_v2.py")

injected_marker = "# --- RUNTIME PATCH: pdf & update_fields filter ---"
if injected_marker in src:
    print("Runtime patch sudah ada. Tidak perlu disuntik lagi.")
else:
    patch = """
# --- RUNTIME PATCH: pdf & update_fields filter ---
# Shim pdf_file agar akses/assign/delete tidak meledak walau tidak ada field DB
def _install_pdf_shim_and_save_filter():
    class _PdfShim:
        url = ""
        path = ""
        def delete(self, save=False): return None
        def __bool__(self): return False
        __nonzero__ = __bool__
    # pdf_file property (getter+setter sederhana)
    try:
        if not hasattr(FreightQuotation, "pdf_file"):
            def _get_pdf(self): return getattr(self, "_pdf_file_stub", _PdfShim())
            def _set_pdf(self, val): setattr(self, "_pdf_file_stub", val if val is not None else _PdfShim())
            FreightQuotation.pdf_file = property(_get_pdf, _set_pdf)
    except Exception:
        pass

    # Filter update_fields saat save() → buang nama field yang tidak konkret
    try:
        _orig_save = FreightQuotation.save
        def _fq_save(self, *args, **kwargs):
            uf = kwargs.get("update_fields")
            if uf:
                uf_set = {str(x) for x in uf}
                uf_set.discard("pdf_generated_at")
                uf_set.discard("pdf_file")
                try:
                    valid = {f.name for f in self._meta.get_fields() if getattr(f, "concrete", False)}
                    uf_set = tuple(x for x in uf_set if x in valid)
                except Exception:
                    uf_set = tuple(uf_set)
                if not uf_set:
                    kwargs.pop("update_fields", None)
                else:
                    kwargs["update_fields"] = uf_set
            return _orig_save(self, *args, **kwargs)
        if getattr(FreightQuotation.save, "_patched_updatefields", False) is not True:
            _fq_save._patched_updatefields = True
            FreightQuotation.save = _fq_save
    except Exception:
        pass

_install_pdf_shim_and_save_filter()
# --- END RUNTIME PATCH ---
"""
    src = src.replace(needle, needle + "\n" + patch)
    wiz.write_text(src, encoding="utf-8")
    print("Patched: sales/wizard_v2.py → runtime filter update_fields + pdf shim disisipkan.")

print("\nBERSIHKAN cache & jalankan server:")
print(r"  del /s /q *.pyc")
print(r"  for /d /r %d in (__pycache__) do @rd /s /q ""%d""")
print("  python manage.py runserver")
print("\nUji lagi:  /sales/quotations/freight/new-v2/?reset=1")
