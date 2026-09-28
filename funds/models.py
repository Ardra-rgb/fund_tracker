

from django.contrib.auth.models import User
from django.db import models


class Member(models.Model):
    member_id = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15)
    monthly_amount = models.DecimalField(max_digits=10, decimal_places=2)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.member_id} - {self.name}"


class Installment(models.Model):
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="installments",
    )
    month = models.DateField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["member", "month"],
                name="unique_member_installment_month",
            )
        ]
        ordering = ["-due_date"]

    def __str__(self):
        return f"{self.member.name} - {self.month.strftime('%B %Y')}"


class Payment(models.Model):
    installment = models.OneToOneField(
        Installment,
        on_delete=models.CASCADE,
        related_name="payment",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.installment.member.name} - {self.amount}"