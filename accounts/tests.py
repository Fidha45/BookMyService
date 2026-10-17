from django.test import TestCase
from django.urls import reverse
from .models import User

class AccountTests(TestCase):
    def test_registration_creates_customer_and_rejects_admin_role(self):
        response = self.client.post(reverse("register"), {"first_name":"A Customer", "email":"person@example.test", "phone":"+91 1234567890", "role":"customer", "password1":"Test-Strong-Pass-123!", "password2":"Test-Strong-Pass-123!"})
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="person@example.test")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertTrue(user.check_password("Test-Strong-Pass-123!"))
        self.assertNotEqual(user.password, "Test-Strong-Pass-123!")
        rejected = self.client.post(reverse("register"), {"first_name":"Attacker", "email":"attacker@example.test", "phone":"1234567890", "role":"admin", "password1":"Test-Strong-Pass-123!", "password2":"Test-Strong-Pass-123!"})
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(User.objects.filter(email="attacker@example.test").exists())

    def test_duplicate_email_and_invalid_login(self):
        User.objects.create_user(email="person@example.test", password="Test-Strong-Pass-123!")
        response = self.client.post(reverse("register"), {"first_name":"Again", "email":"person@example.test", "phone":"1234567890", "role":"customer", "password1":"Test-Strong-Pass-123!", "password2":"Test-Strong-Pass-123!"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.filter(email="person@example.test").count(), 1)
        self.assertFalse(self.client.login(email="person@example.test", password="wrong"))

    def test_login_logout_and_deactivated_session(self):
        user = User.objects.create_user(email="login@example.test", password="Test-Strong-Pass-123!")
        self.assertTrue(self.client.login(email="login@example.test", password="Test-Strong-Pass-123!"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.client.post(reverse("logout"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.client.force_login(user)
        user.is_active = False
        user.save(update_fields=["is_active"])
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_login_page_preserves_safe_return_destination(self):
        response = self.client.get(reverse("login"), {"next": "/bookings/new/1/"})
        self.assertContains(response, 'name="next" value="/bookings/new/1/"')

    def test_login_page_has_administrator_sign_in_option(self):
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Administrator?")
        self.assertContains(response, 'href="/accounts/login/?next=/dashboard/"')
