from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connection, IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from apps.catalog.models import Developer, ResidentialComplex
from apps.knowledge.models import Chunk, Document
from apps.leads.models import Contact
from .models import Agency, ClientRegistration, RegistrationAudit, RegistrationDispute, User
from .services import cancel_registration, register_client, resolve_dispute


PHONE = "79990000001"


def seed():
    developer = Developer.objects.create(name="Synthetic", is_demo=True)
    agency = Agency.objects.create(name="Agency")
    agency.developers.add(developer)
    first = User.objects.create_user(username="first", password="test-only", agency=agency)
    # Same agency colleagues must not share access to clients.
    second = User.objects.create_user(username="second", password="test-only", agency=agency)
    return developer, agency, first, second


class RealtorTests(TestCase):
    def setUp(self):
        self.developer, self.agency, self.first, self.second = seed()
        self.manager = User.objects.create_user(username="manager", role="manager", password="test-only")
        self.client.force_login(self.first)

    def create(self, user=None, phone=PHONE):
        return register_client(user or self.first, self.developer.pk, "Тест", phone)[0]

    def test_normalization_replay_and_expiry(self):
        item = self.create(phone="8 (999) 000-00-01")
        repeated = self.create(phone="9990000001")
        self.assertEqual(item.pk, repeated.pk)
        self.assertEqual(item.expires_at, repeated.expires_at)
        with patch("apps.accounts.services.timezone.now", return_value=item.expires_at):
            renewed = self.create(self.second)
        item.refresh_from_db()
        self.assertEqual(item.status, "expired")
        self.assertNotEqual(item.pk, renewed.pk)
        self.assertEqual(renewed.owner, self.second)

    def test_conflict_private_and_dispute_deduplicated(self):
        item = self.create()
        self.client.force_login(self.second)
        payload = {"developer": self.developer.pk, "name": "Other", "phone": PHONE, "confirmed": "on"}
        for _ in range(2):
            response = self.client.post("/realtor/api/clients/", payload)
            self.assertEqual(response.status_code, 409)
            self.assertNotIn("first", response.content.decode())
            self.assertNotIn(PHONE, response.content.decode())
        self.assertEqual(RegistrationDispute.objects.count(), 1)
        item.refresh_from_db()
        self.assertEqual(item.owner, self.first)
        self.assertEqual(ClientRegistration.objects.count(), 1)

    def test_direct_crm_contact_review_without_overwrite(self):
        contact = Contact.objects.create(name="CRM private", phone=PHONE, phone_normalized=PHONE)
        self.assertIsNone(self.create())
        contact.refresh_from_db()
        self.assertEqual(contact.name, "CRM private")
        self.assertEqual(RegistrationDispute.objects.get().reason, "direct_client")
        self.assertFalse(ClientRegistration.objects.exists())

    def test_own_clients_html_api_and_foreign_id(self):
        item = self.create()
        for url in ("/realtor/", f"/realtor/clients/{item.pk}/", "/realtor/api/clients/", f"/realtor/api/clients/{item.pk}/"):
            self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.second)
        self.assertEqual(self.client.get(f"/realtor/clients/{item.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/realtor/api/clients/{item.pk}/").status_code, 404)
        self.assertNotContains(self.client.get("/realtor/"), PHONE)
        self.assertEqual(self.client.get("/realtor/api/clients/").json(), {"clients": []})
        self.assertEqual(self.client.get("/realtor/disputes/").status_code, 403)
        self.assertEqual(self.client.get("/api/leads/").status_code, 403)

    def test_scope_revocation_roles_and_invalid_inputs(self):
        foreign = Developer.objects.create(name="Foreign")
        with self.assertRaises(PermissionDenied):
            register_client(self.first, foreign.pk, "Test", PHONE)
        for name, phone in (("", PHONE), ("Test", "bad")):
            with self.assertRaises(ValueError):
                register_client(self.first, self.developer.pk, name, phone)
        self.create()
        self.agency.developers.clear()
        self.assertEqual(self.client.get("/realtor/api/clients/").json(), {"clients": []})
        self.agency.active = False
        self.agency.save()
        self.assertEqual(self.client.get("/realtor/").status_code, 403)
        for user in (self.manager, User.objects.create_user(username="unbound")):
            self.client.force_login(user)
            self.assertEqual(self.client.get("/realtor/").status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get("/realtor/").status_code, 302)

    def test_login_routes_confirmation_and_csrf(self):
        self.client.logout()
        response = self.client.post("/accounts/login/", {"username": "first", "password": "test-only"})
        self.assertRedirects(response, "/realtor/", fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/accounts/home/"), "/realtor/", fetch_redirect_response=False)
        payload = {"developer": self.developer.pk, "name": "Test", "phone": PHONE}
        self.assertEqual(self.client.post("/realtor/api/clients/", payload).status_code, 400)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.first)
        self.assertEqual(secure.post("/realtor/clients/new/", payload).status_code, 403)
        self.assertEqual(secure.post("/realtor/api/clients/", payload).status_code, 403)
        self.assertFalse(ClientRegistration.objects.exists())
        payload["confirmed"] = "on"
        response = self.client.post("/realtor/clients/new/", payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ClientRegistration.objects.count(), 1)
        payload["owner_id"] = self.second.pk
        self.assertEqual(self.client.post("/realtor/api/clients/", payload).status_code, 400)

    def test_registration_page_separates_list_from_post_and_refresh(self):
        page = self.client.get("/realtor/")
        self.assertContains(page, 'href="/realtor/clients/new/"')
        self.assertNotContains(page, 'name="phone"')
        self.assertContains(self.client.get("/realtor/clients/new/"), 'name="phone"')
        payload = {"developer": self.developer.pk, "name": "Test", "phone": PHONE, "confirmed": "on"}
        self.assertEqual(self.client.post("/realtor/", payload).status_code, 405)
        self.assertFalse(ClientRegistration.objects.exists())
        response = self.client.post("/realtor/clients/new/", payload)
        item = ClientRegistration.objects.get()
        self.assertRedirects(response, f"/realtor/clients/{item.pk}/")
        for _ in range(2):
            self.assertEqual(self.client.get(response.url).status_code, 200)
            self.assertContains(self.client.get("/realtor/"), "Test")
        self.assertEqual(ClientRegistration.objects.count(), 1)
        self.client.post("/realtor/clients/new/", payload)
        self.assertEqual(ClientRegistration.objects.count(), 1)
        self.client.force_login(self.second)
        conflict = self.client.post("/realtor/clients/new/", payload)
        self.assertEqual(conflict.status_code, 409)
        self.assertTemplateUsed(conflict, "accounts/client_create.html")
        self.assertContains(self.client.get("/realtor/"), "Клиентов пока нет")
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get("/realtor/clients/new/").status_code, 403)
        self.assertEqual(self.client.post("/realtor/clients/new/", payload).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get("/realtor/clients/new/").status_code, 302)

    def test_manager_resolution_and_cancel_audit(self):
        item = self.create()
        self.create(self.second)
        dispute = RegistrationDispute.objects.get()
        with self.assertRaises(PermissionDenied):
            cancel_registration(self.first, item.pk, "No")
        self.client.force_login(self.manager)
        self.assertContains(self.client.get("/realtor/disputes/"), PHONE)
        self.client.post("/realtor/disputes/", {"dispute": dispute.pk, "reason": ""})
        item.refresh_from_db()
        self.assertEqual(item.status, "active")
        resolve_dispute(self.manager, dispute.pk, "Тестовый спор проверен", cancel=True)
        item.refresh_from_db()
        dispute.refresh_from_db()
        self.assertEqual(item.status, "cancelled")
        self.assertEqual(dispute.resolved_by, self.manager)
        self.assertEqual(RegistrationAudit.objects.get().actor, self.manager)
        new = self.create(self.second)
        self.assertEqual(new.owner, self.second)

    def test_dispute_requires_one_decision_and_comment_is_optional(self):
        item = self.create()
        self.create(self.second)
        dispute = RegistrationDispute.objects.get()
        self.client.force_login(self.manager)
        page = self.client.get("/realtor/disputes/")
        self.assertContains(page, 'name="approve"')
        self.assertNotContains(page, 'maxlength="2000" required')
        for decision in ({}, {"approve": "yes", "reject": "yes"}, {"approve": "no"},
                         {"keep": "yes"}, {"cancel": "yes"},
                         {"approve": "yes", "reason": "x" * 2001}):
            self.client.post("/realtor/disputes/", {"dispute": dispute.pk, **decision})
            dispute.refresh_from_db()
            self.assertIsNone(dispute.resolved_at)
        response = self.client.post("/realtor/disputes/", {"dispute": dispute.pk, "reject": "yes"})
        self.assertRedirects(response, "/realtor/disputes/")
        item.refresh_from_db()
        dispute.refresh_from_db()
        self.assertEqual(item.status, "active")
        self.assertEqual(dispute.decision, "rejected")
        self.assertFalse(RegistrationAudit.objects.exists())
        self.create(self.second)
        dispute = RegistrationDispute.objects.get(resolved_at__isnull=True)
        response = self.client.post("/realtor/disputes/", {"dispute": dispute.pk, "approve": "yes", "reason": "   "})
        self.assertRedirects(response, "/realtor/disputes/")
        item.refresh_from_db()
        self.assertEqual(item.status, "cancelled")
        self.assertIn("Прежняя фиксация отменена", RegistrationAudit.objects.get(registration=item).reason)

    def document(self, **changes):
        now = timezone.now()
        complex = ResidentialComplex.objects.create(developer=self.developer, external_id=str(Document.objects.count()), name="Synthetic")
        data = dict(source_id="test", version="1", title="Закрытая комиссия", locator="private:source",
            complex=complex, audience="realtor", topic="purchase_terms", published_at=now,
            valid_from=now - timedelta(days=1), valid_until=now + timedelta(days=1), approved_by="test",
            approved=True, checksum="test", embedding_model="test")
        data.update(changes)
        doc = Document.objects.create(**data)
        Chunk.objects.create(document=doc, position=0, content="Synthetic commission", embedding=[0.0] * 768)
        return doc

    def test_material_download_scope_and_lifecycle(self):
        valid = self.document()
        response = self.client.get(f"/realtor/materials/{valid.pk}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertContains(response, "Synthetic commission")
        self.assertNotContains(response, "private:source")
        for changes in ({"audience": "internal"}, {"audience": "public"}, {"approved": False},
                        {"active": False}, {"valid_until": timezone.now()},
                        {"published_at": timezone.now() + timedelta(days=2)}):
            doc = self.document(**changes)
            self.assertEqual(self.client.get(f"/realtor/materials/{doc.pk}/download/").status_code, 404)
        self.agency.developers.clear()
        self.assertEqual(self.client.get(f"/realtor/materials/{valid.pk}/download/").status_code, 404)
        self.agency.developers.add(self.developer)
        self.client.logout()
        self.assertEqual(self.client.get(f"/realtor/materials/{valid.pk}/download/").status_code, 302)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(f"/realtor/materials/{valid.pk}/download/").status_code, 403)

    def test_foreign_developer_material_and_clients(self):
        item = self.create()
        foreign_developer = Developer.objects.create(name="Foreign developer")
        foreign_agency = Agency.objects.create(name="Foreign agency")
        foreign_agency.developers.add(foreign_developer)
        foreign_user = User.objects.create_user(username="foreign", agency=foreign_agency)
        document = self.document()
        self.client.force_login(foreign_user)
        self.assertEqual(self.client.get(f"/realtor/clients/{item.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/realtor/materials/{document.pk}/download/").status_code, 404)
        self.assertNotContains(self.client.get("/realtor/"), document.title)
        self.assertIsNotNone(register_client(foreign_user, foreign_developer.pk, "Test", PHONE)[0])

    def test_admin_cannot_bypass_realtor_scope(self):
        from django.contrib.auth.models import Permission
        self.first.is_staff = True
        self.first.save()
        self.first.user_permissions.add(*Permission.objects.filter(content_type__app_label="accounts"))
        for model in ("agency", "clientregistration", "registrationdispute", "registrationaudit"):
            self.assertEqual(self.client.get(f"/admin/accounts/{model}/").status_code, 403)

    def test_db_unique_active(self):
        item = self.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClientRegistration.objects.create(developer=self.developer, owner=self.second, agency=self.agency,
                phone_normalized=PHONE, name="Test", expires_at=item.expires_at)

    def test_demo_accounts_normal_login_and_closed_material(self):
        from .management.commands.realtor_demo import seed_realtors
        credentials = seed_realtors()
        for username, password in credentials:
            self.client.logout()
            self.assertTrue(self.client.login(username=username, password=password))
        username, password = credentials[0]
        self.client.login(username=username, password=password)
        self.assertContains(self.client.get("/realtor/"), "Учебная комиссия")


class RealtorConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.developer, self.agency, self.first, self.second = seed()
        other_agency = Agency.objects.create(name="Concurrent agency")
        other_agency.developers.add(self.developer)
        self.second.agency = other_agency
        self.second.save()

    def parallel(self, user_ids):
        self.assertEqual(connection.vendor, "postgresql")
        barrier = Barrier(2)
        def worker(user_id):
            close_old_connections()
            try:
                user = User.objects.get(pk=user_id)
                barrier.wait(timeout=10)
                item, _ = register_client(user, self.developer.pk, "Test", "89990000001")
                return item.pk if item else None
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker, user_ids))

    def test_different_agents_one_winner(self):
        results = self.parallel([self.first.pk, self.second.pk])
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(ClientRegistration.objects.filter(status="active").count(), 1)
        self.assertEqual(RegistrationDispute.objects.count(), 1)

    def test_same_agent_repeat(self):
        results = self.parallel([self.first.pk, self.first.pk])
        self.assertEqual(results[0], results[1])
        self.assertEqual(ClientRegistration.objects.count(), 1)
        self.assertEqual(RegistrationDispute.objects.count(), 0)

    def test_expired_competition(self):
        item, _ = register_client(self.first, self.developer.pk, "Test", PHONE)
        ClientRegistration.objects.filter(pk=item.pk).update(created_at=timezone.now()-timedelta(days=16), expires_at=timezone.now()-timedelta(days=1))
        results = self.parallel([self.first.pk, self.second.pk])
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(ClientRegistration.objects.filter(status="active").count(), 1)
        self.assertEqual(ClientRegistration.objects.filter(status="expired").count(), 1)
