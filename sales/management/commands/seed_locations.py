from django.core.management.base import BaseCommand
from sales.models import Location

class Command(BaseCommand):
    help = "Seed sample locations (City, Seaport, Airport) for freight wizard"

    def handle(self, *args, **options):
        data = [
            ("Jakarta", "CITY"),
            ("Surabaya", "CITY"),
            ("Medan", "CITY"),
            ("Tanjung Priok", "SEAPORT"),
            ("Tanjung Perak", "SEAPORT"),
            ("Belawan", "SEAPORT"),
            ("CGK - Soekarno Hatta", "AIRPORT"),
            ("SUB - Juanda", "AIRPORT"),
            ("KNO - Kualanamu", "AIRPORT"),
        ]
        for name, lt in data:
            obj, created = Location.objects.get_or_create(name=name, loc_type=lt)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created {name} ({lt})"))
            else:
                self.stdout.write(f"Exists {name} ({lt})")
        self.stdout.write(self.style.SUCCESS("Seed locations completed."))
