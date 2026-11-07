from django import forms
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.urls import reverse
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache
from django.core.exceptions import PermissionDenied

from apps.knowledge.models import Document
from apps.leads.permissions import can_access_crm
from .models import ClientRegistration, RegistrationDispute
from .services import allowed_developers, register_client, resolve_dispute, approve_dispute


class PlatformLoginView(LoginView):
    template_name = "leads/login.html"

    def get_default_redirect_url(self):
        return reverse("realtor-home" if self.request.user.role == "realtor" else "crm-lead-list")


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect("realtor-home" if request.user.role == "realtor" else "crm-lead-list")


class RegistrationForm(forms.Form):
    developer = forms.ModelChoiceField(queryset=None, label="Застройщик")
    name = forms.CharField(max_length=150, label="Имя клиента")
    phone = forms.CharField(max_length=30, label="Телефон")
    confirmed = forms.BooleanField(label="Подтверждаю фиксацию тестового клиента на 14 суток")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["developer"].queryset = allowed_developers(user)


def own_clients(user):
    developers = allowed_developers(user)
    return ClientRegistration.objects.filter(owner=user, developer__in=developers).select_related("developer", "owner")


def materials(user):
    now = timezone.now()
    return Document.objects.filter(complex__developer__in=allowed_developers(user),
        approved=True, active=True, audience="realtor", valid_from__lte=now,
        valid_until__gt=now, published_at__lte=now).select_related("complex")


def client_data(item):
    return {"id": item.pk, "name": item.name, "phone": item.phone_normalized,
            "developer_id": item.developer_id, "owner_id": item.owner_id,
            "status": item.effective_status, "expires_at": item.expires_at.isoformat()}


@never_cache
@login_required
@require_http_methods(["GET"])
def cabinet(request):
    return render(request, "accounts/cabinet.html", {
        "clients": own_clients(request.user), "materials": materials(request.user),
        "requests": RegistrationDispute.objects.filter(requester=request.user,
            developer__in=allowed_developers(request.user)).select_related("developer").order_by("-created_at")[:20]})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def client_create(request):
    form = RegistrationForm(request.user, request.POST if request.method == "POST" else None)
    notice = ""
    status = 200
    if request.method == "POST" and form.is_valid():
        try:
            item, _ = register_client(request.user, form.cleaned_data["developer"].pk,
                                      form.cleaned_data["name"], form.cleaned_data["phone"])
            if item:
                return redirect("realtor-client", pk=item.pk)
            notice = "Фиксация не подтверждена. Запрос передан менеджеру для проверки."
            status = 409
        except ValueError as exc:
            form.add_error("phone", str(exc))
    return render(request, "accounts/client_create.html", {
        "form": form, "notice": notice}, status=status)


@never_cache
@login_required
@require_http_methods(["GET"])
def client_detail(request, pk):
    item = get_object_or_404(own_clients(request.user), pk=pk)
    from uuid import uuid4
    from apps.catalog.models import Apartment
    from .models import Booking
    apartments = Apartment.objects.filter(floor__section__building__stage__complex__developer=item.developer,
        floor__section__building__stage__complex__developer__is_demo=True)
    return render(request, "accounts/client.html", {"item": item, "booking_key": uuid4(),
        "apartments": [apartment for apartment in apartments if apartment.is_available_for_selection],
        "bookings": Booking.objects.filter(client=item, owner=request.user)})


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def clients_api(request, pk=None):
    clients = own_clients(request.user)
    if pk is not None:
        if request.method != "GET":
            return HttpResponse(status=405)
        return JsonResponse(client_data(get_object_or_404(clients, pk=pk)))
    if request.method == "GET":
        return JsonResponse({"clients": [client_data(item) for item in clients]})
    # Form encoding shares Django validation and CSRF with the HTML cabinet.
    form = RegistrationForm(request.user, request.POST)
    if set(request.POST) - {"developer", "name", "phone", "confirmed", "csrfmiddlewaretoken"}:
        return JsonResponse({"error": "Неизвестные поля."}, status=400)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors.get_json_data()}, status=400)
    try:
        item, created = register_client(request.user, form.cleaned_data["developer"].pk,
                                        form.cleaned_data["name"], form.cleaned_data["phone"])
    except ValueError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    if item is None:
        return JsonResponse({"error": "Фиксация не подтверждена. Запрос передан менеджеру."}, status=409)
    return JsonResponse(client_data(item), status=201 if created else 200)


