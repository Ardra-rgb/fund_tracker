from django import forms

from .models import Installment, Member, Payment


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


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ("payment_date", "reference")
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "reference": forms.TextInput(attrs={"placeholder": "Optional receipt or reference"}),
        }


class InstallmentForm(forms.ModelForm):
    class Meta:
        model = Installment
        fields = ("member", "month", "due_date", "amount")
        widgets = {
            "month": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
        }