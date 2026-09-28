from calendar import monthrange

from django import forms

from .models import Installment, Member, Payment


class CollectionPeriodForm(forms.Form):
    start_month = forms.DateField(
        input_formats=["%Y-%m"],
        widget=forms.DateInput(format="%Y-%m", attrs={"type": "month"}),
    )
    end_month = forms.DateField(
        input_formats=["%Y-%m"],
        widget=forms.DateInput(format="%Y-%m", attrs={"type": "month"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        start_month = cleaned_data.get("start_month")
        end_month = cleaned_data.get("end_month")
        if start_month and end_month and end_month < start_month:
            self.add_error("end_month", "End month must be the same as or later than the start month.")
        return cleaned_data


class MemberForm(forms.ModelForm):
    monthly_amount = forms.DecimalField(
        min_value=0.01,
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )

    class Meta:
        model = Member
        fields = ("member_id", "name", "phone", "monthly_amount")
        widgets = {
            "member_id": forms.TextInput(attrs={"placeholder": "e.g. M-1042"}),
            "name": forms.TextInput(attrs={"placeholder": "Full name"}),
            "phone": forms.TextInput(attrs={"placeholder": "Phone number"}),
        }

    def __init__(self, *args, owner, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    def clean_member_id(self):
        member_id = self.cleaned_data["member_id"]
        existing_members = Member.objects.filter(owner=self.owner, member_id=member_id)
        if self.instance.pk:
            existing_members = existing_members.exclude(pk=self.instance.pk)
        if existing_members.exists():
            raise forms.ValidationError("You already use this member ID.")
        return member_id


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ("payment_date", "reference")
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "reference": forms.TextInput(attrs={"placeholder": "Optional receipt or reference"}),
        }


class MonthPaymentForm(forms.Form):
    payment_day = forms.IntegerField(
        label="Day paid",
        min_value=1,
        widget=forms.NumberInput(attrs={"min": "1", "max": "31", "placeholder": "Day"}),
    )
    reference = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Optional receipt or reference"}),
    )

    def __init__(self, *args, month, **kwargs):
        super().__init__(*args, **kwargs)
        self.month = month
        self.fields["payment_day"].widget.attrs["max"] = monthrange(month.year, month.month)[1]

    def clean_payment_day(self):
        payment_day = self.cleaned_data["payment_day"]
        if payment_day > monthrange(self.month.year, self.month.month)[1]:
            raise forms.ValidationError("Enter a valid day for the selected month.")
        return payment_day


class InstallmentForm(forms.ModelForm):
    class Meta:
        model = Installment
        fields = ("member", "month", "due_date", "amount")
        widgets = {
            "month": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
        }

    def __init__(self, *args, owner, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["member"].queryset = Member.objects.filter(owner=owner)