from django.contrib import admin

from .models import Installment, Member, Payment


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "member_id",
        "name",
        "phone",
        "monthly_amount",
        "active",
    )
    search_fields = ("member_id", "name", "phone")
    list_filter = ("active",)


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = (
        "member",
        "month",
        "due_date",
        "amount",
    )
    search_fields = (
        "member__member_id",
        "member__name",
    )
    list_filter = ("due_date",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "installment",
        "amount",
        "payment_date",
        "reference",
        "recorded_by",
    )
    search_fields = (
        "installment__member__member_id",
        "installment__member__name",
        "reference",
    )
    list_filter = ("payment_date",)