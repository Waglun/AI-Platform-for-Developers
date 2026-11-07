import json
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.renderers import JSONRenderer
from rest_framework.views import APIView

from apps.chat.llm.base import LLMClient, LLMError, build_messages, redact
from apps.chat.context import normalize_context
from apps.chat.models import ChatRequest, Conversation, Message
from apps.chat.serializers import MessageSerializer, SendMessageSerializer
from apps.chat.services import get_apartment_results

SESSION_VISITOR_KEY = "chat_visitor_id"
SUGGESTIONS = ["Подобрать квартиру", "О жилом комплексе", "Записаться на показ"]
ACTION_TEXT = dict(zip(["apartment_search", "complex_info", "showing"], SUGGESTIONS))
ACTION_TEXT.update({
    "show_more": "Показать ещё", "change_filters": "Изменить параметры",
    "location": "Расположение", "infrastructure": "Инфраструктура",
    "buildings": "Дома и сроки сдачи", "purchase_terms": "Условия покупки",
    "selected_apartment": "Квартира уже выбрана", "need_apartment": "Помогите выбрать",
    "budget_any": "Рассмотрю разные варианты", "area_any": "Любая площадь",
})
ACTION_UPDATES = {}
for rooms in range(1, 5):
    key = f"rooms_{rooms}"
    ACTION_TEXT[key] = f"Количество комнат: {rooms}" + ("+" if rooms == 4 else "")
    ACTION_UPDATES[key] = {"rooms": rooms}
for budget in (5, 8, 10):
    key = f"budget_{budget}"
    ACTION_TEXT[key] = f"До {budget} млн ₽"
    ACTION_UPDATES[key] = {"budget": budget * 1_000_000}
ACTION_UPDATES["budget_any"] = {"budget": None}
ACTION_UPDATES["area_any"] = {"min_area": None, "max_area": None}
for low, high in [(40, 45), (45, 50), (50, None), (60, 65), (65, 70),
                  (70, None), (60, 70), (70, 85), (85, None)]:
    key = f"area_{low}_{high if high else 'plus'}"
    ACTION_TEXT[key] = f"Площадь: от {low}" + (f" до {high}" if high else "") + " м²"
    ACTION_UPDATES[key] = {"min_area": low, "max_area": high}


def get_visitor_id(request):
    try:
        return uuid.UUID(str(request.session.get(SESSION_VISITOR_KEY)))
    except (ValueError, TypeError, AttributeError):
        visitor_id = uuid.uuid4()
        request.session[SESSION_VISITOR_KEY] = str(visitor_id)
        return visitor_id


def upgrade(conversation):
    context = normalize_context(conversation.context)
    if context != conversation.context:
        conversation.context = context
        conversation.save(update_fields=["context"])


def snapshot(conversation):
    return {
        "conversation_id": str(conversation.pk), "status": conversation.status,
        "context": conversation.context,
        "messages": MessageSerializer(conversation.messages.all(), many=True).data,
    }


class ChatStartAPIView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        visitor_id = get_visitor_id(request)
        conversation = Conversation.objects.select_for_update().filter(
            visitor_id=visitor_id, status=Conversation.Status.ACTIVE,
        ).first()
        if conversation is None:
            conversation = Conversation.objects.create(
                visitor_id=visitor_id, context=normalize_context({}),
            )
            Message.objects.create(
                conversation=conversation, role=Message.Role.ASSISTANT,
                content="Здравствуйте! Я ИИ-консультант ЖК «Сибиряков». Чем могу помочь?",
                metadata={"type": "welcome", "suggestions": SUGGESTIONS},
            )
        upgrade(conversation)
        return Response(snapshot(conversation))


