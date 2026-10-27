import re
from django.db import transaction

from apps.catalog.models import Apartment
from apps.leads.models import Contact, Lead, LeadComment

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


class DemoCRMClient(CRMClient):
    def find_contact(self, phone: str):
        normalized = normalize_phone(phone)

        return Contact.objects.filter(
            phone_normalized=normalized
        ).first()

    @transaction.atomic
    def create_lead(self, data: dict):
        key = data.get("idempotency_key")

        # Повтор той же операции не должен создавать новую заявку.
        if key:
            existing_lead = Lead.objects.filter(
                idempotency_key=key
            ).first()

            if existing_lead:
                return existing_lead

        normalized_phone = normalize_phone(data["phone"])

        contact = Contact.objects.filter(
            phone_normalized=normalized_phone
        ).first()

        if contact is None:
            contact = Contact.objects.create(
                name=data["name"].strip(),
                phone=data["phone"],
                phone_normalized=normalized_phone,
                email=data.get("email", "").strip(),
            )
        else:
            # Обновляем контакт только непустыми новыми данными.
            if data.get("name", "").strip():
                contact.name = data["name"].strip()

            if data.get("email", "").strip():
                contact.email = data["email"].strip()

            contact.phone = data["phone"]
            contact.save()

        lead = Lead.objects.create(
            contact=contact,
            budget_min=data.get("budget_min"),
            budget_max=data.get("budget_max"),
            requirements=data.get("requirements") or {},
            source=data.get("source", Lead.Source.WEBSITE_CHAT),
            idempotency_key=key or None,
        )

        apartment_ids = data.get("apartment_ids", [])
        if apartment_ids:
            apartments = Apartment.objects.filter(
                id__in=apartment_ids
            )
            lead.apartments.set(apartments)

        return lead

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