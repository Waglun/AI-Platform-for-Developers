from django.urls import path

from apps.catalog.views import ApartmentListAPIView, ApartmentDetailAPIView

urlpatterns = [
    path("apartments/", ApartmentListAPIView.as_view(), name="apartment-list",),
    path("apartments/<int:pk>/", ApartmentDetailAPIView.as_view(), name="apartment-detail",),
]