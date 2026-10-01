from calendar import monthrange
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from ..forms import CollectionPeriodForm
from ..models import CollectionPeriod, Installment, Member


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