from django.contrib import admin

from .models import (
    Apartment,
    Building,
    ConstructionStage,
    Developer,
    Floor,
    ResidentialComplex,
    Section,
)


@admin.register(Developer)
class DeveloperAdmin(admin.ModelAdmin):
    list_display = ("name", "is_demo")
    search_fields = ("name",)
    list_filter = ("is_demo",)


@admin.register(ResidentialComplex)
class ResidentialComplexAdmin(admin.ModelAdmin):
    list_display = ("name", "external_id", "developer", "city")
    search_fields = ("name", "external_id", "city")
    list_filter = ("developer",)
    list_select_related = ("developer",)


@admin.register(ConstructionStage)
class ConstructionStageAdmin(admin.ModelAdmin):
    list_display = ("name", "complex", "external_id")
    search_fields = ("name", "external_id", "complex__name")
    list_filter = ("complex",)
    list_select_related = ("complex",)


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "stage",
        "building_type",
        "building_state",
        "deadline_code",
    )
    search_fields = (
        "name",
        "external_id",
        "address",
        "stage__name",
        "stage__complex__name",
    )
    list_filter = (
        "building_state",
        "building_type",
        "stage__complex",
    )
    list_select_related = ("stage__complex",)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "building", "number_short", "position")
    search_fields = (
        "name",
        "external_id",
        "building__name",
        "building__stage__complex__name",
    )
    list_filter = ("building__stage__complex",)
    list_select_related = ("building__stage__complex",)


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ("number", "section", "external_id")
    search_fields = (
        "external_id",
        "section__name",
        "section__building__name",
        "section__building__stage__complex__name",
    )
    list_filter = ("section__building__stage__complex",)
    list_select_related = ("section__building__stage__complex",)


@admin.register(Apartment)
class ApartmentAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "floor",
        "source_type",
        "source_status",
        "rooms",
        "area_m2",
        "price_rub",
    )
    search_fields = (
        "number",
        "external_id",
        "source_sid",
        "flat_code",
        "marketing_code",
        "floor__section__building__name",
        "floor__section__building__stage__complex__name",
    )
    list_filter = (
        "source_type",
        "source_status",
        "is_studio",
        "is_apart",
        "floor__section__building__stage__complex",
    )
    list_select_related = (
        "floor__section__building__stage__complex",
    )
    list_per_page = 50