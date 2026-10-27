from django.urls import path

from apps.leads.views import (
    LeadListAPIView,
    LeadDetailAPIView,
    LeadStatusUpdateAPIView,
    LeadCommentCreateAPIView,
    lead_page_list,
    lead_page_detail,
)

urlpatterns = [
    path("", LeadListAPIView.as_view(), name="lead-list"),
    path("<int:pk>/", LeadDetailAPIView.as_view(), name="lead-detail"),
    path("<int:pk>/status/", LeadStatusUpdateAPIView.as_view(), name="lead-status-update"),
    path("<int:lead_id>/comments/", LeadCommentCreateAPIView.as_view(), name="lead-comment-create"),
    path("crm/", lead_page_list, name="crm-lead-list"),
    path("crm/<int:pk>/", lead_page_detail, name="crm-lead-detail"),
]