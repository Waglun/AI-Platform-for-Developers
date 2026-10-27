
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import (
    Apartment,
    Building,
    ConstructionStage,
    Developer,
    Floor,
    ResidentialComplex,
    Section,
)


class Command(BaseCommand):
    help = "Создаёт тестового застройщика, ЖК и квартиры"

    @transaction.atomic
    def handle(self, *args, **options):
        developer, _ = Developer.objects.update_or_create(
            name="Демо-застройщик",
            defaults={"is_demo": True},
        )

        complex_, _ = ResidentialComplex.objects.update_or_create(
            external_id="demo-complex-001",
            defaults={
                "developer": developer,
                "name": "ЖК Солнечный берег",
                "city": "Иркутск",
                "address": "ул. Примерная, 10",
                "property_class": "Комфорт",
                "description": (
                    "Демонстрационный жилой комплекс "
                    "для проверки каталога."
                ),
                "infrastructure": {
                    "items": ["Школа", "Детский сад", "Парковка"]
                },
            },
        )

        stage, _ = ConstructionStage.objects.update_or_create(
            complex=complex_,
            external_id="demo-stage-001",
            defaults={"name": "Первый этап"},
        )

        building, _ = Building.objects.update_or_create(
            stage=stage,
            external_id="demo-building-001",
            defaults={
                "name": "Дом 1",
                "building_type": "Монолит",
                "building_state": "unfinished",
                "deadline_code": 20272,
                "address": "ул. Примерная, 10",
            },
        )

        section, _ = Section.objects.update_or_create(
            building=building,
            external_id="demo-section-001",
            defaults={
                "name": "Секция 1",
                "number_short": "1",
                "position": 1,
            },
        )

        floor, _ = Floor.objects.update_or_create(
            section=section,
            external_id="demo-floor-001",
            defaults={
                "number": 3,
                "plan_url": "",
                "plan_width": None,
                "plan_height": None,
            },
        )

        apartments = [
            {
                "external_id": "demo-flat-001",
                "number": "31",
                "source_status": Apartment.SourceStatus.AVAILABLE,
                "rooms": 1,
                "area_m2": Decimal("38.50"),
                "price_rub": Decimal("5500000.00"),
                "is_studio": False,
            },
            {
                "external_id": "demo-flat-002",
                "number": "32",
                "source_status": Apartment.SourceStatus.AVAILABLE,
                "rooms": 2,
                "area_m2": Decimal("57.20"),
                "price_rub": Decimal("7800000.00"),
                "is_studio": False,
            },
            {
                "external_id": "demo-flat-003",
                "number": "33",
                "source_status": Apartment.SourceStatus.AVAILABLE,
                "rooms": 3,
                "area_m2": Decimal("78.40"),
                "price_rub": Decimal("10200000.00"),
                "is_studio": False,
            },
            {
                "external_id": "demo-flat-004",
                "number": "34",
                "source_status": Apartment.SourceStatus.AVAILABLE,
                "rooms": 1,
                "area_m2": Decimal("26.10"),
                "price_rub": Decimal("4200000.00"),
                "is_studio": True,
            },
            {
                "external_id": "demo-flat-005",
                "number": "35",
                "source_status": Apartment.SourceStatus.SOLD,
                "rooms": 2,
                "area_m2": Decimal("55.00"),
                "price_rub": Decimal("7500000.00"),
                "is_studio": False,
            },
            {
                "external_id": "demo-flat-006",
                "number": "36",
                "source_status": Apartment.SourceStatus.RESERVED,
                "rooms": 1,
                "area_m2": Decimal("40.00"),
                "price_rub": Decimal("5700000.00"),
                "is_studio": False,
            },
        ]

        for data in apartments:
            external_id = data["external_id"]
            number = data["number"]
            source_status = data["source_status"]

            Apartment.objects.update_or_create(
                floor=floor,
                external_id=external_id,
                defaults={
                    "source_sid": "",
                    "number": number,
                    "flat_code": external_id,
                    "marketing_code": "",
                    "source_type": Apartment.SourceType.FLAT,
                    "source_status": source_status,
                    "is_apart": False,
                    "is_studio": data["is_studio"],
                    "rooms": data["rooms"],
                    "rooms_sign": str(data["rooms"]),
                    "area_m2": data["area_m2"],
                    "price_rub": data["price_rub"],
                    "plan_id": "",
                    "plan_url": "",
                    "images": [],
                    "tags": [],
                    "position_on_floor": None,
                    "path_on_floor_plan": "",
                    "path_on_floor_plan_svg": "",
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Тестовый каталог успешно создан или обновлён.\n"
                f"Застройщик: {developer.name}\n"
                f"ЖК: {complex_.name}\n"
                f"Квартир в демонаборе: {len(apartments)}"
            )
        )
