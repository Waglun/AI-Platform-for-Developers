from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Agency, ClientRegistration, RegistrationAudit, RegistrationDispute, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Роль в платформе", {"fields": ("role", "agency")}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Роль в платформе", {"fields": ("role", "agency")}),
    )

    list_display = (
        "username",
        "email",
        "role",
        "is_staff",
        "is_active",
    )

    list_filter = UserAdmin.list_filter + ("role", "agency")

@admin.register(Agency)
class AgencyAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    filter_horizontal = ("developers",)

    def has_module_permission(self, request):
        from apps.leads.permissions import can_access_crm
        return can_access_crm(request.user) and super().has_module_permission(request)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request) and super().has_view_permission(request, obj)

    def has_add_permission(self, request):
        return self.has_module_permission(request) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request) and super().has_delete_permission(request, obj)


class ReadOnlyRegistrationAdmin(AgencyAdmin):
    list_display = ("pk",)
    filter_horizontal = ()

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(ClientRegistration, ReadOnlyRegistrationAdmin)
admin.site.register(RegistrationDispute, ReadOnlyRegistrationAdmin)
admin.site.register(RegistrationAudit, ReadOnlyRegistrationAdmin)
