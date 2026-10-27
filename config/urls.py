from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path("api/", include("apps.catalog.urls")),
    path("api/leads/", include("apps.leads.urls")),
    path("api-auth/", include("rest_framework.urls")),
    path("api/chat/", include("apps.chat.urls")),
]
