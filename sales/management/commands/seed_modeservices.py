from django.core.management.base import BaseCommand
from django.db import transaction
from sales.models import TransportMode, ServiceOption, ModeService, LocationRule

DATA = {
    "SEA": [
        ("D2D", "Door to Door", "CITY", "CITY"),
        ("D2P", "Door to Port", "CITY", "SEAPORT"),
        ("P2D", "Port to Door", "SEAPORT", "CITY"),
        ("P2P", "Port to Port", "SEAPORT", "SEAPORT"),
    ],
    "AIR": [
        ("D2A", "Door to Airport", "CITY", "AIRPORT"),
        ("A2D", "Airport to Door", "AIRPORT", "CITY"),
    ],
    "INLAND": [
        ("TRUCKING", "Trucking", "CITY", "CITY"),
    ],
}

class Command(BaseCommand):
    help = "Seed ModeService & LocationRule untuk SEA, AIR, INLAND"

    @transaction.atomic
    def handle(self, *args, **opts):
        for mode_code, services in DATA.items():
            mode, _ = TransportMode.objects.get_or_create(
                code=mode_code, defaults={"name": mode_code.title()}
            )
            for svc_code, svc_name, origin_type, dest_type in services:
                svc, _ = ServiceOption.objects.get_or_create(
                    code=svc_code, defaults={"name": svc_name}
                )
                ModeService.objects.get_or_create(mode=mode, service=svc)
                LocationRule.objects.get_or_create(
                    mode=mode,
                    service=svc,
                    defaults={"origin_type": origin_type, "destination_type": dest_type},
                )
                self.stdout.write(self.style.SUCCESS(f"OK: {mode_code} + {svc_code}"))
        self.stdout.write(self.style.SUCCESS("Seeding selesai."))
