from rest_framework.permissions import BasePermission

from apps.accounts.models import User


def can_access_crm(user):
    return bool(
        user.is_authenticated and user.is_active
        and (user.is_superuser or user.role in [User.Role.MANAGER, User.Role.ADMIN])
    )


class IsCRMStaff(BasePermission):
    """Общая CRM доступна менеджерам и администраторам."""

    def has_permission(self, request, view):
        return can_access_crm(request.user)


class CanChangeLeadStatus(IsCRMStaff):
    """Изменение статуса использует те же права, что и CRM."""
