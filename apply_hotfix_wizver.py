# apply_hotfix_wizver.py
# Ganti variabel template dari __WIZ_VER -> WIZ_VER (Django tak boleh leading underscore)
from pathlib import Path

ROOT = Path.cwd()
changes = {
    "templates/sales/freight/wizard_v2.html": [
        ("{{ __WIZ_VER|default:", "{{ WIZ_VER|default:"),
        ("Wizard V2 {{ __WIZ_VER", "Wizard V2 {{ WIZ_VER"),
    ],
    "sales/wizard_v2.py": [
        ('"__WIZ_VER":"R8"', '"WIZ_VER":"R8"'),
        ("'__WIZ_VER':'R8'", "'WIZ_VER':'R8'"),
    ],
}

for rel, repls in changes.items():
    p = ROOT / rel
    if not p.exists():
        print(f"SKIP (not found): {rel}")
        continue
    s = p.read_text(encoding="utf-8")
    for old, new in repls:
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print(f"Patched: {rel}")

print("\nDONE. Restart server lalu buka /sales/quotations/freight/new-v2/?reset=1\n")
