"""
Tests para verificación en dos pasos (2FA) con Twilio SMS.
Subtareas: PTCJMGA-188, PTCJMGA-189, PTCJMGA-192, PTCJMGA-194
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from accounts.models import SystemUser, Role, LegalRoom, OTPCode, Secretary


class OTPCodeModelTest(TestCase):
    """PTCJMGA-188: Tests del modelo OTPCode."""

    def setUp(self):
        self.role = Role.objects.create(name="secretaria")
        self.sala = LegalRoom.objects.create(name="Civil")
        self.user = SystemUser.objects.create_user(
            email="sec@icesi.edu.co",
            name="Ana López",
            password="Pass1234!",
            role=self.role,
            room=self.sala,
            phone="+573156963470",
            otp_enabled=True,
        )

    def test_generate_crea_codigo_de_6_digitos(self):
        """PTCJMGA-188: OTPCode.generate() crea un código de 6 dígitos."""
        otp = OTPCode.generate(self.user)
        self.assertEqual(len(otp.code), 6)
        self.assertTrue(otp.code.isdigit())

    def test_codigo_valido_recien_creado(self):
        """PTCJMGA-188: Un OTP recién creado es válido."""
        otp = OTPCode.generate(self.user)
        self.assertTrue(otp.is_valid())

    def test_codigo_invalido_si_ya_usado(self):
        """PTCJMGA-188: Un OTP marcado como usado no es válido."""
        otp = OTPCode.generate(self.user)
        otp.is_used = True
        otp.save()
        self.assertFalse(otp.is_valid())

    def test_codigo_invalido_si_expirado(self):
        """PTCJMGA-188: Un OTP expirado (más de 10 min) no es válido."""
        otp = OTPCode.generate(self.user)
        otp.created_at = timezone.now() - timedelta(minutes=11)
        otp.save()
        self.assertFalse(otp.is_valid())

    def test_codigo_valido_exactamente_a_los_9_minutos(self):
        """PTCJMGA-188: Un OTP de 9 minutos sigue siendo válido."""
        otp = OTPCode.generate(self.user)
        otp.created_at = timezone.now() - timedelta(minutes=9)
        otp.save()
        self.assertTrue(otp.is_valid())


class LoginStep1ViewTest(TestCase):
    """PTCJMGA-189: Tests del primer paso del login (credenciales)."""

    def setUp(self):
        self.client = Client()
        self.role = Role.objects.create(name="secretaria")
        self.sala = LegalRoom.objects.create(name="Civil")

        # Usuario CON 2FA habilitado
        self.user_2fa = SystemUser.objects.create_user(
            email="sec2fa@icesi.edu.co",
            name="Con 2FA",
            password="Pass1234!",
            role=self.role,
            room=self.sala,
            phone="+573156963470",
            otp_enabled=True,
        )
        Secretary.objects.create(user=self.user_2fa)

        # Usuario SIN 2FA
        self.user_no2fa = SystemUser.objects.create_user(
            email="secno2fa@icesi.edu.co",
            name="Sin 2FA",
            password="Pass1234!",
            role=self.role,
            room=self.sala,
            otp_enabled=False,
        )
        Secretary.objects.create(user=self.user_no2fa)

    def test_get_login_carga_formulario(self):
        """PTCJMGA-189: GET /accounts/login/ retorna 200."""
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)

    @patch("accounts.views._send_otp_sms")
    def test_login_con_2fa_redirige_a_otp_verify(self, mock_sms):
        """PTCJMGA-189: Usuario con 2FA habilitado es redirigido a verificación OTP."""
        mock_sms.return_value = None
        response = self.client.post(reverse("accounts:login"), {
            "username": "sec2fa@icesi.edu.co",
            "password": "Pass1234!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("otp", response["Location"])
        mock_sms.assert_called_once()

    @patch("accounts.views._send_otp_sms")
    def test_login_con_2fa_guarda_user_id_en_sesion(self, mock_sms):
        """PTCJMGA-189: El user_id se guarda en sesión durante el paso 1."""
        mock_sms.return_value = None
        self.client.post(reverse("accounts:login"), {
            "username": "sec2fa@icesi.edu.co",
            "password": "Pass1234!",
        })
        self.assertIn("_2fa_user_id", self.client.session)
        self.assertEqual(self.client.session["_2fa_user_id"], self.user_2fa.pk)

    def test_login_sin_2fa_redirige_al_dashboard(self):
        """PTCJMGA-189: Usuario sin 2FA hace login directo sin pasar por OTP."""
        response = self.client.post(reverse("accounts:login"), {
            "username": "secno2fa@icesi.edu.co",
            "password": "Pass1234!",
        })
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("otp", response["Location"])

    def test_credenciales_incorrectas_no_redirigen(self):
        """PTCJMGA-192: Contraseña incorrecta retorna 200 sin enviar SMS."""
        response = self.client.post(reverse("accounts:login"), {
            "username": "sec2fa@icesi.edu.co",
            "password": "PasswordMal!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_2fa_user_id", self.client.session)


class OTPVerifyViewTest(TestCase):
    """PTCJMGA-189, PTCJMGA-192, PTCJMGA-194: Tests del segundo paso (verificación OTP)."""

    def setUp(self):
        self.client = Client()
        self.role = Role.objects.create(name="secretaria")
        self.sala = LegalRoom.objects.create(name="Civil")
        self.user = SystemUser.objects.create_user(
            email="sec@icesi.edu.co",
            name="Ana López",
            password="Pass1234!",
            role=self.role,
            room=self.sala,
            phone="+573156963470",
            otp_enabled=True,
        )
        Secretary.objects.create(user=self.user)

    def _set_session(self):
        """Simula que el paso 1 del login ya fue completado."""
        session = self.client.session
        session["_2fa_user_id"] = self.user.pk
        session["_2fa_backend"] = "accounts.backends.SystemUserBackend"
        session.save()

    def test_get_otp_verify_sin_sesion_redirige_login(self):
        """PTCJMGA-189: Sin sesión de paso 1, redirige al login."""
        response = self.client.get(reverse("accounts:otp-verify"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_get_otp_verify_con_sesion_carga_formulario(self):
        """PTCJMGA-189: Con sesión válida, GET retorna 200."""
        self._set_session()
        response = self.client.get(reverse("accounts:otp-verify"))
        self.assertEqual(response.status_code, 200)

    def test_codigo_correcto_autentica_y_redirige(self):
        """PTCJMGA-189: Código OTP correcto y válido autentica al usuario."""
        self._set_session()
        otp = OTPCode.generate(self.user)
        response = self.client.post(reverse("accounts:otp-verify"), {"code": otp.code})
        self.assertEqual(response.status_code, 302)
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    def test_codigo_incorrecto_retorna_200_con_error(self):
        """PTCJMGA-192: Código OTP incorrecto retorna 200 con error."""
        self._set_session()
        OTPCode.generate(self.user)
        response = self.client.post(reverse("accounts:otp-verify"), {"code": "000000"})
        self.assertEqual(response.status_code, 200)

    def test_codigo_expirado_redirige_al_login(self):
        """PTCJMGA-192: Código expirado redirige al login."""
        self._set_session()
        otp = OTPCode.generate(self.user)
        otp.created_at = timezone.now() - timedelta(minutes=11)
        otp.save()
        response = self.client.post(reverse("accounts:otp-verify"), {"code": otp.code})
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_codigo_ya_usado_no_autentica(self):
        """PTCJMGA-194: Código ya usado no permite autenticación."""
        self._set_session()
        otp = OTPCode.generate(self.user)
        otp.is_used = True
        otp.save()
        response = self.client.post(reverse("accounts:otp-verify"), {"code": otp.code})
        self.assertEqual(response.status_code, 200)

    def test_codigo_usado_una_vez_no_reutilizable(self):
        """PTCJMGA-194: Usar el código lo marca como usado, no se puede reutilizar."""
        self._set_session()
        otp = OTPCode.generate(self.user)
        self.client.post(reverse("accounts:otp-verify"), {"code": otp.code})
        # Intentar usar el mismo código de nuevo
        self._set_session()
        response = self.client.post(reverse("accounts:otp-verify"), {"code": otp.code})
        self.assertEqual(response.status_code, 200)


class SendOTPSMSTest(TestCase):
    """PTCJMGA-188: Tests del servicio de envío de SMS con Twilio."""

    def setUp(self):
        self.role = Role.objects.create(name="secretaria")
        self.sala = LegalRoom.objects.create(name="Civil")
        self.user = SystemUser.objects.create_user(
            email="sec@icesi.edu.co",
            name="Ana López",
            password="Pass1234!",
            role=self.role,
            room=self.sala,
            phone="+573156963470",
            otp_enabled=True,
        )

    @patch("accounts.views.TwilioClient")
    def test_send_otp_llama_a_twilio(self, MockTwilio):
        """PTCJMGA-188: _send_otp_sms llama a Twilio con los parámetros correctos."""
        mock_client = MagicMock()
        MockTwilio.return_value = mock_client

        from accounts.views import _send_otp_sms
        _send_otp_sms("+573156963470", "123456")

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        self.assertIn("123456", call_kwargs["body"])
        self.assertEqual(call_kwargs["to"], "+573156963470")

    @patch("accounts.views.TwilioClient")
    def test_send_otp_error_twilio_no_rompe_el_flujo(self, MockTwilio):
        """PTCJMGA-188: Si Twilio falla, la excepción se propaga para ser manejada en la vista."""
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("Twilio error")
        MockTwilio.return_value = mock_client

        from accounts.views import _send_otp_sms
        with self.assertRaises(Exception):
            _send_otp_sms("+573156963470", "123456")