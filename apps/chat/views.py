import uuid

from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat.models import Conversation, Message
from apps.chat.serializers import (
    MessageSerializer,
    SendMessageSerializer,
)


SESSION_VISITOR_KEY = "chat_visitor_id"


def get_visitor_id(request):
    """Получает или создаёт анонимный ID посетителя."""
    visitor_id = request.session.get(SESSION_VISITOR_KEY)

    try:
        visitor_id = uuid.UUID(str(visitor_id))
    except (ValueError, TypeError, AttributeError):
        visitor_id = uuid.uuid4()
        request.session[SESSION_VISITOR_KEY] = str(visitor_id)

    return visitor_id


class ChatStartAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        visitor_id = get_visitor_id(request)

        conversation = (
            Conversation.objects
            .filter(
                visitor_id=visitor_id,
                status=Conversation.Status.ACTIVE,
            )
            .order_by("-updated_at")
            .first()
        )

        if conversation is None:
            conversation = Conversation.objects.create(
                visitor_id=visitor_id,
            )

        messages = conversation.messages.order_by(
            "created_at",
            "id",
        )

        return Response({
            "conversation_id": str(conversation.id),
            "status": conversation.status,
            "messages": MessageSerializer(
                messages,
                many=True,
            ).data,
        })


class ChatMessagesAPIView(APIView):
    permission_classes = [AllowAny]

    def get_conversation(self, request, conversation_id):
        visitor_id = get_visitor_id(request)

        return get_object_or_404(
            Conversation,
            id=conversation_id,
            visitor_id=visitor_id,
        )

    def get(self, request, conversation_id):
        conversation = self.get_conversation(
            request,
            conversation_id,
        )

        messages = conversation.messages.order_by(
            "created_at",
            "id",
        )

        return Response({
            "conversation_id": str(conversation.id),
            "messages": MessageSerializer(
                messages,
                many=True,
            ).data,
        })

    def post(self, request, conversation_id):
        conversation = self.get_conversation(
            request,
            conversation_id,
        )

        if conversation.status != Conversation.Status.ACTIVE:
            return Response(
                {"detail": "Этот диалог уже не активен."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        content = serializer.validated_data["content"]

        Message.objects.create(
            conversation=conversation,
            role=Message.Role.VISITOR,
            content=content,
        )

        # Временный ответ для проверки механизма чата.
        # Позже здесь появится сценарий подбора и вызов ИИ.
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=(
                "Спасибо за сообщение! Сейчас я работаю "
                "в демонстрационном режиме. Скоро смогу "
                "помочь подобрать квартиру."
            ),
        )

        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])

        messages = conversation.messages.order_by(
            "created_at",
            "id",
        )

        return Response({
            "conversation_id": str(conversation.id),
            "messages": MessageSerializer(
                messages,
                many=True,
            ).data,
        })