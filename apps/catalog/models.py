from django.db import models


class Developer(models.Model):
    name = models.CharField("Название", max_length=200)
    is_demo = models.BooleanField("Демонстрационные данные", default=False)

    def __str__(self):
        return self.name


class ResidentialComplex(models.Model):
    developer = models.ForeignKey(
        Developer,
        on_delete=models.PROTECT,
        related_name="complexes",
        verbose_name="Застройщик",
    )
    external_id = models.CharField(
        "ID проекта Domoplaner",
        max_length=100,
        unique=True,
    )
    name = models.CharField("Название", max_length=200)

    catalog_synced_at = models.DateTimeField("Успешная полная синхронизация", null=True, blank=True)

    city = models.CharField("Город", max_length=100, blank=True)
    address = models.CharField("Адрес", max_length=255, blank=True)
    property_class = models.CharField(
        "Класс жилья",
        max_length=50,
        blank=True,
    )
    description = models.TextField("Описание", blank=True)
    infrastructure = models.JSONField(
        "Инфраструктура",
        default=dict,
        blank=True,
    )

    def __str__(self):
        return self.name


class ConstructionStage(models.Model):
    complex = models.ForeignKey(
        ResidentialComplex,
        on_delete=models.PROTECT,
        related_name="stages",
        verbose_name="ЖК",
    )
    external_id = models.CharField("ID этапа Domoplaner", max_length=100)
    name = models.CharField("Название", max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["complex", "external_id"],
                name="unique_stage_external_id_per_complex",
            ),
        ]
        verbose_name = "Этап строительства"
        verbose_name_plural = "Этапы строительства"

    def __str__(self):
        return f"{self.complex} — {self.name}"


class Building(models.Model):
    class State(models.TextChoices):
        HAND_OVER = "hand-over", "Передан"
        UNFINISHED = "unfinished", "Строится"

    stage = models.ForeignKey(
        ConstructionStage,
        on_delete=models.PROTECT,
        related_name="buildings",
        verbose_name="Этап строительства",
    )
    external_id = models.CharField("ID дома Domoplaner", max_length=100)
    name = models.CharField("Название", max_length=100)

    building_type = models.CharField(
        "Тип здания",
        max_length=100,
        blank=True,
    )
    building_state = models.CharField(
        "Состояние по Domoplaner",
        max_length=50,
        blank=True,
    )
    deadline_code = models.PositiveIntegerField(
        "Код срока сдачи Domoplaner",
        null=True,
        blank=True,
    )

    address = models.CharField("Адрес", max_length=255, blank=True)
    latitude = models.FloatField("Широта", null=True, blank=True)
    longitude = models.FloatField("Долгота", null=True, blank=True)
    cadastral_number = models.CharField(
        "Кадастровый номер",
        max_length=100,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["stage", "external_id"],
                name="unique_building_external_id_per_stage",
            ),
        ]
        verbose_name = "Дом или здание"
        verbose_name_plural = "Дома и здания"

    def __str__(self):
        return f"{self.stage} — {self.name}"


class Section(models.Model):
    building = models.ForeignKey(
        Building,
        on_delete=models.PROTECT,
        related_name="sections",
        verbose_name="Дом",
    )
    external_id = models.CharField("ID секции Domoplaner", max_length=100)
    name = models.CharField("Название", max_length=100)
    number_short = models.CharField(
        "Краткий номер",
        max_length=30,
        blank=True,
    )
    position = models.PositiveIntegerField("Позиция", default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["building", "external_id"],
                name="unique_section_external_id_per_building",
            ),
        ]
        verbose_name = "Секция"
        verbose_name_plural = "Секции"

    def __str__(self):
        return f"{self.building} — {self.name}"


class Floor(models.Model):
    section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="floors",
        verbose_name="Секция",
    )
    external_id = models.CharField("ID этажа Domoplaner", max_length=100)
    number = models.SmallIntegerField("Номер этажа")

    plan_url = models.URLField("План этажа", blank=True)
    plan_width = models.PositiveIntegerField(
        "Ширина плана",
        null=True,
        blank=True,
    )
    plan_height = models.PositiveIntegerField(
        "Высота плана",
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["section", "external_id"],
                name="unique_floor_external_id_per_section",
            ),
        ]
        verbose_name = "Этаж"
        verbose_name_plural = "Этажи"

    def __str__(self):
        return f"{self.section} — этаж {self.number}"


