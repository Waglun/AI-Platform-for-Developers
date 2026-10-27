from rest_framework import serializers

from apps.catalog.models import Apartment


class ApartmentSerializer(serializers.ModelSerializer):
    complex_name = serializers.CharField(
        source="floor.section.building.stage.complex.name",
        read_only=True,
    )
    building_name = serializers.CharField(
        source="floor.section.building.name",
        read_only=True,
    )
    section_name = serializers.CharField(
        source="floor.section.name",
        read_only=True,
    )
    floor_number = serializers.IntegerField(
        source="floor.number",
        read_only=True,
    )

    is_available_for_selection = serializers.BooleanField(
        read_only=True,
    )

    class Meta:
        model = Apartment
        fields = [
            "id",
            "number",
            "rooms",
            "rooms_sign",
            "area_m2",
            "price_rub",
            "is_apart",
            "is_studio",
            "plan_url",
            "images",
            "complex_name",
            "building_name",
            "section_name",
            "floor_number",
            "is_available_for_selection",
        ]