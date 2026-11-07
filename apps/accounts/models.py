from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        MANAGER = "manager", "Менеджер"
        REALTOR = "realtor", "Риелтор"
        ADMIN = "admin", "Администратор"

    role = models.CharField(
        "Роль",
        max_length=20,
        choices=Role.choices,
        default=Role.REALTOR,
    )

    agency = models.ForeignKey("accounts.Agency", on_delete=models.PROTECT, null=True, blank=True, related_name="realtors")

    def __str__(self):
        return self.username

class Agency(models.Model):
    name = models.CharField(max_length=200)
    active = models.BooleanField(default=True)
    developers = models.ManyToManyField("catalog.Developer", blank=True, related_name="agencies")

    def __str__(self):
        return self.name


class ClientRegistration(models.Model):
    """Separate B2B identity; never expose or overwrite the shared CRM Contact."""
    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        EXPIRED = "expired", "Истекла"
        CANCELLED = "cancelled", "Отменена"

    developer = models.ForeignKey("catalog.Developer", on_delete=models.PROTECT)
    owner = models.ForeignKey(User, on_delete=models.PROTECT, related_name="registrations")
    agency = models.ForeignKey(Agency, on_delete=models.PROTECT)
    phone_normalized = models.CharField(max_length=11)
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["developer", "phone_normalized"], condition=models.Q(status="active"), name="one_active_realtor_registration"),
            models.CheckConstraint(condition=models.Q(expires_at__gt=models.F("created_at")), name="registration_positive_term"),
        ]

    @property
    def effective_status(self):
        from django.utils import timezone
        if self.status == self.Status.ACTIVE and self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        return self.status


class RegistrationDispute(models.Model):
    class Decision(models.TextChoices):
        APPROVED = "approved", "Фиксация подтверждена"
        REJECTED = "rejected", "Запрос отклонён"
        CANCELLED = "cancelled", "Прежняя фиксация отменена"

    developer = models.ForeignKey("catalog.Developer", on_delete=models.PROTECT)
    requester = models.ForeignKey(User, on_delete=models.PROTECT, related_name="registration_disputes")
    phone_normalized = models.CharField(max_length=11)
    requested_name = models.CharField(max_length=150, blank=True, default="")
    decision = models.CharField(max_length=12, choices=Decision.choices, blank=True, default="")
    approved_registration = models.ForeignKey(ClientRegistration, on_delete=models.PROTECT,
        null=True, blank=True, related_name="approval_disputes")
    reason = models.CharField(max_length=30, choices=[("other_owner", "Действующая фиксация"), ("direct_client", "Прямой клиент CRM")])
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="resolved_registration_disputes")
    resolution = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["developer", "requester", "phone_normalized"], condition=models.Q(resolved_at__isnull=True), name="one_open_registration_dispute")]


class RegistrationAudit(models.Model):
    registration = models.ForeignKey(ClientRegistration, on_delete=models.PROTECT)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Booking(models.Model):
    owner = models.ForeignKey(User, on_delete=models.PROTECT)
    client = models.ForeignKey(ClientRegistration, on_delete=models.PROTECT)
    apartment = models.ForeignKey("catalog.Apartment", on_delete=models.PROTECT, related_name="demo_bookings")
    operation_key = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=12, default="active")

    @property
    def effective_status(self):
        from django.utils import timezone
        return "expired" if self.status == "active" and self.expires_at <= timezone.now() else self.status

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["apartment"], condition=models.Q(status="active"), name="one_active_demo_booking"),
            models.CheckConstraint(condition=models.Q(expires_at__gt=models.F("created_at")), name="booking_positive_term"),
            models.CheckConstraint(condition=models.Q(status__in=["active", "cancelled", "expired"]), name="booking_valid_status"),
        ]


class BookingEvent(models.Model):
    booking = models.ForeignKey(Booking, on_delete=models.PROTECT)
    action = models.CharField(max_length=12)
    created_at = models.DateTimeField(auto_now_add=True)
