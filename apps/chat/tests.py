import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.chat.context import normalize_context
from apps.chat.models import ChatRequest, Conversation, Message
from apps.chat.services import get_apartment_results
from apps.catalog.importer import import_feed
from apps.catalog.test_sprint1 import feed
from django.utils import timezone


class ChatTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.start = self.client.post("/api/chat/start/", {}, format="json").data
        self.conversation = Conversation.objects.get(pk=self.start["conversation_id"])
        self.url = f"/api/chat/{self.conversation.pk}/messages/"

    def send(self, **kwargs):
        return self.client.post(self.url, {"request_id": str(uuid.uuid4()), **kwargs}, format="json")

    def test_save_and_replay_and_conflict(self):
        payload = {"request_id": str(uuid.uuid4()), "content": "Двухкомнатная до 15 млн"}
        first = self.client.post(self.url, payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["processing"]["status"], "saved_not_processed")
        self.assertEqual(Message.objects.filter(role="visitor", content=payload["content"]).count(), 1)
        self.assertEqual(self.client.post(self.url, payload, format="json").data, first.data)
        payload["content"] = "Другой бюджет"
        self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 409)
        self.assertEqual(self.conversation.messages.count(), 3)

    def test_session_and_closed(self):
        stranger = APIClient()
        self.assertEqual(stranger.get(self.url).status_code, 404)
        self.assertEqual(stranger.post(self.url, {"content": "test"}, format="json").status_code, 404)
        for state in ["completed", "handed_off"]:
            self.conversation.status = state
            self.conversation.save()
            self.assertEqual(self.send(content="test").status_code, 400)
        self.assertEqual(self.conversation.messages.count(), 1)

    def test_validation_without_side_effects(self):
        self.assertEqual(self.client.post(self.url, {"content": "test"}, format="json").status_code, 400)
        for data in [{"content": " "}, {"action": "unknown"},
                     {"content": "test", "action": "showing"}]:
            self.assertEqual(self.send(**data).status_code, 400)
        self.assertEqual(self.conversation.messages.count(), 1)
        self.assertEqual(ChatRequest.objects.count(), 0)

    def test_legacy_context_and_actions(self):
        old = {"mode": "scenario", "flow": "apartment_search", "step": "results",
               "answers": {"rooms": 2, "budget": 15000000, "page": 1,
                           "name": "Test", "phone": "test-contact", "wish": "парк"}}
        self.conversation.context = old
        self.conversation.save()
        loaded = self.client.get(self.url).data["context"]
        self.assertEqual(loaded["legacy"], old)
        self.assertEqual(loaded["contact"]["phone"], "test-contact")
        self.assertEqual(loaded["preferences"]["wish"], "парк")
        self.assertEqual(normalize_context(loaded), loaded)
        for action in ["apartment_search", "complex_info", "showing", "change_filters", "rooms_3"]:
            response = self.send(action=action)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data["context"]["mode"], "free")
            self.assertEqual(response.data["context"]["contact"], loaded["contact"])
        self.assertEqual(response.data["context"]["preferences"]["rooms"], 3)
        self.assertNotIn("actions", response.data["messages"][-1]["metadata"])

    def test_start_resume_preserves_context(self):
        self.send(content="Пожелание")
        resumed = self.client.post("/api/chat/start/", {}, format="json").data
        self.assertEqual(resumed["conversation_id"], self.start["conversation_id"])
        self.assertEqual(len(resumed["messages"]), 3)
        self.assertEqual(self.start["messages"][0]["metadata"]["suggestions"][0], "Подобрать квартиру")

    def test_pagination_end(self):
        import_feed(feed(), observed_at=timezone.now())
        first = get_apartment_results({}, page=1, page_size=2)
        second = get_apartment_results({}, page=2, page_size=2)
        end = get_apartment_results({}, page=3, page_size=2)
        self.assertEqual((first["page_count"], first["has_more"]), (2, True))
        self.assertEqual((second["page_count"], second["has_more"]), (1, False))
        self.assertEqual((end["page_count"], end["has_more"]), (0, False))
        self.conversation.context = {"mode": "scenario", "flow": "apartment_search",
                                     "step": "results", "answers": {"page": 1}}
        self.conversation.save()
        response = self.send(action="show_more")
        self.assertEqual(response.data["messages"][-1]["content"], "Больше подходящих квартир нет.")
        self.assertEqual(response.data["context"]["last_search"]["page"], 1)


class ConcurrentChatTests(TransactionTestCase):
    def test_serialized_messages_and_duplicate(self):
        client = APIClient()
        start = client.post("/api/chat/start/", {}, format="json").data
        url = f"/api/chat/{start['conversation_id']}/messages/"
        cookies = client.cookies
        for duplicate in (True, False):
            barrier = Barrier(2)
            shared_id = str(uuid.uuid4())

            def send(index):
                close_old_connections()
                try:
                    api = APIClient()
                    api.cookies = cookies.copy()
                    barrier.wait(timeout=10)
                    payload = {"request_id": shared_id if duplicate else str(uuid.uuid4())}
                    payload.update({"content": "Запрос"} if duplicate else
                                   {"action": ["rooms_2", "budget_8"][index]})
                    return api.post(url, payload, format="json").status_code
                finally:
                    close_old_connections()

            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(list(pool.map(send, range(2))), [200, 200])
        self.assertEqual(ChatRequest.objects.count(), 3)
        self.assertEqual(Message.objects.filter(role="visitor").count(), 3)
        roles = list(Message.objects.values_list("role", flat=True))
        self.assertEqual(roles, ["assistant", "visitor", "assistant", "visitor", "assistant", "visitor", "assistant"])
        context = Conversation.objects.get(pk=start["conversation_id"]).context
        self.assertEqual(context["preferences"]["rooms"], 2)
        self.assertEqual(context["preferences"]["budget"], 8000000)
