from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import close_old_connections, connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.catalog.importer import import_feed
from apps.catalog.models import Apartment, ResidentialComplex
from apps.catalog.test_sprint1 import feed
from apps.leads.models import Contact, Lead, LeadComment
from apps.leads.services.demo import DemoCRMClient, IdempotencyConflict, normalize_phone


def operation(**changes):
    return {"name": "Тест", "phone": "+7 (999) 000-00-01", "idempotency_key": "operation-1", **changes}


class CRMAccessTests(TestCase):
    def setUp(self):
        self.lead = DemoCRMClient().create_lead(operation())
        LeadComment.objects.create(lead=self.lead, text="История")
        self.api = APIClient()

    def test_role_matrix_all_routes(self):
        for role, superuser, active, allowed in [
            ("manager", False, True, True), ("admin", False, True, True),
            ("realtor", True, True, True), ("realtor", False, True, False),
            ("unknown", False, True, False), ("manager", False, False, False),
        ]:
            with self.subTest(role=role, superuser=superuser, active=active):
                user = User.objects.create(username=f"u{User.objects.count()}", role=role,
                                           is_superuser=superuser, is_active=active)
                self.api.force_authenticate(user)
                before = LeadComment.objects.count()
                for route, kwargs in [("lead-list", {}), ("lead-detail", {"pk": self.lead.pk})]:
                    response = self.api.get(reverse(route, kwargs=kwargs))
                    self.assertEqual(response.status_code, 200 if allowed else 403)
                    if not allowed:
                        self.assertNotIn("contact_phone", str(response.data))
                response = self.api.post(reverse("lead-comment-create", args=[self.lead.pk]), {"text": "API"})
                self.assertEqual(response.status_code, 201 if allowed else 403)
                response = self.api.patch(reverse("lead-status-update", args=[self.lead.pk]), {"status": "in_progress"})
                self.assertEqual(response.status_code, 200 if allowed else 403)
                self.client.force_login(user)
                # Inactive sessions are rejected by Django's authentication backend.
                denied = 403 if active else 302
                for route, args in [("crm-lead-list", []), ("crm-lead-detail", [self.lead.pk])]:
                    self.assertEqual(self.client.get(reverse(route, args=args)).status_code, 200 if allowed else denied)
                for payload in [{"action": "add_comment", "text": "HTML"},
                                {"action": "update_status", "status": "qualified"}]:
                    response = self.client.post(reverse("crm-lead-detail", args=[self.lead.pk]), payload)
                    self.assertEqual(response.status_code, 302 if allowed else denied)
                self.assertEqual(LeadComment.objects.count(), before + (2 if allowed else 0))
                self.lead.refresh_from_db()
                self.assertEqual(self.lead.status, "qualified" if allowed else "new")
                self.lead.status = "new"
                self.lead.save()

                self.client.logout()

    def test_admin_does_not_bypass_role_restriction(self):
        user = User.objects.create(username="staff-realtor", role="realtor", is_staff=True)
        user.user_permissions.set(Permission.objects.filter(content_type__app_label="leads"))
        self.client.force_login(user)
        for model, pk in [("lead", self.lead.pk), ("contact", self.lead.contact_id),
                          ("leadcomment", LeadComment.objects.get().pk)]:
            for suffix, args in [("changelist", []), ("change", [pk]), ("add", [])]:
                self.assertEqual(self.client.get(reverse(f"admin:leads_{model}_{suffix}", args=args)).status_code, 403)
            self.assertEqual(self.client.post(reverse(f"admin:leads_{model}_change", args=[pk]), {}).status_code, 403)
        self.assertEqual(LeadComment.objects.count(), 1)

    def test_anonymous_and_invalid_input(self):
        for route, args in [("lead-list", []), ("lead-detail", [self.lead.pk])]:
            self.assertIn(self.api.get(reverse(route, args=args)).status_code, [401, 403])
        self.assertIn(self.api.post(reverse("lead-comment-create", args=[self.lead.pk]), {"text": "x"}).status_code, [401, 403])
        self.assertIn(self.api.patch(reverse("lead-status-update", args=[self.lead.pk]), {"status": "won"}).status_code, [401, 403])
        self.assertEqual(self.client.get(reverse("crm-lead-list")).status_code, 302)
        self.assertEqual(self.client.get(reverse("crm-lead-detail", args=[self.lead.pk])).status_code, 302)
        self.assertEqual(self.client.post(reverse("crm-lead-detail", args=[self.lead.pk]), {"action": "add_comment", "text": "x"}).status_code, 302)
        user = User.objects.create(username="manager", role="manager")
        self.api.force_authenticate(user)
        self.assertEqual(self.api.post(reverse("lead-comment-create", args=[self.lead.pk]), {"text": "  "}).status_code, 400)
        self.assertEqual(self.api.patch(reverse("lead-status-update", args=[self.lead.pk]), {"status": "invalid"}).status_code, 400)
        self.assertEqual(LeadComment.objects.count(), 1)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "new")


