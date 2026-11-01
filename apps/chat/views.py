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
from apps.chat.services import (
    start_scenario,
    process_scenario_action,
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
                context={
                    "mode": "menu",
                    "flow": None,
                    "step": None,
                    "answers": {},
                },
            )

            Message.objects.create(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=(
                    "Здравствуйте! Я ИИ-консультант ЖК «Сибиряков». "
                    "Чем могу помочь?"
                ),
                metadata={
                    "type": "welcome",
                    "actions": [
                        {
                            "id": "apartment_search",
                            "label": "Подобрать квартиру",
                        },
                        {
                            "id": "complex_info",
                            "label": "О жилом комплексе",
                        },
                        {
                            "id": "showing",
                            "label": "Записаться на показ",
                        },
                    ],
                },
            )

        messages = conversation.messages.order_by(
            "created_at",
            "id",
        )

        return Response({
            "conversation_id": str(conversation.id),
            "context": conversation.context,
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
            "context": conversation.context,
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

        data = serializer.validated_data

        # Обработка нажатия кнопки
        if "action" in data:
            action = data["action"]

            action_labels = {
                "apartment_search": "Подобрать квартиру",
                "complex_info": "О жилом комплексе",
                "showing": "Записаться на показ",
                "rooms_1": "1 комната",
                "rooms_2": "2 комнаты",
                "rooms_3": "3 комнаты",
                "rooms_4": "4+ комнаты",
                "budget_5": "До 5 млн ₽",
                "budget_8": "До 8 млн ₽",
                "budget_10": "До 10 млн ₽",
                "budget_any": "Рассмотрю разные варианты",
                "area_40_45": "40–45 м²",
                "area_45_50": "45–50 м²",
                "area_50_plus": "От 50 м²",
                "area_60_65": "60–65 м²",
                "area_65_70": "65–70 м²",
                "area_70_plus": "От 70 м²",
                "area_60_70": "60–70 м²",
                "area_70_85": "70–85 м²",
                "area_85_plus": "От 85 м²",
                "area_any": "Любая площадь",
            }

            if action not in action_labels:
                return Response(
                    {"detail": "Неизвестное действие."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            Message.objects.create(
                conversation=conversation,
                role=Message.Role.VISITOR,
                content=action_labels[action],
                metadata={
                    "type": "action",
                    "action": action,
                },
            )

            if action in (
                    "apartment_search",
                    "complex_info",
                    "showing",
            ):
                start_scenario(conversation, action)

            else:
                result = process_scenario_action(conversation, action)

                if result is None:
                    return Response(
                        {"detail": "Действие недоступно на текущем шаге сценария."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])

        messages = conversation.messages.order_by(
            "created_at",
            "id",
        )

        return Response({
            "conversation_id": str(conversation.id),
            "context": conversation.context,
            "messages": MessageSerializer(
                messages,
                many=True,
            ).data,
        })