@never_cache
@login_required
@require_http_methods(["GET"])
def download(request, pk):
    document = get_object_or_404(materials(request.user), pk=pk)
    # Extracted text only, never redirect to the private source locator.
    content = "\n\n".join(document.chunks.order_by("position").values_list("content", flat=True))
    response = HttpResponse(f"{document.title}\nВерсия: {document.version}\n"
        f"Действует до: {document.valid_until.isoformat()}\n\n{content}", content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="material-{document.pk}.txt"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def disputes(request):
    if not can_access_crm(request.user):
        raise PermissionDenied
    error = ""
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        dispute_id = request.POST.get("dispute", "")
        if not dispute_id.isdecimal() or len(dispute_id) > 18:
            return HttpResponse("Некорректный номер спора.", status=400)
        approve = request.POST.get("approve") == "yes"
        reject = request.POST.get("reject") == "yes"
        if approve == reject or "cancel" in request.POST or "keep" in request.POST:
            error = "Выберите один вариант: подтвердить фиксацию за заявителем или отклонить запрос."
        elif len(reason) > 2000:
            error = "Комментарий должен содержать не более 2000 символов."
        else:
            try:
                if approve:
                    approve_dispute(request.user, int(dispute_id), reason, request.POST.get("client_name"))
                else:
                    resolve_dispute(request.user, int(dispute_id), reason)
            except RegistrationDispute.DoesNotExist as exc:
                raise Http404 from exc
            except ValueError as exc:
                error = str(exc)
            else:
                return redirect("realtor-disputes")
    return render(request, "accounts/disputes.html", {"disputes": RegistrationDispute.objects.filter(
        resolved_at__isnull=True).select_related("developer", "requester", "requester__agency"), "error": error})


class BookingForm(forms.Form):
    apartment = forms.IntegerField(min_value=1)
    operation_key = forms.UUIDField()
    confirmed = forms.BooleanField()


@never_cache
@login_required
@require_http_methods(["POST"])
def booking_create(request, pk):
    from apps.catalog.models import Apartment
    from apps.leads.services.demo import IdempotencyConflict
    from .bookings import create_booking
    item = get_object_or_404(own_clients(request.user), pk=pk)
    form = BookingForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": "Укажите квартиру, ключ операции и явное подтверждение."}, status=400)
    apartment = get_object_or_404(Apartment, pk=form.cleaned_data["apartment"],
        floor__section__building__stage__complex__developer=item.developer,
        floor__section__building__stage__complex__developer__is_demo=True)
    try:
        create_booking(request.user, item.pk, apartment.pk, form.cleaned_data["operation_key"])
    except (ValueError, IdempotencyConflict):
        return JsonResponse({"error": "Квартира/фиксация недоступна или ключ уже использован."}, status=409)
    return redirect("realtor-client", pk=pk)


@never_cache
@login_required
@require_http_methods(["POST"])
def booking_cancel(request, pk):
    from .models import Booking
    from .bookings import cancel_booking
    item = get_object_or_404(Booking, pk=pk, owner=request.user,
        client__in=own_clients(request.user))
    if request.POST.get("confirmed") != "on":
        return JsonResponse({"error": "Подтвердите отмену."}, status=400)
    cancel_booking(request.user, item.pk)
    return redirect("realtor-client", pk=item.client_id)
