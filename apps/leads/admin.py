from django.contrib import admin
from django.db import transaction

from .models import Contact, Lead, LeadComment, CRMDelivery
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

    @transaction.atomic
    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        lead = form.instance
        # Django changeform wraps save_model/save_related in one transaction.
        CRMDelivery.objects.get_or_create(lead=lead, defaults={"payload": {
            "lead_id": lead.pk, "name": lead.contact.name, "phone": lead.contact.phone_normalized,
            "email": lead.contact.email, "requirements": lead.requirements,
            "apartment_ids": list(lead.apartments.values_list("pk", flat=True)),
            "source": lead.source, "budget_min": str(lead.budget_min), "budget_max": str(lead.budget_max),
        }})


@admin.register(LeadComment)
class LeadCommentAdmin(CRMAdminAccessMixin, admin.ModelAdmin):
    list_display = ("id", "lead", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("text", "lead__contact__name")
    readonly_fields = ("created_at",)