from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone

from accounts.utils import validate_coordinator
from notifications.models import FailedNotification
from notifications.services import send_notification


class FailedNotificationListView(LoginRequiredMixin, View):

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticación requerida'}, status=401)

    def get(self, request):
        try:
            validate_coordinator(request.user)
        except Exception:
            return JsonResponse({'error': 'Acceso denegado'}, status=403)

        pendientes = FailedNotification.objects.filter(resolved=False).values(
            'id', 'to', 'subject', 'body', 'error_message', 'failed_at'
        )

        return JsonResponse({'failed_notifications': list(pendientes)})


class RetryNotificationView(LoginRequiredMixin, View):

    def handle_no_permission(self):
        return JsonResponse({'error': 'Autenticación requerida'}, status=401)

    def post(self, request, pk):
        try:
            validate_coordinator(request.user)
        except Exception:
            return JsonResponse({'error': 'Acceso denegado'}, status=403)

        try:
            notif = FailedNotification.objects.get(pk=pk)
        except FailedNotification.DoesNotExist:
            return JsonResponse({'error': 'Notificación no encontrada'}, status=404)

        try:
            send_notification(to=notif.to, subject=notif.subject, body=notif.body)
            notif.resolved = True
            notif.resolved_at = timezone.now()
            notif.save()
            return JsonResponse({'status': 'enviado'})
        except Exception as e:
            notif.error_message = str(e)
            notif.save()
            return JsonResponse({'status': 'fallo', 'error': str(e)})