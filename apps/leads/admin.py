from django.contrib import admin

from .models import Contact, Lead, LeadComment
from .permissions import can_access_crm


class CRMAdminAccessMixin:
    def has_module_permission(self, request):
        return can_access_crm(request.user) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return can_access_crm(request.user) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return can_access_crm(request.user) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return can_access_crm(request.user) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return can_access_crm(request.user) and super().has_delete_permission(request, obj)


@admin.register(Contact)
class ContactAdmin(CRMAdminAccessMixin, admin.ModelAdmin):
    list_display = ("id", "name", "phone", "email", "created_at")
    search_fields = ("name", "phone", "phone_normalized", "email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Lead)
class LeadAdmin(CRMAdminAccessMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "contact",
        "status",
        "source",
        "assigned_to",
        "created_at",
    )
    list_filter = ("status", "source", "created_at")
    search_fields = (
        "contact__name",
        "contact__phone",
        "contact__phone_normalized",
    )
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("apartments",)


@admin.register(LeadComment)
class LeadCommentAdmin(CRMAdminAccessMixin, admin.ModelAdmin):
    list_display = ("id", "lead", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("text", "lead__contact__name")
    readonly_fields = ("created_at",)