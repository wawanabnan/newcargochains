# revert_wizard_runtime_patches.py
from pathlib import Path
import re

p = Path("sales/wizard_v2.py")
s = p.read_text(encoding="utf-8")

# 1) Hapus blok runtime patch (update_fields filter + pdf shim) yang ditandai marker
s = re.sub(
    r"\n# --- RUNTIME PATCH: pdf & update_fields filter ---[\s\S]*?# --- END RUNTIME PATCH ---\n",
    "\n",
    s,
    flags=re.M,
)

# 2) Hapus blok "PDF shim installer" jika sempat tersisip
s = re.sub(
    r"\n# --- PDF shim installer ---[\s\S]*?# --- end PDF shim installer ---\n",
    "\n",
    s,
    flags=re.M,
)

# 3) Pastikan redirect sukses ke list (aman, tidak ke view yg akses pdf_file)
s = s.replace(
    'return redirect("sales:freight_view", pk=q.pk)',
    'return redirect("sales:freight_list")'
)

p.write_text(s, encoding="utf-8")
print("Done: runtime patches dicabut dari sales/wizard_v2.py")
