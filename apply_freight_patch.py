# apply_freight_patch.py
# Jalankan dari root project:  python apply_freight_patch.py
import re, os, sys, shutil

VIEWS = os.path.join("sales", "views.py")
BACKUP = os.path.join("sales", "views.py.bak")

HELPERS = '''
from geo.models import Location

def _normalize_opt(val: str) -> str:
    return (val or "").upper().replace("-", "_").replace(" ", "_")

def _origin_dest_types(transport_mode: str, service_option: str):
    """
    Return (origin_types, dest_types) berisi tipe Location yang dibolehkan.
    TRUCK/LAND → CITY↔CITY, SEA 'port' = SEAPORT/JETTY, AIR 'port' = AIRPORT.
    DOOR↔DOOR=CITY↔CITY, DOOR→PORT=CITY→PORT, PORT→DOOR=PORT→CITY, PORT↔PORT=PORT↔PORT
    """
    mode = _normalize_opt(transport_mode)
    opt  = _normalize_opt(service_option)
    if mode in ("LAND", "TRUCK", "ROAD", "TRUCKING"):
        return ({Location.CITY}, {Location.CITY})
    port_types = {Location.AIRPORT} if mode == "AIR" else {Location.SEAPORT, Location.JETTY}
    city = {Location.CITY}
    if opt in ("DOOR_TO_DOOR", "D2D"):
        return (city, city)
    if opt in ("DOOR_TO_PORT", "D2P", "DOOR_TO_AIRPORT"):
        return (city, port_types)
    if opt in ("PORT_TO_DOOR", "P2D", "AIRPORT_TO_DOOR"):
        return (port_types, city)
    if opt in ("PORT_TO_PORT", "P2P", "AIRPORT_TO_AIRPORT"):
        return (port_types, port_types)
    return (port_types, port_types) if mode in ("SEA", "AIR") else (city, city)

def _qs_for_types(type_set):
    return Location.objects.filter(type__in=list(type_set)).order_by("name")
'''.strip() + "\n"

def ensure_helpers(txt):
    if "_origin_dest_types(" in txt and "_qs_for_types(" in txt:
        return txt, False
    # sisipkan setelah _wiz_clear kalau ada; jika tidak, setelah blok imports
    m = re.search(r"def\s+_wiz_clear\s*\([^)]*\):.*?\n(?=def\s)", txt, re.S)
    insert_at = None
    if m:
        insert_at = m.end()
    else:
        m2 = re.search(r"(?:^from\s+\S+\s+import[^\n]*\n|^import[^\n]*\n)+", txt, re.M)
        insert_at = m2.end() if m2 else 0
    return txt[:insert_at] + "\n\n" + HELPERS + "\n" + txt[insert_at:], True

def patch_post_block(txt):
    """
    Di blok POST Step-2: setelah membuat CargoFormSet(prefix="cargo"),
    hitung origin/dest types -> queryset, dan set ke fields.
    """
    # Tambahkan kalkulasi origin_qs/dest_qs setelah CargoFormSet(..., prefix="cargo")
    txt_new, n = re.subn(
        r"(cargo_fs\s*=\s*CargoFormSet\([^\)]*prefix\s*=\s*[\"']cargo[\"'][^\)]*\)\s*)\n",
        r"\1\n            mode = (hdr.get(\"transport_mode\") or \"SEA\")\n"
        r"            opt  = (hdr.get(\"service_option\") or \"PORT_TO_PORT\")\n"
        r"            origin_types, dest_types = _origin_dest_types(mode, opt)\n"
        r"            origin_qs = _qs_for_types(origin_types)\n"
        r"            dest_qs   = _qs_for_types(dest_types)\n",
        txt, flags=re.M
    )
    txt = txt_new

    # Ganti assignment queryset lama (loc_qs) → origin_qs/dest_qs
    txt = re.sub(r"f\.fields\[[\"']origin[\"']\]\.queryset\s*=\s*loc_qs",
                 r"f.fields[\"origin\"].queryset = origin_qs", txt)
    txt = re.sub(r"f\.fields\[[\"']destination[\"']\]\.queryset\s*=\s*loc_qs",
                 r"f.fields[\"destination\"].queryset = dest_qs", txt)

    return txt

def patch_get_block(txt):
    """
    Di blok GET Step-2: setelah CargoFormSet(prefix="cargo"),
    hitung origin/dest types -> queryset, dan set ke fields.
    """
    txt_new, n = re.subn(
        r"(cargo_fs\s*=\s*CargoFormSet\(\s*prefix\s*=\s*[\"']cargo[\"'][^\)]*\)\s*)\n",
        r"\1\n        mode = (hdr.get(\"transport_mode\") or \"SEA\")\n"
        r"        opt  = (hdr.get(\"service_option\") or \"PORT_TO_PORT\")\n"
        r"        origin_types, dest_types = _origin_dest_types(mode, opt)\n"
        r"        origin_qs = _qs_for_types(origin_types)\n"
        r"        dest_qs   = _qs_for_types(dest_types)\n",
        txt, flags=re.M
    )
    txt = txt_new

    txt = re.sub(r"f\.fields\[[\"']origin[\"']\]\.queryset\s*=\s*loc_qs",
                 r"f.fields[\"origin\"].queryset = origin_qs", txt)
    txt = re.sub(r"f\.fields\[[\"']destination[\"']\]\.queryset\s*=\s*loc_qs",
                 r"f.fields[\"destination\"].queryset = dest_qs", txt)
    return txt

def patch_redirect(txt):
    """
    Ubah redirect akhir dari list → detail.
    """
    return re.sub(r"return\s+redirect\(\s*[\"']sales:freight_list[\"']\s*\)",
                  r"return redirect(\"sales:freight_view\", pk=q.pk)", txt)

def main():
    if not os.path.exists(VIEWS):
        print("Tidak menemukan sales/views.py — jalankan dari root proyek.")
        sys.exit(1)

    # backup dulu
    if not os.path.exists(BACKUP):
        shutil.copyfile(VIEWS, BACKUP)

    with open(VIEWS, "r", encoding="utf-8") as f:
        txt = f.read()

    txt, added_helpers = ensure_helpers(txt)
    before = txt
    txt = patch_post_block(txt)
    txt = patch_get_block(txt)
    txt = patch_redirect(txt)

    if txt == before and not added_helpers:
        print("Tidak ada perubahan yang diterapkan. Cek pola di views.py Anda.")
        sys.exit(2)

    with open(VIEWS, "w", encoding="utf-8") as f:
        f.write(txt)

    print("Selesai. {}helpers ditambahkan. Backup: {}".format(
        "Dengan " if added_helpers else "Tanpa ", BACKUP))

if __name__ == "__main__":
    main()