@override_settings(CATALOG_COMPLEX_EXTERNAL_ID="1368", CATALOG_MAX_AGE_MINUTES=60)
class CRMOperationTests(TestCase):
    def setUp(self):
        self.crm = DemoCRMClient()
        import_feed(feed(), observed_at=timezone.now())
        self.ids = list(Apartment.objects.values_list("pk", flat=True))

    def test_phone_normalization(self):
        for phone in ["89990000001", "9990000001", "+7 (999) 000-00-01"]:
            self.assertEqual(normalize_phone(phone), "79990000001")
        for phone in ["", "123", "+19990000001"]:
            with self.assertRaises(ValueError):
                normalize_phone(phone)

    def test_canonical_replay_new_enquiry_and_mutable_contact(self):
        data = operation(apartment_ids=self.ids, budget_max="100.00", requirements={"a": 1, "b": 2})
        lead = self.crm.create_lead(data)
        repeat = {**data, "phone": "89990000001", "budget_max": 100,
                  "apartment_ids": self.ids[::-1] + self.ids, "requirements": {"b": 2, "a": 1}}
        self.assertEqual(self.crm.create_lead(repeat).pk, lead.pk)
        new = self.crm.create_lead(operation(idempotency_key="new", name="Другое имя"))
        self.assertNotEqual(new.pk, lead.pk)
        self.assertEqual(self.crm.create_lead(data).pk, lead.pk)
        self.assertEqual(Contact.objects.get().name, "Другое имя")
        self.assertEqual(Lead.objects.count(), 2)

    def test_conflicting_payload_does_not_change_data(self):
        lead = self.crm.create_lead(operation())
        for changes in [{"name": "Новое"}, {"phone": "89990000002"}, {"email": "test@example.com"},
                        {"budget_min": 1}, {"budget_max": 2}, {"source": "manual"},
                        {"requirements": {"rooms": 2}}, {"apartment_ids": self.ids}]:
            with self.subTest(changes=changes), self.assertRaises(IdempotencyConflict):
                self.crm.create_lead(operation(**changes))
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(Contact.objects.get().name, "Тест")
        self.assertEqual(Lead.objects.count(), 1)
        Lead.objects.filter(pk=lead.pk).update(operation_fingerprint="")
        with self.assertRaises(IdempotencyConflict):
            self.crm.create_lead(operation())

    def test_selection_scope_availability_and_replay(self):
        data = operation(apartment_ids=self.ids)
        lead = self.crm.create_lead(data)
        Apartment.objects.update(source_present=False)
        self.assertEqual(self.crm.create_lead(data).pk, lead.pk)
        with self.assertRaises(ValidationError):
            self.crm.create_lead({**data, "idempotency_key": "new"})
        Apartment.objects.update(source_present=True)
        foreign = deepcopy(feed())
        foreign["projects"][0]["id"] = "other"
        with override_settings(CATALOG_COMPLEX_EXTERNAL_ID="other"):
            import_feed(foreign, observed_at=timezone.now())
        foreign_id = Apartment.objects.filter(floor__section__building__stage__complex__external_id="other").first().pk
        for ids in [[foreign_id], [999999], [self.ids[0], 999999]]:
            with self.assertRaises(ValidationError):
                self.crm.create_lead(operation(idempotency_key="invalid", apartment_ids=ids))
        ResidentialComplex.objects.filter(external_id="1368").update(catalog_synced_at=timezone.now() - timedelta(hours=2))
        with self.assertRaises(ValidationError):
            self.crm.create_lead(operation(idempotency_key="stale", apartment_ids=self.ids))
        self.assertEqual(Lead.objects.count(), 1)

    def test_invalid_operations_and_no_key(self):
        for changes in [{"budget_min": 10, "budget_max": 1}, {"name": " "}, {"source": "bad"},
                        {"requirements": []}, {"budget_max": "NaN"}, {"unexpected": True}]:
            with self.assertRaises(ValidationError):
                self.crm.create_lead(operation(**changes))
        for _ in range(2):
            self.crm.create_lead(operation(idempotency_key=None))
        self.assertEqual(Lead.objects.count(), 2)
        self.assertEqual(Contact.objects.count(), 1)


