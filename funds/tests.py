from django.test import TestCase

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from .models import CollectionPeriod, Installment, Member, Payment


class FundTrackerWorkflowTests(TestCase):
	def setUp(self):
		self.owner = User.objects.create_user(username="manager", password="pass")

	def create_member(self, owner=None, **fields):
		return Member.objects.create(owner=owner or self.owner, **fields)

	def test_root_opens_login_page(self):
		response = self.client.get("/")

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "funds/auth.html")
		self.assertContains(response, "Welcome back")

		self.client.force_login(self.owner)
		response = self.client.get("/")

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "funds/auth.html")

	def test_authenticated_user_can_open_register_page(self):
		self.client.force_login(self.owner)

		response = self.client.get(reverse("register"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "funds/auth.html")
		self.assertContains(response, "Create your account")

	def test_registered_account_can_log_in_and_open_dashboard(self):
		self.client.force_login(self.owner)
		credentials = {
			"username": "second_manager",
			"password1": "Different-Pass-824!",
			"password2": "Different-Pass-824!",
		}

		response = self.client.post(reverse("register"), credentials)

		self.assertRedirects(response, reverse("login"))
		account = User.objects.get(username=credentials["username"])
		self.assertTrue(account.check_password(credentials["password1"]))
		self.assertEqual(User.objects.count(), 2)

		response = self.client.get(reverse("dashboard"))
		self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

		response = self.client.post(
			reverse("login"),
			{"username": credentials["username"], "password": credentials["password1"]},
		)

		self.assertRedirects(response, reverse("dashboard"))
		response = self.client.get(reverse("dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.wsgi_request.user, account)

	def test_fund_records_are_isolated_between_accounts(self):
		other_owner = User.objects.create_user(username="other_manager", password="pass")
		member = self.create_member(
			member_id="M-500",
			name="First Account Member",
			phone="5550500",
			monthly_amount=Decimal("50.00"),
		)
		installment = Installment.objects.create(
			member=member,
			month=date(2026, 1, 1),
			due_date=date(2026, 1, 31),
			amount=Decimal("50.00"),
		)
		payment = Payment.objects.create(
			installment=installment,
			amount=installment.amount,
			payment_date=date(2026, 1, 20),
			reference="FIRST-ACCOUNT-RECEIPT",
		)

		self.client.force_login(other_owner)
		response = self.client.get(reverse("dashboard"))
		self.assertNotContains(response, "First Account Member")
		self.assertNotContains(response, "FIRST-ACCOUNT-RECEIPT")

		response = self.client.post(
			reverse("dashboard"),
			{
				"action": "add_member",
				"member_id": "M-500",
				"name": "Second Account Member",
				"phone": "5550501",
				"monthly_amount": "60.00",
			},
		)
		self.assertRedirects(response, reverse("dashboard"))
		other_member = Member.objects.get(owner=other_owner, member_id="M-500")
		self.assertNotEqual(other_member.pk, member.pk)

		response = self.client.post(
			reverse("dashboard"),
			{"action": "delete_member", "member_id": member.pk},
		)
		self.assertEqual(response.status_code, 404)
		response = self.client.post(
			reverse("dashboard"),
			{"action": "delete_payment", "payment_id": payment.pk},
		)
		self.assertEqual(response.status_code, 404)
		self.assertTrue(Member.objects.filter(pk=member.pk).exists())
		self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

	def test_collection_period_generates_installments_and_month_navigation(self):
		self.client.force_login(self.owner)
		member = self.create_member(
			member_id="M-103",
			name="Casey Morgan",
			phone="5550103",
			monthly_amount=Decimal("50.00"),
		)
		payload = {"start_month": "2026-01", "end_month": "2026-03"}

		response = self.client.post(reverse("collection_period"), payload)

		self.assertRedirects(response, f"{reverse('dashboard')}?month=2026-01")
		self.assertEqual(CollectionPeriod.objects.count(), 1)
		self.assertEqual(
			list(Installment.objects.filter(member=member).order_by("month").values_list("month", flat=True)),
			[date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1)],
		)
		self.client.post(reverse("collection_period"), payload)
		self.assertEqual(Installment.objects.filter(member=member).count(), 3)

		response = self.client.get(reverse("dashboard"), {"month": "2026-02"})
		self.assertContains(response, "February 2026")
		self.assertContains(response, "Casey Morgan")
		self.assertContains(response, "Jan 2026")
		self.assertContains(response, "Mar 2026")

	def test_selected_month_history_only_shows_and_adds_payments_for_that_month(self):
		user = self.owner
		self.client.force_login(user)
		paid_member = self.create_member(
			member_id="M-201",
			name="January Payer",
			phone="5550201",
			monthly_amount=Decimal("50.00"),
		)
		unpaid_member = self.create_member(
			member_id="M-202",
			name="January Pending",
			phone="5550202",
			monthly_amount=Decimal("55.00"),
		)
		other_month_member = self.create_member(
			member_id="M-203",
			name="February Payer",
			phone="5550203",
			monthly_amount=Decimal("60.00"),
		)
		january_installment = Installment.objects.create(
			member=paid_member,
			month=date(2026, 1, 1),
			due_date=date(2026, 1, 31),
			amount=Decimal("50.00"),
		)
		unpaid_installment = Installment.objects.create(
			member=unpaid_member,
			month=date(2026, 1, 1),
			due_date=date(2026, 1, 31),
			amount=Decimal("55.00"),
		)
		february_installment = Installment.objects.create(
			member=other_month_member,
			month=date(2026, 2, 1),
			due_date=date(2026, 2, 28),
			amount=Decimal("60.00"),
		)
		Payment.objects.create(
			installment=january_installment,
			amount=january_installment.amount,
			payment_date=date(2026, 1, 20),
			reference="JAN-RECEIPT",
		)
		Payment.objects.create(
			installment=february_installment,
			amount=february_installment.amount,
			payment_date=date(2026, 2, 20),
			reference="FEB-RECEIPT",
		)

		response = self.client.get(reverse("dashboard"), {"month": "2026-01"})

		self.assertLess(
			response.content.index(b"<h2>Payments</h2>"),
			response.content.index(b"<h2>Installments</h2>"),
		)
		self.assertContains(response, "JAN-RECEIPT")
		self.assertNotContains(response, "FEB-RECEIPT")
		self.assertContains(response, "Installments")
		self.assertContains(response, "Due date")
		self.assertContains(response, "Paid")
		self.assertContains(response, "Pending")
		self.assertContains(response, "January Pending")
		self.assertNotContains(response, "February Payer")

		response = self.client.post(
			f"{reverse('dashboard')}?month=2026-01",
			{
				"action": "record_payment",
				"installment_id": unpaid_installment.pk,
				"payment_day": "25",
				"reference": "JAN-NEW",
			},
		)

		self.assertRedirects(response, f"{reverse('dashboard')}?month=2026-01")
		payment = Payment.objects.get(installment=unpaid_installment)
		self.assertEqual(payment.payment_date, date(2026, 1, 25))
		response = self.client.get(reverse("dashboard"), {"month": "2026-01"})
		self.assertContains(response, "JAN-NEW")
		self.assertNotContains(response, "FEB-RECEIPT")

	def test_delete_payment_from_history_keeps_installment_unpaid(self):
		self.client.force_login(self.owner)
		member = self.create_member(
			member_id="M-204",
			name="Payment to Remove",
			phone="5550204",
			monthly_amount=Decimal("65.00"),
		)
		installment = Installment.objects.create(
			member=member,
			month=date(2026, 1, 1),
			due_date=date(2026, 1, 31),
			amount=Decimal("65.00"),
		)
		payment = Payment.objects.create(
			installment=installment,
			amount=installment.amount,
			payment_date=date(2026, 1, 20),
			reference="DELETE-ME",
		)

		response = self.client.post(
			f"{reverse('dashboard')}?month=2026-01",
			{"action": "delete_payment", "payment_id": payment.pk},
		)

		self.assertRedirects(response, f"{reverse('dashboard')}?month=2026-01")
		self.assertFalse(Payment.objects.filter(pk=payment.pk).exists())
		self.assertTrue(Installment.objects.filter(pk=installment.pk).exists())
		self.assertNotContains(self.client.get(reverse("dashboard"), {"month": "2026-01"}), "DELETE-ME")

	def test_collection_period_rejects_end_before_start(self):
		self.client.force_login(self.owner)

		response = self.client.post(
			reverse("collection_period"),
			{"start_month": "2026-04", "end_month": "2026-03"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "End month must be the same as or later than the start month.")
		self.assertEqual(CollectionPeriod.objects.count(), 0)
		self.assertEqual(Installment.objects.count(), 0)

	def test_registration_requires_login_before_opening_dashboard(self):
		response = self.client.post(
			reverse("register"),
			{"username": "fundmanager", "password1": "Robust-passphrase-918!", "password2": "Robust-passphrase-918!"},
		)

		self.assertRedirects(response, reverse("login"))
		self.assertTrue(User.objects.filter(username="fundmanager").exists())
		self.assertRedirects(
			self.client.get(reverse("dashboard")),
			f"{reverse('login')}?next={reverse('dashboard')}",
		)
		self.assertRedirects(
			self.client.post(
				reverse("login"),
				{"username": "fundmanager", "password": "Robust-passphrase-918!"},
			),
			reverse("dashboard"),
		)
		self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
		self.assertRedirects(self.client.post(reverse("logout")), reverse("login"))
		self.assertRedirects(
			self.client.get(reverse("dashboard")),
			f"{reverse('login')}?next={reverse('dashboard')}",
		)

	def test_dashboard_adds_member(self):
		self.client.force_login(self.owner)

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
		self.assertTrue(
			Member.objects.filter(owner=self.owner, member_id="M-102", active=True).exists()
		)

	def test_members_view_only_shows_member_details(self):
		self.client.force_login(self.owner)
		self.create_member(
			member_id="M-105",
			name="Taylor Quinn",
			phone="5550105",
			monthly_amount=Decimal("40.00"),
		)

		response = self.client.get(reverse("dashboard"), {"view": "members"})

		self.assertContains(response, "Taylor Quinn")
		self.assertContains(response, "Add a member")
		self.assertNotContains(response, "Monthly installments")
		self.assertNotContains(response, "Payment history")
		self.assertNotContains(response, "FUND OVERVIEW")

	def test_payments_view_only_shows_payment_history(self):
		self.client.force_login(self.owner)
		member = self.create_member(
			member_id="M-106",
			name="Ledger Member",
			phone="5550106",
			monthly_amount=Decimal("45.00"),
		)
		installment = Installment.objects.create(
			member=member,
			month=date(2026, 1, 1),
			due_date=date(2026, 1, 31),
			amount=Decimal("45.00"),
		)
		payment = Payment.objects.create(
			installment=installment,
			amount=installment.amount,
			payment_date=date(2026, 1, 20),
			reference="LEDGER-ONLY",
		)

		response = self.client.get(reverse("dashboard"), {"view": "payments"})

		self.assertContains(response, "LEDGER-ONLY")
		self.assertContains(response, "Payment history")
		self.assertNotContains(response, "Monthly installments")
		self.assertNotContains(response, "YOUR COMMUNITY")
		self.assertNotContains(response, "FUND OVERVIEW")

		response = self.client.post(
			f"{reverse('dashboard')}?view=payments",
			{"action": "delete_payment", "payment_id": payment.pk},
		)

		self.assertRedirects(response, f"{reverse('dashboard')}?view=payments")

	def test_generate_installments_is_idempotent_for_current_month(self):
		self.client.force_login(self.owner)
		member = self.create_member(
			member_id="M-100",
			name="Avery Stone",
			phone="5550100",
			monthly_amount=Decimal("45.00"),
		)

		current_month = timezone.localdate().replace(day=1)
		payload = {
			"start_month": current_month.strftime("%Y-%m"),
			"end_month": current_month.strftime("%Y-%m"),
		}
		self.client.post(reverse("collection_period"), payload)
		self.client.post(reverse("collection_period"), payload)

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
			previous_month.strftime("%b %Y"),
		)

	def test_record_payment_updates_status_and_payment_history(self):
		user = self.owner
		self.client.force_login(user)
		member = self.create_member(
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
		response = self.client.get(reverse("dashboard"), {"view": "payments"})
		self.assertContains(response, "Paid")
		self.assertContains(response, "RCPT-204")
