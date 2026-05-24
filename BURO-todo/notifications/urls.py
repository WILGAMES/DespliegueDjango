from django.urls import path
from notifications.views import FailedNotificationListView, RetryNotificationView

app_name = 'notifications'

urlpatterns = [
    path('failed/', FailedNotificationListView.as_view(), name='failed-list'),
    path('failed/<int:pk>/retry/', RetryNotificationView.as_view(), name='retry'),
]