import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from apps.catalog.models import (
    Apartment,
    Building,
    Developer,
    ResidentialComplex,
)


FINISHING_MAP = {
    "без отделки": Apartment.Finishing.NONE,
    "предчистовая": Apartment.Finishing.PRE_FINISHED,
    "чистовая": Apartment.Finishing.FINISHED,
}


def save_validated(model, lookup, values):
    obj = model.objects.filter(**lookup).first()
    created = obj is None

    if created:
        obj = model(**lookup)

    for field, value in values.items():
        setattr(obj, field, value)

    obj.full_clean()
    obj.save()

    return obj, created


class Command(BaseCommand):
    help = "Загружает демонстрационный каталог из JSON-фида"

    def add_arguments(self, parser):
        parser.add_argument("path", type=Path, help="Путь к JSON-фиду")

    def handle(self, *args, **options):
        try:
            with options["path"].open(encoding="utf-8-sig") as file:
                feed = json.load(file, parse_float=Decimal)

            if feed.get("is_demo") is not True:
                raise ValueError("Команда предназначена только для демо-фида")

            if feed.get("schema_version") != "1.0":
                raise ValueError("Неподдерживаемая версия фида")

            with transaction.atomic():
                created_count, updated_count = self.import_feed(feed)

        except (
            OSError,
            ValueError,
            KeyError,
            TypeError,
            ValidationError,
            IntegrityError,
        ) as exc:
            raise CommandError(f"Импорт отменён: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Импорт завершён. "
                f"Квартир создано: {created_count}, "
                f"обновлено: {updated_count}"
            )
        )

    def import_feed(self, feed):
        complex_data = feed["complex"]

        developer, _ = save_validated(
            Developer,
            {"name": complex_data["developer"]},
            {"is_demo": True},
        )

        complex_obj, _ = save_validated(
            ResidentialComplex,
            {"external_id": complex_data["id"]},
            {
                "developer": developer,
                "name": complex_data["name"],
                "city": complex_data["city"],
                "address": complex_data["address"],
                "property_class": complex_data["class"],
                "description": complex_data.get("description", ""),
                "infrastructure": complex_data.get("infrastructure", {}),
            },
        )

        buildings = {}

        for item in complex_data["buildings"]:
            if item["id"] in buildings:
                raise ValueError(f"Повторный ID корпуса: {item['id']}")

            building, _ = save_validated(
                Building,
                {
                    "complex": complex_obj,
                    "external_id": item["id"],
                },
                {
                    "name": item["name"],
                    "floors": item["floors"],
                    "completion_date": date.fromisoformat(
                        item["completion_date"]
                    ),
                    "key_handover_date": date.fromisoformat(
                        item["key_handover_date"]
                    ),
                },
            )
            buildings[item["id"]] = building

        created_count = 0
        updated_count = 0
        seen_ids = set()

        for item in feed["apartments"]:
            external_id = item["id"]

            if external_id in seen_ids:
                raise ValueError(f"Повторный ID квартиры: {external_id}")
            seen_ids.add(external_id)

            if item["complex_id"] != complex_obj.external_id:
                raise ValueError(f"{external_id}: неверный ЖК")

            building = buildings[item["building_id"]]

            if not 1 <= item["floor"] <= building.floors:
                raise ValueError(f"{external_id}: неверный этаж")

            if item["total_floors"] != building.floors:
                raise ValueError(f"{external_id}: этажность не совпадает")

            if item["area_m2"] <= 0 or item["price_rub"] <= 0:
                raise ValueError(f"{external_id}: площадь и цена должны быть > 0")

            if item["currency"] != "RUB":
                raise ValueError(f"{external_id}: поддерживаются только рубли")

            source_updated_at = parse_datetime(item["updated_at"])

            if source_updated_at is None or not is_aware(source_updated_at):
                raise ValueError(f"{external_id}: неверная дата обновления")

            values = {
                field: item[field]
                for field in (
                    "apartment_number",
                    "entrance",
                    "floor",
                    "rooms",
                    "layout_type",
                    "area_m2",
                    "kitchen_area_m2",
                    "kitchen_living_area_m2",
                    "price_rub",
                    "status",
                    "balcony_type",
                    "bathrooms",
                    "view",
                    "ceiling_height_m",
                    "is_corner",
                    "mortgage_available",
                    "installment_available",
                )
            }
            values.update(
                finishing=FINISHING_MAP[item["finishing"]],
                source_updated_at=source_updated_at,
                layout_url=item.get("layout_url") or "",
                property_url=item.get("property_url") or "",
            )

            _, created = save_validated(
                Apartment,
                {
                    "building": building,
                    "external_id": external_id,
                },
                values,
            )

            if created:
                created_count += 1
            else:
                updated_count += 1

        return created_count, updated_count