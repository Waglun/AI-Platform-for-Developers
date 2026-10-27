import uuid

from django.db import models


class Conversation(models.Model):
    """Диалог посетителя с AI-консультантом."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Активен"
        COMPLETED = "completed", "Завершён"
        HANDED_OFF = "handed_off", "Передан менеджеру"

    # Идентификатор конкретного диалога
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # Идентификатор анонимного посетителя.
    # Один посетитель потенциально может иметь несколько диалогов.
    visitor_id = models.UUIDField(
        "Идентификатор посетителя",
        default=uuid.uuid4,
        db_index=True,
    )

    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    # Заявка появляется только после передачи контактов в CRM.
    lead = models.ForeignKey(
        "leads.Lead",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
        verbose_name="Заявка CRM",
    )

    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Диалог"
        verbose_name_plural = "Диалоги"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Диалог {self.id} ({self.get_status_display()})"


class Message(models.Model):
    """Отдельное сообщение внутри диалога."""

    class Role(models.TextChoices):
        VISITOR = "visitor", "Посетитель"
        ASSISTANT = "assistant", "Ассистент"
        SYSTEM = "system", "Система"
        MANAGER = "manager", "Менеджер"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name="Диалог",
    )

    role = models.CharField(
        "Отправитель",
        max_length=20,
        choices=Role.choices,
    )

    content = models.TextField("Текст сообщения")

    # Дополнительные данные: например, ID квартир для карточек
    # или код выбранного действия.
    metadata = models.JSONField(
        "Дополнительные данные",
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Сообщение"
        verbose_name_plural = "Сообщения"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.get_role_display()}: {self.content[:50]}"