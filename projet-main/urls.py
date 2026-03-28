# dashboard/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('api/occupation/', views.api_occupation, name='api_occupation'),
    path('bureau/<str:bureau_id>/', views.bureau_detail, name='bureau_detail'),
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/bureau/<str:bureau_id>/stats/', views.api_bureau_stats, name='api_bureau_stats'),
    
    # NOUVELLES ROUTES POUR LES EMPLOYÉS
    path('employes/', views.employe_list, name='employe_list'),
    path('employes/ajouter/', views.employe_ajouter, name='employe_ajouter'),
    path('employes/<str:employe_id>/', views.employe_detail, name='employe_detail'),
    path('employes/<str:employe_id>/modifier/', views.employe_modifier, name='employe_modifier'),
    path('employes/<str:employe_id>/supprimer/', views.employe_supprimer, name='employe_supprimer'),
    path('api/employes/', views.api_employes, name='api_employes'),
    path('api/employes/<str:employe_id>/acces/', views.api_employe_acces, name='api_employe_acces'),
]