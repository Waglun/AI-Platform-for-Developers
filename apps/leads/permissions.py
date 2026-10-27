from rest_framework.permissions import BasePermission

from apps.accounts.models import User


class IsCRMStaff(BasePermission):
    """Доступ к CRM для менеджеров, риелторов и администраторов."""

    def has_permission(self, request, view):
        user = request.user

        return (
            user.is_authenticated
            and (
                user.is_superuser
                or user.role in User.Role.values
            )
        )


class CanChangeLeadStatus(BasePermission):
    """Менять статус могут менеджеры и администраторы."""

    def has_permission(self, request, view):
        user = request.user

        return (
            user.is_authenticated
            and (
                user.is_superuser
                or user.role in [
                    User.Role.MANAGER,
                    User.Role.ADMIN,
                ]
            )
        )