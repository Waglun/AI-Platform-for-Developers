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
    request_id = serializers.UUIDField()
    apartment_id = serializers.IntegerField(min_value=1, required=False)

    content = serializers.CharField(
        max_length=5000,
        trim_whitespace=True,
        required=False,
    )

    action = serializers.CharField(
        max_length=50,
        required=False,
    )

    def validate(self, attrs):
        content = attrs.get("content")
        action = attrs.get("action")

        if bool(content) == bool(action):
            raise serializers.ValidationError(
                "Укажите либо текст сообщения, либо действие."
            )
        if (action == "select_apartment") != ("apartment_id" in attrs):
            raise serializers.ValidationError("apartment_id требуется только для явного выбора квартиры.")

        return attrs

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Сообщение не должно быть пустым."
            )
        return value
