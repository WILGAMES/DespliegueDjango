from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.report_list_view, name='list'),
    path('generar/', views.report_generate_view, name='generate'),
    path('<int:pk>/', views.report_detail_view, name='detail'),
    path('<int:pk>/pdf/', views.report_export_pdf_view, name='export-pdf'),
    path('<int:pk>/csv/', views.report_export_csv_view, name='export-csv'),
]
