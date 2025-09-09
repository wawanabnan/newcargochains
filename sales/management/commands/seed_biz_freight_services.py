from django.core.management.base import BaseCommand
from django.db import transaction
from sales.models import BusinessType, TransportMode, ServiceOption, ModeService

class Command(BaseCommand):
    help = "Seed Business Types, Transport Modes, Service Options, dan mapping Mode↔Service."

    @transaction.atomic
    def handle(self, *args, **kwargs):
        # Business Types
        bt, _ = BusinessType.objects.get_or_create(code="FREIGHT", defaults={"name": "Freight Forwarding", "is_active": True})
        self.stdout.write(self.style.SUCCESS(f"BusinessType: {bt.code}"))

        # Transport Modes
        modes = {
            "SEA": ("Sea Freight", True),
            "AIR": ("Air Freight", True),
            "INLAND": ("Inland / Trucking", True),
        }
        mode_objs = {}
        for code, (name, active) in modes.items():
            m, _ = TransportMode.objects.get_or_create(code=code, defaults={"name": name, "business_type": bt, "is_active": active})
            # keep data fresh if changed
            changed = False
            if m.name != name: m.name, changed = name, True
            if m.business_type_id != bt.id: m.business_type, changed = bt, True
            if m.is_active != active: m.is_active, changed = active, True
            if changed: m.save()
            mode_objs[code] = m
            self.stdout.write(f"Mode: {m.code} ({m.name})")

        # Service Options
        services = {
            "D2D": "Door to Door",
            "D2P": "Door to Port",
            "P2D": "Port to Door",
            "P2P": "Port to Port",
            "D2A": "Door to Airport",
            "A2D": "Airport to Door",
            "TRUCKING": "Trucking",
        }
        svc_objs = {}
        for code, name in services.items():
            s, _ = ServiceOption.objects.get_or_create(code=code, defaults={"name": name, "is_active": True})
            if s.name != name: s.name = name; s.save(update_fields=["name"])
            svc_objs[code] = s
            self.stdout.write(f"Service: {s.code} ({s.name})")

        # Mode ↔ Service mapping
        mapping = {
            "SEA": ["D2D", "D2P", "P2D", "P2P"],
            "AIR": ["D2A", "A2D"],
            "INLAND": ["TRUCKING"],
        }
        for mcode, scodes in mapping.items():
            m = mode_objs[mcode]
            for scode in scodes:
                s = svc_objs[scode]
                ModeService.objects.get_or_create(mode=m, service=s)
                self.stdout.write(f"Map: {m.code} -> {s.code}")

        self.stdout.write(self.style.SUCCESS("Seed Business/Mode/Service mapping completed."))
