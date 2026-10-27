from rest_framework import serializers

from apps.chat.models import Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = (
            "id",
            "role",
            "content",
            "metadata",
            "created_at",
        )
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(
        max_length=5000,
        trim_whitespace=True,
    )

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Сообщение не должно быть пустым."
            )
        return value