class Apartment(models.Model):
    class SourceType(models.IntegerChoices):
        FLAT = 0, "Квартира или апартамент"
        PARKING = 1, "Машино-место"
        STORAGE = 2, "Кладовая"

    class SourceStatus(models.IntegerChoices):
        RESERVED = -1, "Резерв"
        AVAILABLE = 0, "Свободно"
        BOOKED = 1, "Бронь"
        CONTRACT = 2, "Оформление договора"
        SOLD = 3, "Продано"

    floor = models.ForeignKey(
        Floor,
        on_delete=models.PROTECT,
        related_name="apartments",
        verbose_name="Этаж",
    )
    external_id = models.CharField("ID помещения Domoplaner", max_length=100)
    source_sid = models.CharField(
        "SID Domoplaner",
        max_length=100,
        blank=True,
    )

    number = models.CharField("Номер помещения", max_length=50)
    flat_code = models.CharField("Код помещения", max_length=100, blank=True)
    marketing_code = models.CharField(
        "Маркетинговый код",
        max_length=100,
        blank=True,
    )

    source_type = models.PositiveSmallIntegerField(
        "Тип помещения Domoplaner",
        choices=SourceType.choices,
    )
    source_status = models.SmallIntegerField(
        "Статус помещения Domoplaner",
        choices=SourceStatus.choices,
    )

    is_apart = models.BooleanField("Апартамент", default=False)
    is_studio = models.BooleanField("Студия", default=False)

    rooms = models.PositiveSmallIntegerField(
        "Количество комнат",
        null=True,
        blank=True,
    )
    rooms_sign = models.CharField(
        "Обозначение комнатности",
        max_length=30,
        blank=True,
    )

    area_m2 = models.DecimalField(
        "Площадь, м²",
        max_digits=9,
        decimal_places=2,
        null=True,
        blank=True,
    )
    price_rub = models.DecimalField(
        "Цена, ₽",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    plan_id = models.CharField(
        "ID планировки Domoplaner",
        max_length=100,
        blank=True,
    )
    plan_url = models.URLField("Ссылка на планировку", blank=True)
    images = models.JSONField("Изображения", default=list, blank=True)
    tags = models.JSONField("Теги источника", default=list, blank=True)

    position_on_floor = models.PositiveIntegerField(
        "Позиция на этаже",
        null=True,
        blank=True,
    )
    path_on_floor_plan = models.TextField(
        "Контур на плане этажа",
        blank=True,
    )
    path_on_floor_plan_svg = models.TextField(
        "Контур SVG",
        blank=True,
    )

    source_present = models.BooleanField("Есть в последнем полном фиде", default=False)

    created_at = models.DateTimeField("Создана в платформе", auto_now_add=True)
    updated_at = models.DateTimeField("Изменена в платформе", auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["floor", "external_id"],
                name="unique_apartment_external_id_per_floor",
            ),
        ]
        indexes = [
            models.Index(fields=["source_type", "source_status"]),
            models.Index(fields=["price_rub"]),
            models.Index(fields=["rooms"]),
            models.Index(fields=["area_m2"]),
        ]
        verbose_name = "Помещение"
        verbose_name_plural = "Помещения"

    def __str__(self):
        return f"{self.floor} — №{self.number}"

    @property
    def is_available_for_selection(self):
        from datetime import timedelta
        from django.conf import settings
        from django.utils import timezone

        synced_at = self.floor.section.building.stage.complex.catalog_synced_at
        return (
            not self.demo_bookings.filter(status="active", expires_at__gt=timezone.now()).exists()
            and self.source_present
            and synced_at is not None
            and timezone.now() - timedelta(minutes=settings.CATALOG_MAX_AGE_MINUTES) <= synced_at <= timezone.now()
            and self.source_type == self.SourceType.FLAT
            and self.source_status == self.SourceStatus.AVAILABLE
            and self.price_rub is not None
            and self.price_rub > 0
        )
