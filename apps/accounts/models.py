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

    def __str__(self):
        return self.username