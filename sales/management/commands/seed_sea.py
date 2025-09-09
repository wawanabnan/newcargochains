from django.core.management.base import BaseCommand
from django.db import transaction
from sales.models import TransportMode, ServiceOption, ModeService, LocationRule

SEA = {"code": "SEA", "name": "Sea Freight"}

SERVICES = [
    ("D2D", "Door to Door",   "CITY",    "CITY"),
    ("D2P", "Door to Port",   "CITY",    "SEAPORT"),
    ("P2D", "Port to Door",   "SEAPORT", "CITY"),
    ("P2P", "Port to Port",   "SEAPORT", "SEAPORT"),
]

class Command(BaseCommand):
    help = "Seed ModeService & LocationRule untuk SEA (D2D, D2P, P2D, P2P). Aman diulang."

    @transaction.atomic
    def handle(self, *args, **kwargs):
        # 1) Pastikan mode SEA ada
        sea, _ = TransportMode.objects.get_or_create(
            code=SEA["code"], defaults={"name": SEA["name"]}
        )
        self.stdout.write(self.style.SUCCESS(f"[OK] TransportMode {sea.code}"))

        # 2) Pastikan services ada + mapping ModeService + LocationRule
        for svc_code, svc_name, otype, dtype in SERVICES:
            svc, _ = ServiceOption.objects.get_or_create(
                code=svc_code, defaults={"name": svc_name}
            )
            ModeService.objects.get_or_create(mode=sea, service=svc)
            lr, created = LocationRule.objects.get_or_create(
                mode=sea, service=svc,
                defaults={"origin_type": otype, "destination_type": dtype},
            )
            # Jika rule sudah ada tapi typenya pengin dipastikan, bisa diupdate ringan:
            if not created:
                changed = False
                if lr.origin_type != otype:
                    lr.origin_type = otype; changed = True
                if lr.destination_type != dtype:
                    lr.destination_type = dtype; changed = True
                if changed:
                    lr.save(update_fields=["origin_type", "destination_type"])
            self.stdout.write(self.style.SUCCESS(f"[OK] {sea.code}+{svc.code} → {otype} -> {dtype}"))

        self.stdout.write(self.style.SUCCESS("Selesai. SEA services & rules siap."))
