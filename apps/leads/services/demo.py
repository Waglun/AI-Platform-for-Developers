import hashlib
import json
import re

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError

from apps.catalog.search import available_apartments
from apps.leads.models import Contact, Lead, LeadComment, CRMDelivery

from .base import CRMClient


def normalize_phone(phone: str) -> str:
    """Привести российский номер к формату 7XXXXXXXXXX."""
    digits = re.sub(r"\D", "", phone or "")

    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits

    if len(digits) != 11 or not digits.startswith("7"):
        raise ValueError(
            "Укажите корректный российский номер телефона."
        )

    return digits


class IdempotencyConflict(APIException):
    status_code = 409
    default_detail = "Конфликт ключа операции."
    default_code = "idempotency_conflict"


class LeadOperationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=30)
    email = serializers.EmailField(default="", allow_blank=True)
    budget_min = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, default=None, allow_null=True)
    budget_max = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0, default=None, allow_null=True)
    requirements = serializers.JSONField(default=dict)
    source = serializers.ChoiceField(choices=Lead.Source.choices, default=Lead.Source.WEBSITE_CHAT)
    apartment_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), default=list)
    idempotency_key = serializers.CharField(max_length=100, default="", allow_blank=True, allow_null=True)

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("Неизвестные поля операции.")
        if not isinstance(attrs["requirements"], dict):
            raise serializers.ValidationError({"requirements": "Ожидается объект требований."})
        low, high = attrs["budget_min"], attrs["budget_max"]
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError("Нижняя граница бюджета превышает верхнюю.")
        return attrs


class DemoCRMClient(CRMClient):
    def find_contact(self, phone: str):
        normalized = normalize_phone(phone)

        return Contact.objects.filter(
            phone_normalized=normalized
        ).first()

    def create_lead(self, data: dict):
        serializer = LeadOperationSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        operation = serializer.validated_data
        operation["phone"] = normalize_phone(operation["phone"])
        operation["apartment_ids"] = sorted(set(operation["apartment_ids"]))
        key = operation.pop("idempotency_key") or None
        canonical = {**operation, "complex": settings.CATALOG_COMPLEX_EXTERNAL_ID}
        fingerprint = hashlib.sha256(json.dumps(
            canonical, sort_keys=True, ensure_ascii=False, default=str,
            allow_nan=False, separators=(",", ":"),
        ).encode()).hexdigest()

        def replay(lead):
            if not lead.operation_fingerprint:
                raise IdempotencyConflict("Исходные данные старой операции неизвестны; используйте новый ключ.")
            if lead.operation_fingerprint != fingerprint:
                raise IdempotencyConflict("Ключ операции уже использован с другими данными.")
            return lead

        if key:
            existing = Lead.objects.filter(idempotency_key=key).first()
            if existing:
                return replay(existing)
        try:
            with transaction.atomic():
                # get_or_create handles a concurrent insert using the unique phone.
                contact, _ = Contact.objects.get_or_create(
                    phone_normalized=operation["phone"],
                    defaults={"name": operation["name"], "phone": operation["phone"],
                              "email": operation["email"]},
                )
                contact = Contact.objects.select_for_update().get(pk=contact.pk)
                # A same-phone operation may have completed while we waited.
                if key:
                    existing = Lead.objects.filter(idempotency_key=key).first()
                    if existing:
                        return replay(existing)
                ids = operation["apartment_ids"]
                if set(available_apartments().filter(pk__in=ids).values_list("pk", flat=True)) != set(ids):
                    raise ValidationError({"apartment_ids": "Выбранные квартиры недоступны или вне разрешённого ЖК."})
                for field in ("name", "email"):
                    if operation[field]:
                        setattr(contact, field, operation[field])
                contact.phone = operation["phone"]
                contact.save()
                lead = Lead.objects.create(
                    contact=contact, idempotency_key=key, operation_fingerprint=fingerprint,
                    **{field: operation[field] for field in
                       ("budget_min", "budget_max", "requirements", "source")},
                )
                lead.apartments.set(ids)
                CRMDelivery.objects.create(lead=lead, payload={**json.loads(json.dumps(operation, default=str)), "lead_id": lead.pk})
                return lead
        except IntegrityError:
            # The entire losing operation (including contact changes) is rolled back.
            if key:
                existing = Lead.objects.filter(idempotency_key=key).first()
                if existing:
                    return replay(existing)
            raise

    @transaction.atomic
    def add_comment(self, lead_id: int, text: str):
        text = text.strip()
        if not text:
            raise ValueError("Комментарий не может быть пустым.")

        lead = Lead.objects.get(pk=lead_id)

        return LeadComment.objects.create(
            lead=lead,
            text=text,
        )