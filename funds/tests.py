from django.test import TestCase

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from .models import Installment, Member, Payment


class FundTrackerWorkflowTests(TestCase):
	def test_registration_signs_user_in_and_opens_dashboard(self):
		response = self.client.post(
			reverse("register"),
			{"username": "fundmanager", "password1": "Robust-passphrase-918!", "password2": "Robust-passphrase-918!"},
		)

		self.assertRedirects(response, reverse("dashboard"))
		self.assertTrue(User.objects.filter(username="fundmanager").exists())
		self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
		self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
		self.assertRedirects(
			self.client.get(reverse("dashboard")),
			f"{reverse('login')}?next=%2F",
		)

	def test_dashboard_adds_member(self):
		self.client.force_login(User.objects.create_user(username="manager", password="pass"))

		response = self.client.post(
			reverse("dashboard"),
			{
				"action": "add_member",
				"member_id": "M-102",
				"name": "Morgan Reed",
				"phone": "5550102",
				"monthly_amount": "35.00",
			},
		)

		self.assertRedirects(response, reverse("dashboard"))
		self.assertTrue(Member.objects.filter(member_id="M-102", active=True).exists())

	def test_generate_installments_is_idempotent_for_current_month(self):
		self.client.force_login(User.objects.create_user(username="manager", password="pass"))
		member = Member.objects.create(
			member_id="M-100",
			name="Avery Stone",
			phone="5550100",
			monthly_amount=Decimal("45.00"),
		)

		self.client.post(reverse("dashboard"), {"action": "generate_installments"})
		self.client.post(reverse("dashboard"), {"action": "generate_installments"})

		current_month = timezone.localdate().replace(day=1)
		installment = Installment.objects.get(member=member, month=current_month)
		previous_month = current_month - timedelta(days=1)
		Installment.objects.create(
			member=member,
			month=previous_month.replace(day=1),
			due_date=previous_month,
			amount=Decimal("45.00"),
		)
		self.assertEqual(installment.amount, Decimal("45.00"))
		self.assertEqual(Installment.objects.filter(member=member).count(), 2)
		self.assertContains(
			self.client.get(reverse("dashboard")),
			previous_month.strftime("%B %Y"),
		)

	def test_record_payment_updates_status_and_payment_history(self):
		user = User.objects.create_user(username="manager", password="pass")
		self.client.force_login(user)
		member = Member.objects.create(
			member_id="M-101",
			name="Jordan Lee",
			phone="5550101",
			monthly_amount=Decimal("60.00"),
		)
		installment = Installment.objects.create(
			member=member,
			month=timezone.localdate().replace(day=1),
			due_date=timezone.localdate(),
			amount=Decimal("60.00"),
		)

		self.client.post(
			reverse("dashboard"),
			{
				"action": "record_payment",
				"installment_id": installment.pk,
				"payment_date": timezone.localdate().isoformat(),
				"reference": "RCPT-204",
			},
		)

		payment = Payment.objects.get(installment=installment)
		self.assertEqual(payment.amount, installment.amount)
		self.assertEqual(payment.recorded_by, user)
		response = self.client.get(reverse("dashboard"))
		self.assertContains(response, "Paid")
		self.assertContains(response, "RCPT-204")
