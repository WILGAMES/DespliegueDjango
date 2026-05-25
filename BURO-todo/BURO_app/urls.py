"""
URL configuration for BURO_app project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import include
from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect, render
from accounts.views import academic_dashboard_view, custom_404_view
from cases.views import academic_action_traceability_view

handler404 = custom_404_view

def home_view(request):
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    return render(request, 'accounts/home.html')

urlpatterns = [
    path('', home_view, name='home'),
    path('admin/', admin.site.urls),
    path('academic-dashboard/', academic_dashboard_view, name='academic-dashboard-root'),
    path(
        'academic-actions/<int:id>/traceability/',
        academic_action_traceability_view,
        name='academic-action-traceability',
    ),
    path('accounts/', include('accounts.urls')),
    path('cases/', include('cases.urls')),
    path('notifications/', include('notifications.urls')),
    path('reports/', include('reports.urls')),
]
