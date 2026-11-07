from django.urls import path

from apps.chat.views import (
    ChatMessagesAPIView,
    ChatStartAPIView,
)


from apps.chat.handoff import contact_page


urlpatterns = [
    path("<uuid:conversation_id>/contact/", contact_page, name="chat-contact"),
    path("start/", ChatStartAPIView.as_view(), name="chat-start"),
    path(
        "<uuid:conversation_id>/messages/",
        ChatMessagesAPIView.as_view(),
        name="chat-messages",
    ),
]