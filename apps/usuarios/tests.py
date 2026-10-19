from django.test import TestCase

from .models import Usuario


class PinTests(TestCase):
    def test_pin_se_guarda_como_hash(self):
        u = Usuario.objects.create_user("op1", password="x")
        u.set_pin("1234")
        u.save()
        self.assertNotIn("1234", u.pin)
        self.assertTrue(u.check_pin("1234"))
        self.assertFalse(u.check_pin("0000"))
