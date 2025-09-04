# sales/helpers_freight_overlay.py
from geo.models import Location

def normalize_opt(val):
    return (val or "").upper().replace("-", "_").replace(" ", "_")

def origin_dest_types(transport_mode, service_option):
    """
    Return (origin_types, dest_types) berupa SET tipe Location yang dibolehkan.
    - TRUCK/LAND/ROAD/TRUCKING -> CITY <-> CITY
    - SEA 'port' = SEAPORT (TANPA JETTY)
    - AIR 'port' = AIRPORT
    - DOOR<->DOOR = CITY<->CITY
    - DOOR->PORT = CITY->PORT
    - PORT->DOOR = PORT->CITY
    - PORT<->PORT = PORT<->PORT
    """
    mode = normalize_opt(transport_mode)
    opt  = normalize_opt(service_option)

    if mode in ("LAND", "TRUCK", "ROAD", "TRUCKING"):
        return ({Location.CITY}, {Location.CITY})

    port_types = {Location.AIRPORT} if mode == "AIR" else {Location.SEAPORT}
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

def qs_for_types(type_set):
    return Location.objects.filter(type__in=list(type_set)).order_by("name")

def service_options_for_mode(mode):
    m = (mode or '').upper()
    if m in ('LAND', 'TRUCK', 'ROAD', 'TRUCKING'):
        return [('DOOR_TO_DOOR', 'Door to Door')]
    elif m == 'AIR':
        return [
            ('PORT_TO_PORT', 'Airport to Airport'),
            ('DOOR_TO_PORT', 'Door to Airport'),
            ('PORT_TO_DOOR', 'Airport to Door'),
            ('DOOR_TO_DOOR', 'Door to Door'),
        ]
    else:  # SEA default
        return [
            ('PORT_TO_PORT', 'Port to Port'),
            ('DOOR_TO_PORT', 'Door to Port'),
            ('PORT_TO_DOOR', 'Port to Door'),
            ('DOOR_TO_DOOR', 'Door to Door'),
        ]
