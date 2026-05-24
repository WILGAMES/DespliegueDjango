#this is the notifications/models.py file
from django.db import models


class FailedNotification(models.Model):
    to            = models.EmailField()
    subject       = models.CharField(max_length=255)
    body          = models.TextField()
    error_message = models.TextField()
    failed_at     = models.DateTimeField(auto_now_add=True)
    resolved      = models.BooleanField(default=False)
    resolved_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table     = 'notificacion_fallida'
        verbose_name = 'Failed Notification'
        verbose_name_plural = 'Failed Notifications'
        ordering = ['-failed_at']

    def __str__(self):
        return f'{self.subject} → {self.to} ({self.failed_at})'