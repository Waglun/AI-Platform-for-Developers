from rest_framework import generics
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from apps.accounts.models import User
from apps.leads.models import Lead, LeadComment
from apps.leads.serializers import (
    LeadDetailSerializer,
    LeadListSerializer,
    LeadStatusUpdateSerializer,
    LeadCommentCreateSerializer,
)
from apps.leads.permissions import (
    IsCRMStaff,
    CanChangeLeadStatus,
)
from django.contrib import messages
from django.http import HttpResponseForbidden



class LeadListAPIView(generics.ListAPIView):
    serializer_class = LeadListSerializer
    permission_classes = [IsCRMStaff]

    def get_queryset(self):
        return (
            Lead.objects
            .select_related("contact", "assigned_to")
            .order_by("-created_at")
        )


class LeadDetailAPIView(generics.RetrieveAPIView):
    serializer_class = LeadDetailSerializer
    permission_classes = [IsCRMStaff]

    def get_queryset(self):
        return (
            Lead.objects
            .select_related("contact", "assigned_to")
            .prefetch_related("apartments", "comments__author")
        )


class LeadStatusUpdateAPIView(generics.UpdateAPIView):
    serializer_class = LeadStatusUpdateSerializer
    permission_classes = [CanChangeLeadStatus]
    http_method_names = ["patch", "options", "head"]

    def get_queryset(self):
        return Lead.objects.all()


class LeadCommentCreateAPIView(generics.CreateAPIView):
    serializer_class = LeadCommentCreateSerializer
    permission_classes = [IsCRMStaff]

    def perform_create(self, serializer):
        lead = get_object_or_404(
            Lead,
            pk=self.kwargs["lead_id"],
        )

        serializer.save(
            lead=lead,
            author=self.request.user,
        )


@login_required
def lead_page_list(request):
    leads = (
        Lead.objects
        .select_related("contact", "assigned_to")
        .order_by("-created_at")
    )

    return render(
        request,
        "leads/lead_list.html",
        {"leads": leads},
    )


@login_required
def lead_page_detail(request, pk):
    user = request.user

    if not (
        user.is_superuser
        or user.role in User.Role.values
    ):
        return HttpResponseForbidden("Нет доступа к CRM.")

    lead = get_object_or_404(
        Lead.objects
        .select_related("contact", "assigned_to")
        .prefetch_related("apartments", "comments__author"),
        pk=pk,
    )

    can_change_status = (
        user.is_superuser
        or user.role in [User.Role.MANAGER, User.Role.ADMIN]
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "update_status":
            if not can_change_status:
                return HttpResponseForbidden(
                    "У вас нет прав для изменения статуса."
                )

            new_status = request.POST.get("status")

            if new_status not in Lead.Status.values:
                messages.error(request, "Выбран недопустимый статус.")
            else:
                lead.status = new_status
                lead.save(update_fields=["status", "updated_at"])
                messages.success(request, "Статус заявки обновлён.")

            return redirect("crm-lead-detail", pk=lead.pk)

        if action == "add_comment":
            text = request.POST.get("text", "").strip()

            if not text:
                messages.error(request, "Введите текст комментария.")
            else:
                LeadComment.objects.create(
                    lead=lead,
                    author=user,
                    text=text,
                )
                messages.success(request, "Комментарий добавлен.")

            return redirect("crm-lead-detail", pk=lead.pk)

    requirement_labels = {
        "rooms": "Количество комнат",
        "min_area": "Площадь от, м²",
        "max_area": "Площадь до, м²",
        "min_price": "Цена от, ₽",
        "max_price": "Цена до, ₽",
    }

    requirements_display = [
        {
            "label": requirement_labels.get(key, key),
            "value": value,
        }
        for key, value in lead.requirements.items()
    ]

    return render(
        request,
        "leads/lead_detail.html",
        {
            "lead": lead,
            "can_change_status": can_change_status,
            "status_choices": Lead.Status.choices,
            "requirements_display": requirements_display,
        },
    )