from django.contrib import admin
from django.contrib.auth.views import LogoutView
from django.urls import include, path

from apps.chat.demo import demo_chat, developer_demo
from apps.chat.widget import widget_page
from apps.accounts.views import PlatformLoginView, home
from config.observability import readiness

urlpatterns = [
    path("health/ready/", readiness, name="readiness"),
    path("widget/", widget_page, name="chat-widget"),
    path("accounts/logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("accounts/home/", home, name="account-home"),
    path("realtor/", include("apps.accounts.urls")),
    path('accounts/login/', PlatformLoginView.as_view(), name='login'),
    path("demo/", demo_chat, name="chat-demo"),
    path("developer-demo/", developer_demo, name="developer-demo"),
    path('admin/', admin.site.urls),
    path("api/", include("apps.catalog.urls")),
    path("api/leads/", include("apps.leads.urls")),
    path("api-auth/", include("rest_framework.urls")),
    path("api/chat/", include("apps.chat.urls")),
]