class ChatMessagesAPIView(APIView):
    permission_classes = [AllowAny]

    def owned(self, request, conversation_id):
        return get_object_or_404(
            Conversation.objects.select_for_update(), pk=conversation_id,
            visitor_id=get_visitor_id(request),
        )

    @transaction.atomic
    def get(self, request, conversation_id):
        conversation = self.owned(request, conversation_id)
        upgrade(conversation)
        return Response(snapshot(conversation))

    def post(self, request, conversation_id):
        prepared = self.prepare(request, conversation_id)
        if isinstance(prepared, Response):
            return prepared
        conversation, operation, messages = prepared
        try:
            reply = LLMClient().complete(messages)
            reply = redact(reply, conversation.context)
            metadata = {"type": "llm_reply"}
        except LLMError as exc:
            reply, metadata = failure(exc.code)
        with transaction.atomic():
            conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
            operation.refresh_from_db()
            if operation.result:
                return Response(operation.result)
            return Response(finish(conversation, operation, reply, metadata))

    @transaction.atomic
    def prepare(self, request, conversation_id):
        conversation = self.owned(request, conversation_id)
        if conversation.status != Conversation.Status.ACTIVE:
            return Response({"detail": "Этот диалог уже не активен."}, status=400)
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        request_id = data["request_id"]
        payload = {key: value for key, value in data.items() if key != "request_id"}
        previous = ChatRequest.objects.filter(
            conversation=conversation, request_id=request_id,
        ).first()
        pending = ChatRequest.objects.filter(conversation=conversation, result={}).first()
        if pending and pending.started_at < timezone.now() - timedelta(
                seconds=2 * settings.LLM_TIMEOUT_SECONDS + 30):
            finish(conversation, pending, *failure("interrupted"))
            if previous and previous.pk == pending.pk:
                previous.refresh_from_db()
            pending = None
        if previous:
            if previous.payload != payload:
                return Response({"detail": "request_id уже использован с другими данными."}, status=409)
            if not previous.result:
                return Response({"request_id": str(request_id), "processing": {"status": "processing"}}, status=202)
            return Response(previous.result)
        if pending:
            return Response({"detail": "Предыдущее сообщение ещё обрабатывается. Повторите позже."}, status=409)
        action = data.get("action")
        if action is not None and action not in ACTION_TEXT:
            return Response({"detail": "Неизвестное действие."}, status=400)
        upgrade(conversation)
        context = conversation.context
        text = data.get("content") or ACTION_TEXT[action]
        if action in ACTION_UPDATES:
            context["preferences"].update(ACTION_UPDATES[action])
            context["last_search"] = {"page": 1, "apartment_ids": []}
        Message.objects.create(
            conversation=conversation, role=Message.Role.VISITOR, content=text,
            metadata={"request_id": str(request_id), **({"legacy_action": action} if action else {})},
        )
        if action != "show_more" and settings.LLM_ENABLED:
            operation = ChatRequest.objects.create(
                conversation=conversation, request_id=request_id, payload=payload, result={},
            )
            conversation.save(update_fields=["context", "updated_at"])
            if ChatRequest.objects.filter(conversation=conversation).count() > settings.LLM_MAX_CALLS_PER_CONVERSATION:
                return Response(finish(conversation, operation, *failure("budget_exhausted")))
            return conversation, operation, build_messages(conversation)
        outcome = "saved_not_processed"
        reply = "Сообщение сохранено. ИИ-консультант ещё не подключён; консультация и отправка заявки пока недоступны."
        metadata = {"type": outcome}
        if action == "show_more":
            last = context["last_search"]
            results = get_apartment_results(context["preferences"], page=last["page"] + 1)
            if results["page_count"]:
                context["last_search"] = {
                    "page": results["page"], "apartment_ids": results["apartment_ids"],
                }
                reply = results["content"]
            else:
                reply = "Больше подходящих квартир нет."
            outcome = "catalog_page"
            metadata = {"type": outcome, **{k: v for k, v in results.items() if k != "content"}}
        Message.objects.create(conversation=conversation, role=Message.Role.ASSISTANT,
                               content=reply, metadata=metadata)
        conversation.save(update_fields=["context", "updated_at"])
        result = snapshot(conversation)
        result.update(request_id=str(request_id), processing={"status": outcome})
        # JSON-safe durable response, including timestamp strings.
        result = json.loads(JSONRenderer().render(result))
        ChatRequest.objects.create(conversation=conversation, request_id=request_id,
                                   payload=payload, result=result)
        return Response(result)


def failure(code):
    return (
        "ИИ-консультант сейчас недоступен. Сообщение сохранено. "
        "Вы можете повторить обращение позже; заявка не отправлена.",
        {"type": "llm_error", "code": code, "contact_form": {"available": False, "requested": True}},
    )


def finish(conversation, operation, reply, metadata):
    # Caller holds the conversation lock; a late worker cannot append a second answer.
    Message.objects.create(conversation=conversation, role=Message.Role.ASSISTANT,
                           content=reply, metadata=metadata)
    conversation.save(update_fields=["updated_at"])
    result = snapshot(conversation)
    result.update(request_id=str(operation.request_id), processing={"status": metadata["type"]})
    operation.result = json.loads(JSONRenderer().render(result))
    operation.save(update_fields=["result"])
    return operation.result
