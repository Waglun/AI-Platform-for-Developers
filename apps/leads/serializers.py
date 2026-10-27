from rest_framework import serializers

from apps.catalog.serializers import ApartmentSerializer
from apps.leads.models import Lead, LeadComment


class LeadListSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(
        source="contact.name",
        read_only=True,
    )
    contact_phone = serializers.CharField(
        source="contact.phone",
        read_only=True,
    )
    assigned_to_name = serializers.CharField(
        source="assigned_to.get_full_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Lead
        fields = [
            "id",
            "contact_name",
            "contact_phone",
            "budget_min",
            "budget_max",
            "source",
            "status",
            "assigned_to_name",
            "created_at",
        ]


class LeadCommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(
        source="author.get_full_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = LeadComment
        fields = ["id", "author_name", "text", "created_at"]


class LeadDetailSerializer(serializers.ModelSerializer):
    contact_name = serializers.CharField(
        source="contact.name",
        read_only=True,
    )
    contact_phone = serializers.CharField(
        source="contact.phone",
        read_only=True,
    )
    contact_email = serializers.EmailField(
        source="contact.email",
        read_only=True,
    )
    assigned_to_name = serializers.CharField(
        source="assigned_to.get_full_name",
        read_only=True,
        allow_null=True,
    )
    apartments = ApartmentSerializer(many=True, read_only=True)
    comments = LeadCommentSerializer(many=True, read_only=True)

    class Meta:
        model = Lead
        fields = [
            "id",
            "contact_name",
            "contact_phone",
            "contact_email",
            "budget_min",
            "budget_max",
            "requirements",
            "apartments",
            "source",
            "status",
            "assigned_to",
            "assigned_to_name",
            "comments",
            "created_at",
            "updated_at",
        ]


class LeadStatusUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ["status"]

    def validate_status(self, value):
        if value not in Lead.Status.values:
            raise serializers.ValidationError(
                "Недопустимый статус заявки."
            )
        return value


class LeadCommentCreateSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(
        source="author.get_full_name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = LeadComment
        fields = ["id", "author_name", "text", "created_at"]
        read_only_fields = ["id", "author_name", "created_at"]

    def validate_text(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Комментарий не может быть пустым."
            )

        return value