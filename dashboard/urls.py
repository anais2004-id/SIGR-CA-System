from django.urls import path
from . import views

urlpatterns = [
    # ── Page d'accueil ──────────────────────────────────────────────────
    path('', views.login_view, name='home'),

    # ── Authentification ────────────────────────────────────────────────
    path('login/',    views.login_view,    name='login'),
    path('logout/',   views.logout_view,   name='logout'),
    path('register/', views.register_employe, name='register_employe'),

    # Redirections compatibilité (anciennes URLs employé)
    path('employe/login/',    views.login_view,       name='login_employe'),
    path('employe/register/', views.register_employe, name='register_employe_alt'),
    path('employe/logout/',   views.logout_view,       name='employe_logout'),

    # ── Espace Employé ──────────────────────────────────────────────────
    path('employe/',                                          views.employe_espace,             name='employe_espace'),
    path('employe/reservations/',                             views.employe_mes_reservations,   name='employe_mes_reservations'),
    path('employe/historique/',                               views.employe_mon_historique,     name='employe_mon_historique'),
    path('employe/reservations/<str:reservation_id>/annuler/', views.employe_annuler_reservation, name='employe_annuler_reservation'),

    # ── Dashboard Admin ─────────────────────────────────────────────────
    path('dashboard/', views.dashboard, name='dashboard'),

    # ── Employés ────────────────────────────────────────────────────────
    path('employes/',                          views.employe_list,     name='employe_list'),
    path('employes/ajouter/',                  views.employe_ajouter,  name='employe_ajouter'),
    path('employes/<str:employe_id>/',         views.employe_detail,   name='employe_detail'),
    path('employes/<str:employe_id>/modifier/', views.employe_modifier, name='employe_modifier'),
    path('employes/<str:employe_id>/supprimer/', views.employe_supprimer, name='employe_supprimer'),

    # ── Pages Admin ─────────────────────────────────────────────────────
    path('historique/',   views.historique,   name='historique'),
    path('live/',         views.live,         name='live'),
    path('ressources/',   views.ressources,   name='ressources'),
    path('calendrier/',   views.calendrier,   name='calendrier'),
    path('statistiques/', views.statistiques, name='statistiques'),
    path('parametres/',   views.parametres,   name='parametres'),

    # ── Bureaux ─────────────────────────────────────────────────────────
    path('bureaux/ajouter/',           views.bureau_ajouter, name='bureau_ajouter'),
    path('bureaux/<str:bureau_id>/',   views.bureau_detail,  name='bureau_detail'),

    # ── Équipements ─────────────────────────────────────────────────────
    path('equipements/',                                   views.equipement_list,     name='equipement_list'),
    path('equipements/ajouter/',                           views.equipement_ajouter,  name='equipement_ajouter'),
    path('equipements/<str:equipement_id>/',               views.equipement_detail,   name='equipement_detail'),
    path('equipements/<str:equipement_id>/modifier/',      views.equipement_modifier, name='equipement_modifier'),
    path('equipements/<str:equipement_id>/supprimer/',     views.equipement_supprimer, name='equipement_supprimer'),
    path('equipements/<str:equipement_id>/tester/',        views.equipement_tester,   name='equipement_tester'),

    # ── Réservations Admin ──────────────────────────────────────────────
    path('reservations/',                                  views.reservation_list,    name='reservation_list'),
    path('reservations/ajouter/',                          views.reservation_ajouter, name='reservation_ajouter'),
    path('reservations/<str:reservation_id>/modifier/',    views.reservation_modifier, name='reservation_modifier'),
    path('reservations/<str:reservation_id>/annuler/',     views.reservation_annuler, name='reservation_annuler'),

    # ── API Calendrier & règles ──────────────────────────────────────────
    path('api/employee/<str:employe_id>/rules/', views.api_get_employee_rules, name='api_employee_rules'),
    path('api/save-day-rules/',                   views.api_save_day_rules,     name='api_save_day_rules'),
    path('api/save-all-rules/',                   views.api_save_all_rules,     name='api_save_all_rules'),
    path('api/bureaux/',                           views.api_bureaux,            name='api_bureaux'),

    # ── API Occupation & stats ───────────────────────────────────────────
    path('api/occupation/',                          views.api_occupation,    name='api_occupation'),
    path('api/bureau/<str:bureau_id>/stats/',        views.api_bureau_stats,  name='api_bureau_stats'),
    path('api/stats/trend/',                          views.api_stats_trend,   name='api_stats_trend'),

    # ── API Live & urgence ───────────────────────────────────────────────
    path('api/live-feed/',         views.api_live_feed,         name='api_live_feed'),
    path('api/emergency-unlock/',  views.api_emergency_unlock,  name='api_emergency_unlock'),

    # ── API Équipements ──────────────────────────────────────────────────
    path('api/equipements/',                                  views.api_equipements,        name='api_equipements'),
    path('api/equipements/<str:equipement_id>/logs/',         views.api_equipement_logs,    name='api_equipement_logs'),
    path('api/equipements/<str:equipement_id>/commande/',     views.api_equipement_commande, name='api_equipement_commande'),

    # ── API Réservations ────────────────────────────────────────────────
    path('api/reservations/calendrier/',                          views.api_reservations_calendrier, name='api_reservations_calendrier'),
    path('api/reservations/active/',                              views.api_reservations_active,     name='api_reservations_active'),
    path('api/bureaux/<str:bureau_id>/disponibilite/',            views.api_disponibilite_bureau,    name='api_disponibilite_bureau'),

    # ── API Ressources ───────────────────────────────────────────────────
    path('api/resources/top/', views.api_resources_top, name='api_resources_top'),

    # ── API Employé (historique modal) ──────────────────────────────────
    path('api/employee/<str:employe_id>/history/', views.api_employee_history, name='api_employee_history'),

    # ── API Admin Profil ─────────────────────────────────────────────────
    path('api/admin/profile/update/', views.update_admin_profile, name='update_admin_profile'),
    path('api/admin/avatar/',          views.update_admin_avatar,   name='update_admin_avatar'),
    path('api/admin/login-history/',   views.admin_login_history,   name='admin_login_history'),

    # ── API Paramètres ────────────────────────────────────────────────────
    path('api/parametres/save/', views.api_parametres_save, name='api_parametres_save'),
    # Ajouter dans urls.py, à la fin du tableau urlpatterns

    # ── Gestion des ressources ─────────────────────────────────────────
    path('resources/',                               views.resource_list,      name='resource_list'),
    path('resources/ajouter/',                       views.resource_ajouter,   name='resource_ajouter'),
    path('resources/<str:resource_id>/modifier/',    views.resource_modifier,  name='resource_modifier'),
    path('resources/<str:resource_id>/supprimer/',   views.resource_supprimer, name='resource_supprimer'),
    
    # ── API Ressources ──────────────────────────────────────────────────
    path('api/resources/',                           views.api_resources,      name='api_resources'),
    
    # ── API Contrôle d'accès physique ───────────────────────────────────
    path('api/verify-access/',                       views.api_verify_access,  name='api_verify_access'),
    
    # ── API Notifications ───────────────────────────────────────────────
    path('api/send-notification/',                   views.api_send_notification, name='api_send_notification'),
    path('api/alerts/',                              views.api_alerts,         name='api_alerts'),
    
    # ── API Statistiques avancées ───────────────────────────────────────
    path('api/stats/predictions/',                   views.api_stats_predictions, name='api_stats_predictions'),
    
    # ── Réservations avancées ───────────────────────────────────────────
    path('reservations/ajouter/avance/',             views.reservation_ajouter_avance, name='reservation_ajouter_avance'),
    # urls.py - Ajouter ces lignes

   # dashboard/urls.py - Ajoutez ces lignes dans urlpatterns

    # ── Gestion des sessions actives ─────────────────────────────────────
    path('active-sessions/',                views.active_sessions,        name='active_sessions'),
    path('terminate-session/<int:session_id>/', views.terminate_session,  name='terminate_session'),
    path('terminate-all-sessions/',         views.terminate_all_sessions, name='terminate_all_sessions'),
    path('api/connected-users/',            views.api_connected_users,    name='api_connected_users'),
    # dashboard/urls.py - Ajoutez ces lignes si elles n'existent pas

    # ── API Réservations ────────────────────────────────────────────────
    path('api/reservations/calendrier/', views.api_reservations_calendrier, name='api_reservations_calendrier'),
    path('api/reservations/<str:reservation_id>/details/', views.api_reservation_details, name='api_reservation_details'),
    
    # ── Réservations Employé ────────────────────────────────────────────
    path('employe/reservations/', views.employe_mes_reservations, name='employe_mes_reservations'),
    path('employe/reservations/<str:reservation_id>/annuler/', views.employe_annuler_reservation, name='employe_annuler_reservation'),
    path('api/bureaux/<str:bureau_id>/disponibilite/', views.api_disponibilite_bureau, name='api_disponibilite_bureau'),
     path('api/reservations/calendrier/', views.api_reservations_calendrier, name='api_reservations_calendrier'),
      path('api/reservations/<str:reservation_id>/details/', views.api_reservation_details, name='api_reservation_details'),
       path('employe/profil/', views.employe_profil, name='employe_profil'),
    path('employe/change-password/', views.employe_change_password, name='employe_change_password'),
     # ── Gestion des réservations admin ──────────────────────────────────
    path('reservations/',                          views.reservation_list,        name='reservation_list'),
    path('reservations/<str:reservation_id>/',     views.reservation_detail,      name='reservation_detail'),
    path('reservations/<str:reservation_id>/confirmer/', views.reservation_confirmer, name='reservation_confirmer'),
    path('reservations/<str:reservation_id>/refuser/',    views.reservation_refuser,  name='reservation_refuser'),
    
    # ── API QR Code ──────────────────────────────────────────────────────
    path('api/reservations/<str:reservation_id>/qr/', views.api_reservation_qr,      name='api_reservation_qr'),
path('api/stats/overview/', views.api_stats_overview, name='api_stats_overview'),
path('api/stats/occupation/', views.api_occupation_stats, name='api_occupation_stats'),
path('api/stats/top-ressources/', views.api_top_ressources, name='api_top_ressources'),
path('api/stats/weekly-schedule/', views.api_weekly_schedule, name='api_weekly_schedule'),
path('api/stats/hour/', views.api_hour_stats, name='api_hour_stats'),
# Export statistiques
    path('dashboard/api/stats/export/csv/', views.api_stats_export_csv, name='api_stats_export_csv'),
    path('dashboard/api/stats/export/pdf/', views.api_stats_export_pdf, name='api_stats_export_pdf'),
    path('dashboard/api/stats/departement/', views.api_stats_departement, name='api_stats_departement'),
    path('dashboard/api/stats/period-custom/', views.api_stats_period_custom, name='api_stats_period_custom'),
    path('dashboard/api/stats/trend-cache/', views.api_stats_trend_cache, name='api_stats_trend_cache'),
# Ajoutez ces lignes
path('active-sessions/', views.active_sessions, name='active_sessions'),
path('terminate-session/<int:session_id>/', views.terminate_session, name='terminate_session'),
path('terminate-all-sessions/', views.terminate_all_sessions, name='terminate_all_sessions'),
path('api/connected-users/', views.api_connected_users, name='api_connected_users'),
path('api/session-stats/', views.api_session_stats, name='api_session_stats'),
path('api/session-details/<int:session_id>/', views.api_session_details, name='api_session_details'),
path('clear-session-history/', views.clear_session_history, name='clear_session_history'),
# Ajoutez ces routes
path('api/bureau/<str:bureau_id>/stats/', views.api_bureau_stats, name='api_bureau_stats'),
path('api/materiel/list/', views.api_materiel_list, name='api_materiel_list'),
path('api/materiel/ajouter/', views.api_materiel_ajouter, name='api_materiel_ajouter'),
path('api/materiel/<str:materiel_id>/supprimer/', views.api_materiel_supprimer, name='api_materiel_supprimer'),
path('bureau/supprimer/<str:bureau_id>/', views.bureau_supprimer, name='bureau_supprimer'),

# Gestion des ressources (bureaux/zones)
    path('ressources/', views.ressources, name='ressources'),
    path('bureaux/ajouter/', views.bureau_ajouter, name='bureau_ajouter'),
    path('bureaux/<str:bureau_id>/', views.bureau_detail, name='bureau_detail'),
    path('bureaux/<str:bureau_id>/supprimer/', views.bureau_supprimer, name='bureau_supprimer'),
    # Ajoutez ces routes pour le profil employé
path('employe/profil/', views.employe_profil, name='employe_profil'),
path('employe/change-password/', views.employe_change_password, name='employe_change_password'),
path('api/save-preferences/', views.api_save_preferences, name='api_save_preferences'),
path('api/employee/stats/', views.api_employee_stats, name='api_employee_stats'),
path('api/employee/update-profil/', views.employe_update_profil, name='employe_update_profil'),
# Notifications employé
path('employe/notifications/', views.employe_notifications, name='employe_notifications'),
path('employe/notifications/mark-read/', views.employe_notifications, name='employe_notifications_mark_read'),
path('api/send-test-notification/', views.api_send_test_notification, name='api_send_test_notification'),
# Centre d'aide
path('employe/aide/', views.employe_aide, name='employe_aide'),
# dashboard/urls.py - Ajoutez ces lignes dans urlpatterns

# ── Espace Employé - Nouvelles fonctionnalités ──────────────────────────
path('employe/notifications/', views.employe_notifications, name='employe_notifications'),
path('employe/plan-zones/', views.employe_plan_zones, name='employe_plan_zones'),
path('employe/badge-virtuel/', views.employe_badge_virtuel, name='employe_badge_virtuel'),
path('employe/aide/', views.employe_aide, name='employe_aide'),

# API pour les notifications
path('api/save-preferences/', views.api_save_preferences, name='api_save_preferences'),
path('api/employee/stats/', views.api_employee_stats, name='api_employee_stats'),
# Dans urls.py
path('api/reservations/<str:reservation_id>/qr/', views.api_reservation_qr, name='api_reservation_qr'),
path('api/reservations/<str:reservation_id>/duplicate/', views.api_reservation_duplicate, name='api_reservation_duplicate'),
path('api/bureaux/<str:bureau_id>/schedule/', views.api_bureau_schedule, name='api_bureau_schedule'),
path('api/bureaux/<str:bureau_id>/suggestions/', views.api_bureau_suggestions, name='api_bureau_suggestions'),
# Chatbot
path('api/chatbot/message/', views.api_chatbot_message, name='api_chatbot_message'),
path('api/chatbot/conversations/', views.api_chatbot_conversations, name='api_chatbot_conversations'),
path('api/chatbot/conversation/<int:conversation_id>/', views.api_chatbot_conversation_detail, name='api_chatbot_conversation_detail'),
# dashboard/urls.py
# dashboard/urls.py - Ajoutez ces routes

path('employe/notifications/', views.employe_notifications, name='employe_notifications'),
path('api/notifications/mark-read/', views.api_mark_notification_read, name='api_mark_notification_read'),
path('api/notifications/delete/', views.api_delete_notification, name='api_delete_notification'),
path('api/notifications/delete-all/', views.api_delete_all_notifications, name='api_delete_all_notifications'),
path('api/notifications/test/', views.api_send_test_notification, name='api_send_test_notification'),
path('api/notifications/unread-count/', views.api_notifications_unread_count, name='api_notifications_unread_count'),
path('api/reservations/<str:reservation_id>/qr/', views.api_reservation_qr, name='api_reservation_qr'),

# dashboard/urls.py

# Notifications Admin - Utilisez le préfixe dashboard/
# dashboard/urls.py - Extrait

# Notifications Admin (après avoir changé le chemin)
path('dashboard/notifications/', views.admin_notifications, name='admin_notifications'),
path('api/admin/notifications/unread-count/', views.api_admin_notifications_unread_count, name='api_admin_notifications_unread_count'),
path('api/admin/notifications/mark-read/', views.api_admin_mark_notification_read, name='api_admin_mark_notification_read'),
path('api/admin/notifications/delete/', views.api_admin_delete_notification, name='api_admin_delete_notification'),
path('api/admin/notifications/test/', views.api_admin_send_test_notification, name='api_admin_send_test_notification'),

path('api/materiel/ajouter/', views.api_materiel_ajouter, name='api_materiel_ajouter'),
path('api/materiel/<str:materiel_id>/supprimer/', views.api_materiel_supprimer, name='api_materiel_supprimer'),
path('api/export/ressources/csv/', views.api_export_ressources_csv, name='api_export_ressources_csv'),
# ── Mot de passe oublié ──────────────────────────────────────────────────────
path('password-forgot/', views.password_forgot, name='password_forgot'),
path('password-reset/<str:token>/', views.password_reset, name='password_reset'),
path('password-reset-done/', views.password_reset_done, name='password_reset_done'),]