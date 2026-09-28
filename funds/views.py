from calendar import monthrange
from datetime import date

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import InstallmentForm, MemberForm, PaymentForm
from .models import Installment, Member, Payment


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("dashboard")
    return render(request, "funds/auth.html", {"form": form, "mode": "login"})


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("dashboard")
    return render(request, "funds/auth.html", {"form": form, "mode": "register"})


def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect("login")
    return redirect("dashboard")


@login_required(login_url="login")
def dashboard(request):
    today = timezone.localdate()
    current_month = today.replace(day=1)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_member":
            member_form = MemberForm(request.POST)
            if member_form.is_valid():
                member_form.save()
                messages.success(request, "Member added.")
                return redirect("dashboard")
            return _render_dashboard(request, member_form=member_form)
        if action == "edit_member":
            member = get_object_or_404(Member, pk=request.POST.get("member_id"))
            form = MemberForm(request.POST, instance=member)
            if form.is_valid():
                form.save()
                messages.success(request, "Member updated.")
                return redirect("dashboard")
            return _render_dashboard(request, member_edit_form=form)
        if action == "delete_member":
            member = get_object_or_404(Member, pk=request.POST.get("member_id"))
            member.delete()
            messages.success(request, "Member and associated records deleted.")
            return redirect("dashboard")
        if action == "edit_installment":
            installment = get_object_or_404(Installment, pk=request.POST.get("installment_id"))
            form = InstallmentForm(request.POST, instance=installment)
            if form.is_valid():
                installment = form.save()
                if hasattr(installment, "payment"):
                    installment.payment.amount = installment.amount
                    installment.payment.save(update_fields=["amount"])
                messages.success(request, "Installment updated.")
                return redirect("dashboard")
            return _render_dashboard(request, installment_edit_form=form)
        if action == "delete_installment":
            installment = get_object_or_404(Installment, pk=request.POST.get("installment_id"))
            installment.delete()
            messages.success(request, "Installment and associated payment deleted.")
            return redirect("dashboard")
        if action == "generate_installments":
            active_members = Member.objects.filter(active=True)
            due_date = date(
                current_month.year,
                current_month.month,
                monthrange(current_month.year, current_month.month)[1],
            )
            created = 0
            for member in active_members:
                _, was_created = Installment.objects.get_or_create(
                    member=member,
                    month=current_month,
                    defaults={"due_date": due_date, "amount": member.monthly_amount},
                )
                created += was_created
            messages.success(request, f"{created} installment(s) created for {current_month:%B %Y}.")
            return redirect("dashboard")
        if action == "record_payment":
            installment = get_object_or_404(
                Installment.objects.select_related("member"),
                pk=request.POST.get("installment_id"),
            )
            form = PaymentForm(request.POST)
            if Payment.objects.filter(installment=installment).exists():
                messages.error(request, "This installment is already paid.")
                return redirect("dashboard")
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
                return redirect("dashboard")
            return _render_dashboard(request, payment_form=form)

    return _render_dashboard(request)


def _render_dashboard(
    request,
    member_form=None,
    payment_form=None,
    member_edit_form=None,
    installment_edit_form=None,
):
    today = timezone.localdate()
    current_month = today.replace(day=1)
    installments = list(
        Installment.objects.select_related("member")
        .prefetch_related("payment")
        .order_by("-month", "member__name")
    )
    members = list(Member.objects.order_by("name"))
    for member in members:
        member.edit_form = (
            member_edit_form
            if member_edit_form and member_edit_form.instance.pk == member.pk
            else MemberForm(instance=member)
        )
    for installment in installments:
        installment.edit_form = (
            installment_edit_form
            if installment_edit_form and installment_edit_form.instance.pk == installment.pk
            else InstallmentForm(instance=installment)
        )
    current_installments = [
        installment for installment in installments if installment.month == current_month
    ]
    paid_count = sum(hasattr(installment, "payment") for installment in current_installments)
    payments = Payment.objects.select_related(
        "installment__member", "recorded_by"
    ).order_by("-payment_date", "-created_at")
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
            "installments": installments,
            "payments": payments,
            "payment_months": payment_months,
            "active_members": Member.objects.filter(active=True).count(),
            "paid_count": paid_count,
            "pending_count": len(current_installments) - paid_count,
            "collected": sum(
                (
                    installment.payment.amount
                    for installment in current_installments
                    if hasattr(installment, "payment")
                ),
                start=0,
            ),
            "current_month": today.strftime("%B %Y"),
            "member_form": member_form or MemberForm(),
            "payment_form": payment_form or PaymentForm(initial={"payment_date": today}),
        },
    )