from django.urls import path

from apps.chat.views import (
    ChatMessagesAPIView,
    ChatStartAPIView,
)


urlpatterns = [
    path("start/", ChatStartAPIView.as_view(), name="chat-start"),
    path(
        "<uuid:conversation_id>/messages/",
        ChatMessagesAPIView.as_view(),
        name="chat-messages",
    ),
]