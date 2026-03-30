from django.urls import path
from . import views

urlpatterns = [
    # Page d'accueil - redirige vers login si pas connecté, sinon vers le bon espace
    path('', views.login_view, name='home'),
    
    # Authentification unique
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Inscription employé
    path('register/', views.register_employe, name='register_employe'),
    
    # Redirections pour compatibilité (anciennes URLs employé)
    path('employe/login/', views.login_view, name='login_employe'),
    path('employe/register/', views.register_employe, name='register_employe'),
    path('employe/logout/', views.logout_view, name='employe_logout'),
    
    # Espace Employé — Pages
    path('employe/', views.employe_espace, name='employe_espace'),
    path('employe/reservations/', views.employe_mes_reservations, name='employe_mes_reservations'),
    path('employe/historique/', views.employe_mon_historique, name='employe_mon_historique'),
    path('employe/reservations/<str:reservation_id>/annuler/',
         views.employe_annuler_reservation, name='employe_annuler_reservation'),
    
    # Dashboard Admin
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # API
    path('api/occupation/', views.api_occupation, name='api_occupation'),
    path('api/bureau/<str:bureau_id>/stats/', views.api_bureau_stats, name='api_bureau_stats'),
    
    # Employés
    path('employes/', views.employe_list, name='employe_list'),
    path('employes/ajouter/', views.employe_ajouter, name='employe_ajouter'),
    path('employes/<str:employe_id>/', views.employe_detail, name='employe_detail'),
    path('employes/<str:employe_id>/modifier/', views.employe_modifier, name='employe_modifier'),
    path('employes/<str:employe_id>/supprimer/', views.employe_supprimer, name='employe_supprimer'),
    
    # Autres pages admin
    path('historique/', views.historique, name='historique'),
    path('live/', views.live, name='live'),
    path('ressources/', views.ressources, name='ressources'),
    path('calendrier/', views.calendrier, name='calendrier'),
    path('statistiques/', views.statistiques, name='statistiques'),
    path('parametres/', views.parametres, name='parametres'),
    
    # Ajout bureau
    path('bureaux/ajouter/', views.bureau_ajouter, name='bureau_ajouter'),
    
    # API Calendrier et règles
    path('api/employee/<str:employe_id>/rules/', views.api_get_employee_rules, name='api_employee_rules'),
    path('api/save-day-rules/', views.api_save_day_rules, name='api_save_day_rules'),
    path('api/save-all-rules/', views.api_save_all_rules, name='api_save_all_rules'),
    path('api/bureaux/', views.api_bureaux, name='api_bureaux'),
    
    # Équipements
    path('equipements/', views.equipement_list, name='equipement_list'),
    path('equipements/ajouter/', views.equipement_ajouter, name='equipement_ajouter'),
    path('equipements/<str:equipement_id>/', views.equipement_detail, name='equipement_detail'),
    path('equipements/<str:equipement_id>/modifier/', views.equipement_modifier, name='equipement_modifier'),
    path('equipements/<str:equipement_id>/supprimer/', views.equipement_supprimer, name='equipement_supprimer'),
    path('equipements/<str:equipement_id>/tester/', views.equipement_tester, name='equipement_tester'),
    
    # API Équipements
    path('api/equipements/', views.api_equipements, name='api_equipements'),
    path('api/equipements/<str:equipement_id>/logs/', views.api_equipement_logs, name='api_equipement_logs'),
    path('api/equipements/<str:equipement_id>/commande/', views.api_equipement_commande, name='api_equipement_commande'),
    
    # Réservations Admin
    path('reservations/', views.reservation_list, name='reservation_list'),
    path('reservations/ajouter/', views.reservation_ajouter, name='reservation_ajouter'),
    path('reservations/<str:reservation_id>/modifier/', views.reservation_modifier, name='reservation_modifier'),
    path('reservations/<str:reservation_id>/annuler/', views.reservation_annuler, name='reservation_annuler'),
    
    # API Réservations
    path('api/reservations/calendrier/', views.api_reservations_calendrier, name='api_reservations_calendrier'),
    path('api/bureaux/<str:bureau_id>/disponibilite/', views.api_disponibilite_bureau, name='api_disponibilite_bureau'),
]