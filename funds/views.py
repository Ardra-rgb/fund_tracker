from calendar import monthrange
from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import CollectionPeriodForm, InstallmentForm, MemberForm, MonthPaymentForm, PaymentForm
from .models import CollectionPeriod, Installment, Member, Payment


def login_view(request, redirect_authenticated=True):
    if request.user.is_authenticated and redirect_authenticated:
        return redirect("dashboard")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("dashboard")
    return render(request, "funds/auth.html", {"form": form, "mode": "login"})


def register_view(request):
    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        logout(request)
        return redirect("login")
    return render(request, "funds/auth.html", {"form": form, "mode": "register"})


def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect("login")
    return redirect("dashboard")


@login_required(login_url="login")
def collection_period(request):
    current_month = timezone.localdate().replace(day=1)
    form = CollectionPeriodForm(
        request.POST or None,
        initial={"start_month": current_month, "end_month": current_month},
    )
    if request.method == "POST" and form.is_valid():
        start_month = form.cleaned_data["start_month"]
        end_month = form.cleaned_data["end_month"]
        active_members = Member.objects.filter(owner=request.user, active=True)
        created = 0
        with transaction.atomic():
            CollectionPeriod.objects.get_or_create(
            owner=request.user,
                start_month=start_month,
                end_month=end_month,
            )
            month = start_month
            while month <= end_month:
                due_date = date(
                    month.year,
                    month.month,
                    monthrange(month.year, month.month)[1],
                )
                for member in active_members:
                    _, was_created = Installment.objects.get_or_create(
                        member=member,
                        month=month,
                        defaults={"due_date": due_date, "amount": member.monthly_amount},
                    )
                    created += was_created
                month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
        messages.success(
            request,
            f"{created} installment(s) created for {start_month:%B %Y} through {end_month:%B %Y}.",
        )
        return redirect(f"{reverse('dashboard')}?month={start_month:%Y-%m}")
    return render(request, "funds/collection_period.html", {"form": form})


