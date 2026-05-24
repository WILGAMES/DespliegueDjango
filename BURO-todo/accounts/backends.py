from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.backends import ModelBackend
from .models import SystemUser, Beneficiary


class BeneficiaryBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # Intenta buscar por correo o por documento
            if '@' in str(username):
                user = Beneficiary.objects.get(email=username)
            else:
                user = Beneficiary.objects.get(document=username)
        except Beneficiary.DoesNotExist:
            return None

        if user.check_password(password) and user.is_active:
            return user
        return None

    def get_user(self, user_id):
        try:
            return Beneficiary.objects.get(pk=user_id)
        except Beneficiary.DoesNotExist:
            return None



class BeneficiaryBackend(ModelBackend):
    """
    Allows beneficiaries to log in with document number or email + password.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            if username and username.replace(' ', '').isdigit():
                user = Beneficiary.objects.get(document=username)
            else:
                user = Beneficiary.objects.get(email=username)
        except Beneficiary.DoesNotExist:
            return None

        if user.check_password(password) and user.is_active:
            return user
        return None

    def get_user(self, user_id):
        try:
            return Beneficiary.objects.get(pk=user_id)
        except Beneficiary.DoesNotExist:
            return None


class SystemUserBackend(ModelBackend):
    """
    Allows internal users (secretary, student, professor, admin) to log in with email.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = SystemUser.objects.get(email=username)
        except SystemUser.DoesNotExist:
            return None

        if user.check_password(password) and user.is_active:
            return user
        return None

    def get_user(self, user_id):
        try:
            return SystemUser.objects.get(pk=user_id)
        except SystemUser.DoesNotExist:
            return None
        

