from django.contrib import admin

from .models import Contact, Lead, LeadComment


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "email", "created_at")
    search_fields = ("name", "phone", "phone_normalized", "email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
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
class LeadCommentAdmin(admin.ModelAdmin):
    list_display = ("id", "lead", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("text", "lead__contact__name")
    readonly_fields = ("created_at",)