@login_required(login_url="login")
def dashboard(request):
    today = timezone.localdate()
    current_month = today.replace(day=1)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_member":
            member_form = MemberForm(request.POST, owner=request.user)
            if member_form.is_valid():
                member = member_form.save(commit=False)
                member.owner = request.user
                member.save()
                messages.success(request, "Member added.")
                return _dashboard_redirect(request)
            return _render_dashboard(request, member_form=member_form)
        if action == "edit_member":
            member = get_object_or_404(
                Member,
                pk=request.POST.get("member_pk"),
                owner=request.user,
            )
            form = MemberForm(request.POST, instance=member, owner=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Member updated.")
                return _dashboard_redirect(request)
            return _render_dashboard(request, member_edit_form=form)
        if action == "delete_member":
            member = get_object_or_404(
                Member,
                pk=request.POST.get("member_id"),
                owner=request.user,
            )
            member.delete()
            messages.success(request, "Member and associated records deleted.")
            return _dashboard_redirect(request)
        if action == "edit_installment":
            installment = get_object_or_404(
                Installment,
                pk=request.POST.get("installment_id"),
                member__owner=request.user,
            )
            form = InstallmentForm(request.POST, instance=installment, owner=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, "Installment updated.")
                return _dashboard_redirect(request)
            return _render_dashboard(request, installment_edit_form=form)
        if action == "delete_installment":
            installment = get_object_or_404(
                Installment,
                pk=request.POST.get("installment_id"),
                member__owner=request.user,
            )
            installment.delete()
            messages.success(request, "Installment and associated payment deleted.")
            return _dashboard_redirect(request)
        if action == "delete_payment":
            payment = get_object_or_404(
                Payment.objects.select_related("installment__member"),
                pk=request.POST.get("payment_id"),
                installment__member__owner=request.user,
            )
            payment.delete()
            messages.success(request, "Payment deleted. The installment is now unpaid.")
            return _dashboard_redirect(request)
        if action == "generate_installments":
            return redirect("collection_period")
        if action == "record_payment":
            requested_month = request.GET.get("month") or request.POST.get("month")
            if "payment_day" in request.POST:
                if requested_month:
                    try:
                        selected_month = date.fromisoformat(f"{requested_month}-01")
                    except ValueError:
                        messages.error(request, "Select a valid collection month.")
                        return redirect("dashboard")
                else:
                    selected_month = timezone.localdate().replace(day=1)
                form = MonthPaymentForm(
                    request.POST,
                    month=selected_month,
                    owner=request.user,
                )
                if form.is_valid():
                    member = form.cleaned_data["member"]
                    due_date = date(
                        selected_month.year,
                        selected_month.month,
                        monthrange(selected_month.year, selected_month.month)[1],
                    )
                    try:
                        with transaction.atomic():
                            installment, _ = Installment.objects.get_or_create(
                                member=member,
                                month=selected_month,
                                defaults={
                                    "due_date": due_date,
                                    "amount": member.monthly_amount,
                                },
                            )
                            if Payment.objects.filter(installment=installment).exists():
                                messages.error(request, "This installment is already paid.")
                            else:
                                Payment.objects.create(
                                    installment=installment,
                                    amount=form.cleaned_data["amount"],
                                    payment_date=date(
                                        selected_month.year,
                                        selected_month.month,
                                        form.cleaned_data["payment_day"],
                                    ),
                                    reference=form.cleaned_data["reference"],
                                    recorded_by=request.user,
                                )
                                messages.success(request, "Payment recorded.")
                    except IntegrityError:
                        messages.error(request, "This installment is already paid.")
                    return _dashboard_redirect(request)
                return _render_dashboard(request, month_payment_form=form)
            installment = get_object_or_404(
                Installment.objects.select_related("member"),
                pk=request.POST.get("installment_id"),
                member__owner=request.user,
            )
            form = PaymentForm(request.POST)
            if Payment.objects.filter(
                installment=installment,
                installment__member__owner=request.user,
            ).exists():
                messages.error(request, "This installment is already paid.")
                return _dashboard_redirect(request)
            if form.is_valid():
                payment = form.save(commit=False)
                payment.installment = installment
                payment.amount = installment.amount
                payment.recorded_by = request.user
                try:
                    with transaction.atomic():
                        payment.save()
                except IntegrityError:
                    messages.error(request, "This installment is already paid.")
                else:
                    messages.success(request, "Payment recorded.")
                return _dashboard_redirect(request)
            return _render_dashboard(request, payment_form=form)

    return _render_dashboard(request)


def _render_dashboard(
    request,
    member_form=None,
    payment_form=None,
    member_edit_form=None,
    installment_edit_form=None,
    month_payment_form=None,
):
    today = timezone.localdate()
    current_month = today.replace(day=1)
    collection_months = {
        month
        for period in CollectionPeriod.objects.filter(owner=request.user)
        for month in _months_between(period.start_month, period.end_month)
    }
    collection_months.update(
        Installment.objects.filter(member__owner=request.user).dates("month", "month")
    )
    collection_months = sorted(collection_months, reverse=True)
    requested_month = request.GET.get("month")
    try:
        selected_month = date.fromisoformat(f"{requested_month}-01")
    except (TypeError, ValueError):
        selected_month = current_month
    if collection_months and selected_month not in collection_months:
        selected_month = current_month if current_month in collection_months else collection_months[0]
    installments = list(
        Installment.objects.filter(member__owner=request.user, month=selected_month)
        .select_related("member")
        .prefetch_related("payment")
        .order_by("member__name")
    )
    members = list(Member.objects.filter(owner=request.user).order_by("name"))
    for member in members:
        member.edit_form = (
            member_edit_form
            if member_edit_form and member_edit_form.instance.pk == member.pk
            else MemberForm(instance=member, owner=request.user)
        )
    for installment in installments:
        installment.edit_form = (
            installment_edit_form
            if installment_edit_form and installment_edit_form.instance.pk == installment.pk
            else InstallmentForm(instance=installment, owner=request.user)
        )
    current_installments = installments
    paid_count = sum(hasattr(installment, "payment") for installment in current_installments)
    pending_installments = [
        installment for installment in current_installments if not hasattr(installment, "payment")
    ]
    payments = (
        Payment.objects.filter(installment__member__owner=request.user)
        .select_related("installment__member", "recorded_by")
        .order_by("-payment_date", "-created_at")
    )
    payment_date_filter = request.GET.get("payment_date", "").strip()
    member_name_filter = request.GET.get("member_name", "").strip()
    if payment_date_filter:
        try:
            payment_date = date.fromisoformat(payment_date_filter)
        except ValueError:
            payments = payments.none()
        else:
            payments = payments.filter(payment_date=payment_date)
    if member_name_filter:
        payments = payments.filter(
            installment__member__name__icontains=member_name_filter
        )
    selected_month_payments = payments.filter(installment__month=selected_month)
    payment_months = []
    for payment in payments:
        month = payment.payment_date.replace(day=1)
        if not payment_months or payment_months[-1]["month"] != month:
            payment_months.append({"month": month, "payments": []})
        payment_months[-1]["payments"].append(payment)
    return render(
        request,
        "funds/dashboard.html",
        {
            "members": members,
            "show_members_only": request.GET.get("view") == "members",
            "show_payments_only": request.GET.get("view") == "payments",
            "installments": installments,
            "collection_months": collection_months,
            "selected_month": selected_month,
            "payments": payments,
            "payment_date_filter": payment_date_filter,
            "member_name_filter": member_name_filter,
            "selected_month_payments": selected_month_payments,
            "show_month_history": "month" in request.GET,
            "payment_months": payment_months,
            "active_members": Member.objects.filter(owner=request.user, active=True).count(),
            "paid_count": paid_count,
            "pending_count": len(pending_installments),
            "pending_installments": pending_installments,
            "current_installment_count": len(current_installments),
            "collected": sum(
                (
                    installment.payment.amount
                    for installment in current_installments
                    if hasattr(installment, "payment")
                ),
                start=0,
            ),
            "current_month": selected_month.strftime("%B %Y"),
            "member_form": member_form or MemberForm(owner=request.user),
            "payment_form": payment_form or PaymentForm(initial={"payment_date": today}),
            "month_payment_form": month_payment_form or MonthPaymentForm(
                month=selected_month,
                owner=request.user,
            ),
        },
    )


def _months_between(start_month, end_month):
    month = start_month
    while month <= end_month:
        yield month
        month = date(month.year + month.month // 12, month.month % 12 + 1, 1)


def _dashboard_redirect(request):
    if request.GET.get("view") == "members":
        return redirect(f"{reverse('dashboard')}?view=members")
    if request.GET.get("view") == "payments":
        query = {"view": "payments"}
        for filter_name in ("payment_date", "member_name"):
            filter_value = request.GET.get(filter_name, "").strip()
            if filter_value:
                query[filter_name] = filter_value
        return redirect(f"{reverse('dashboard')}?{urlencode(query)}")
    month = request.GET.get("month")
    if month:
        return redirect(f"{reverse('dashboard')}?month={month}")
    return redirect("dashboard")