class CRMConcurrencyTests(TransactionTestCase):
    def run_parallel(self, payloads, synchronize_contact=False, synchronize_lead=False):
        self.assertEqual(connection.vendor, "postgresql")
        barrier = Barrier(len(payloads))
        lead_barrier = Barrier(len(payloads))
        original_create = Lead.objects.create
        original = Contact.objects.get_or_create

        def synchronized(*args, **kwargs):
            barrier.wait(timeout=10)
            return original(*args, **kwargs)

        def synchronized_create(*args, **kwargs):
            lead_barrier.wait(timeout=10)
            return original_create(*args, **kwargs)

        def worker(data):
            close_old_connections()
            try:
                if not synchronize_contact:
                    barrier.wait(timeout=10)
                return DemoCRMClient().create_lead(data).pk
            except IdempotencyConflict:
                return "conflict"
            finally:
                close_old_connections()

        with (patch.object(Contact.objects, "get_or_create", side_effect=synchronized if synchronize_contact else original),
              patch.object(Lead.objects, "create", side_effect=synchronized_create if synchronize_lead else original_create)):
            with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
                return list(pool.map(worker, payloads))

    def test_same_operation_and_same_contact(self):
        results = self.run_parallel([operation(), operation(phone="89990000001")], True)
        self.assertEqual(results[0], results[1])
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)

    def test_new_operations_same_phone(self):
        results = self.run_parallel([operation(), operation(idempotency_key="second")], True)
        self.assertNotEqual(results[0], results[1])
        self.assertEqual(Lead.objects.count(), 2)
        self.assertEqual(Contact.objects.count(), 1)

    def test_same_key_different_phone_rolls_back_loser(self):
        results = self.run_parallel([operation(), operation(phone="89990000002")], True, True)
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(Lead.objects.get().contact_id, Contact.objects.get().pk)

    def test_same_key_changed_content_same_phone(self):
        results = self.run_parallel([operation(), operation(name="Другое")], True)
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)


class CRMLoginTests(TestCase):
    @override_settings(SETTINGS_MODULE='config.settings')
    def test_demo_manager_rejects_working_settings(self):
        from django.core.management import call_command, CommandError
        with self.assertRaises(CommandError):
            call_command('demo_manager')

    def test_csrf_login_next_and_visitor_session_preserved(self):
        client = Client(enforce_csrf_checks=True)
        lead = DemoCRMClient().create_lead(operation())
        target = reverse('crm-lead-detail', args=[lead.pk])
        redirect = client.get(target)
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(redirect.url, reverse('login') + '?next=' + target)
        self.assertEqual(client.get(redirect.url).status_code, 200)
        self.assertEqual(client.get('/api-auth/login/?next=/api/leads/crm/').status_code, 200)
        manager = User.objects.create_user(username='login-manager', password='test-local-only', role='manager')
        session = client.session
        session['chat_visitor_id'] = 'retained-visitor'
        session.save()
        payload = {'username': manager.username, 'password': 'test-local-only', 'next': target}
        self.assertEqual(client.post(reverse('login'), payload).status_code, 403)
        client.get(reverse('login'))
        payload['csrfmiddlewaretoken'] = client.cookies['csrftoken'].value
        response = client.post(reverse('login'), payload)
        self.assertRedirects(response, target)
        self.assertEqual(client.session['chat_visitor_id'], 'retained-visitor')
        self.assertEqual(client.get(target).status_code, 200)

    def test_demo_manager_preserves_leads_and_cannot_access_admin(self):
        from apps.chat.management.commands.demo_server import prepare_demo_data
        import_feed(feed(), observed_at=timezone.now())
        lead = DemoCRMClient().create_lead(operation())
        with patch('apps.chat.management.commands.demo_server.seed') as seed_demo:
            password = prepare_demo_data(keep_data=True)
        seed_demo.assert_not_called()
        self.assertTrue(Lead.objects.filter(pk=lead.pk).exists())
        manager = User.objects.get(username='demo_manager')
        self.assertFalse(manager.is_staff)
        self.assertFalse(manager.is_superuser)
        response = self.client.post(reverse('login'), {'username': 'demo_manager', 'password': password,
                                                     'next': 'https://example.invalid/'})
        self.assertRedirects(response, reverse('crm-lead-list'))
        self.assertEqual(self.client.get(reverse('crm-lead-detail', args=[lead.pk])).status_code, 200)
        self.assertEqual(self.client.get('/admin/').status_code, 302)
