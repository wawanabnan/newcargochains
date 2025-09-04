# sales/location_helper.py

from typing import Tuple

# Mapping sederhana: service -> (origin_type, destination_type)
# Kita pakai label generik "PORT" dan "CITY".
# Nanti, di endpoint, label ini diterjemahkan ke tipe aktual (SEAPORT/AIRPORT/CITY/JETTY) tergantung mode.
SERVICE_PAIR = {
    "P2P": ("PORT", "PORT"),
    "D2P": ("CITY", "PORT"),
    "P2D": ("PORT", "CITY"),
    "D2D": ("CITY", "CITY"),
}

# Mode → tipe "PORT" yang benar untuk mode tsb
PORT_TYPE_BY_MODE = {
    "SEA": "SEAPORT",
    "AIR": "AIRPORT",
    # Untuk moda darat, tidak ada "PORT" → default ke CITY/JETTY
    "LAND": "CITY",
    "ROAD": "CITY",
    "TRUCK": "CITY",
}

def compute_location_types(mode: str, service: str) -> Tuple[str, str]:
    """
    Kembalikan tuple (origin_type, destination_type) spesifik untuk DB,
    contoh: ("SEAPORT", "CITY") untuk SEA + P2D.
    """
    mode = (mode or "").upper()
    service = (service or "").upper()

    base = SERVICE_PAIR.get(service, ("CITY", "CITY"))
    # terjemahkan "PORT" ke tipe aktual berdasar mode
    def resolve(t):
        if t == "PORT":
            return PORT_TYPE_BY_MODE.get(mode, "CITY")
        return t
    return resolve(base[0]), resolve(base[1])
