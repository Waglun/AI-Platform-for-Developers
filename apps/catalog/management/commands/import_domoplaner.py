import json
from urllib.request import urlopen

from django.core.management.base import BaseCommand, CommandError
from decimal import Decimal
from apps.catalog.models import (
    Developer,
    ResidentialComplex,
    ConstructionStage,
    Building,
    Section,
    Floor,
    Apartment,
)


FEED_URL = "https://domoplaner.ru/dc-api/feeds/609-Kner2AYCFzxdc9CrWtKEzDHYi4QHzTCms99nzSK3mmBCOHhJDbmtwLhxThqHdmFm/"


class Command(BaseCommand):
    help = "Импорт каталога недвижимости из Domoplaner"

    def handle(self, *args, **options):
        self.stdout.write("Получение фида Domoplaner...")

        try:
            with urlopen(FEED_URL, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as error:
            raise CommandError(f"Не удалось получить фид: {error}")

        if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
            raise CommandError("Некорректная структура фида Domoplaner.")

        developer, _ = Developer.objects.get_or_create(
            name="Застройщик Domoplaner",
            defaults={"is_demo": False},
        )

        for project in data["projects"]:
            complex_, created = ResidentialComplex.objects.update_or_create(
                external_id=str(project["id"]),
                defaults={
                    "developer": developer,
                    "name": project["title"],
                },
            )

            for stage_data in project.get("stages", []):
                stage, stage_created = ConstructionStage.objects.update_or_create(
                    complex=complex_,
                    external_id=str(stage_data["id"]),
                    defaults={
                        "name": stage_data["title"],
                    },
                )

                for house_data in stage_data.get("houses", []):
                    building, building_created = Building.objects.update_or_create(
                        stage=stage,
                        external_id=str(house_data["id"]),
                        defaults={
                            "name": house_data["title"],
                            "deadline_code": house_data.get("deadline"),
                            "building_state": house_data.get("building_state", ""),
                            "building_type": house_data.get("building_type", ""),
                            "latitude": house_data.get("lat"),
                            "longitude": house_data.get("lng"),
                            "address": house_data.get("address", ""),
                            "cadastral_number": house_data.get("cadastral_number") or "",
                        },
                    )

                    for section_data in house_data.get("sections", []):
                        section, section_created = Section.objects.update_or_create(
                            building=building,
                            external_id=str(section_data["id"]),
                            defaults={
                                "name": section_data["title"],
                                "number_short": str(section_data.get("number_short") or ""),
                                "position": section_data.get("position") or 0,
                            },
                        )

                        for floor_data in section_data.get("floors", []):
                            plan = floor_data.get("plan") or {}

                            floor, floor_created = Floor.objects.update_or_create(
                                section=section,
                                external_id=str(floor_data["id"]),
                                defaults={
                                    "number": floor_data["number"],
                                    "plan_url": plan.get("image") or "",
                                    "plan_width": plan.get("width"),
                                    "plan_height": plan.get("height"),
                                },
                            )

                            for flat_data in floor_data.get("flats", []):
                                images = flat_data.get("images") or []

                                plan_url = next(
                                    (
                                        image.get("src")
                                        for image in images
                                        if image.get("type") == "plan" and image.get("src")
                                    ),
                                    "",
                                )

                                flat, flat_created = Apartment.objects.update_or_create(
                                    floor=floor,
                                    external_id=str(flat_data["id"]),
                                    defaults={
                                        "source_sid": flat_data.get("sid") or "",
                                        "number": str(flat_data.get("number") or ""),
                                        "flat_code": flat_data.get("flat_code") or "",
                                        "marketing_code": flat_data.get("flat_marketing_code") or "",

                                        "source_type": flat_data["type"],
                                        "source_status": flat_data["status"],

                                        "is_apart": bool(flat_data.get("is_apart")),
                                        "is_studio": bool(flat_data.get("is_studio")),

                                        "rooms": flat_data.get("rooms"),
                                        "rooms_sign": flat_data.get("rooms_sign") or "",

                                        "area_m2": (
                                            Decimal(str(flat_data["area"]))
                                            if flat_data.get("area") is not None else None
                                        ),
                                        "price_rub": (
                                            Decimal(str(flat_data["price"]))
                                            if flat_data.get("price") is not None else None
                                        ),

                                        "plan_id": (
                                            str(flat_data["plan_id"])
                                            if flat_data.get("plan_id") is not None else ""
                                        ),
                                        "plan_url": plan_url,
                                        "images": images,
                                        "tags": flat_data.get("tags") or [],

                                        "position_on_floor": flat_data.get("position_on_floor"),
                                        "path_on_floor_plan": flat_data.get("path_on_floor_plan") or "",
                                        "path_on_floor_plan_svg": (
                                                flat_data.get("path_on_floor_plan_svg_format") or ""
                                        ),
                                    },
                                )

                            action = "Создан" if floor_created else "Обновлён"

                            self.stdout.write(
                                f"        {action} этаж: {floor.number} "
                                f"(ID: {floor.external_id})"
                            )

                        action = "Создана" if section_created else "Обновлена"

                        self.stdout.write(
                            f"      {action} секция: {section.name} "
                            f"(ID: {section.external_id})"
                        )

                    action = "Создан" if building_created else "Обновлён"

                    self.stdout.write(
                        f"    {action} дом: {building.name} "
                        f"(ID: {building.external_id})"
                    )

                action = "Создан" if stage_created else "Обновлён"

                self.stdout.write(
                    f"  {action} этап: {stage.name} "
                    f"(ID: {stage.external_id})"
                )

            action = "Создан" if created else "Обновлён"

            self.stdout.write(
                self.style.SUCCESS(
                    f"{action} ЖК: {complex_.name} (ID: {complex_.external_id})"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Фид успешно получен. Версия: {data.get('v')}. "
                f"Проектов: {len(data['projects'])}"
            )
        )