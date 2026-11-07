from django.conf import settings
from django.db import models


class Contact(models.Model):
    name = models.CharField(
        "Имя",
        max_length=150,
    )
    phone = models.CharField(
        "Телефон",
        max_length=30,
    )
    phone_normalized = models.CharField(
        "Нормализованный телефон",
        max_length=20,
        unique=True,
    )
    email = models.EmailField(
        "Email",
        blank=True,
    )
    created_at = models.DateTimeField(
        "Создан",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "Обновлён",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Контакт"
        verbose_name_plural = "Контакты"

    def __str__(self):
        return f"{self.name} — {self.phone}"


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новая"
        IN_PROGRESS = "in_progress", "В работе"
        QUALIFIED = "qualified", "Квалифицирована"
        WON = "won", "Успешная"
        LOST = "lost", "Неуспешная"

    class Source(models.TextChoices):
        WEBSITE_CHAT = "website_chat", "Чат на сайте"
        WEBSITE_FORM = "website_form", "Форма на сайте"
        REALTOR = "realtor", "Риелтор"
        MANUAL = "manual", "Создана вручную"

    contact = models.ForeignKey(
        Contact,
        on_delete=models.PROTECT,
        related_name="leads",
        verbose_name="Контакт",
    )
    apartments = models.ManyToManyField(
        "catalog.Apartment",
        blank=True,
        related_name="leads",
        verbose_name="Выбранные квартиры",
    )
    budget_min = models.DecimalField(
        "Бюджет от",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    budget_max = models.DecimalField(
        "Бюджет до",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    requirements = models.JSONField(
        "Требования клиента",
        default=dict,
        blank=True,
    )
    source = models.CharField(
        "Источник",
        max_length=30,
        choices=Source.choices,
        default=Source.WEBSITE_CHAT,
    )
    status = models.CharField(
        "Статус",
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_leads",
        verbose_name="Ответственный менеджер",
    )
    idempotency_key = models.CharField(
        "Ключ операции",
        max_length=100,
        unique=True,
        null=True,
        blank=True,
    )
    operation_fingerprint = models.CharField(
        "Отпечаток исходной операции", max_length=64, blank=True, editable=False,
    )
    created_at = models.DateTimeField(
        "Создана",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "Обновлена",
        auto_now=True,
    )

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Заявка №{self.pk} — {self.contact.name}"


class LeadComment(models.Model):
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="Заявка",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_comments",
        verbose_name="Автор",
    )
    text = models.TextField("Комментарий")
    created_at = models.DateTimeField(
        "Создан",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Комментарий к заявке"
        verbose_name_plural = "Комментарии к заявкам"
        ordering = ["created_at"]

    def __str__(self):
        return f"Комментарий к заявке №{self.lead_id}"