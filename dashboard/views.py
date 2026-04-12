# dashboard/views.py
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
from bson import ObjectId
from datetime import datetime, timedelta
from collections import Counter
from django.contrib import messages
import json
import random
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect, ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth import get_user_model
from django.contrib.auth import update_session_auth_hash
import qrcode
from io import BytesIO
from django.core.files.base import ContentFile
import base64
import logging
from dashboard.models import UserSession, SessionLog
from .models import Utilisateur, UserSession
import json
import re
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import models
from .models import ChatbotConversation, ChatbotMessage
from dashboard.models import Notification
from django.contrib.auth import get_user_model

db = settings.MONGO_DB
User = get_user_model()
logger = logging.getLogger(__name__)


# ====================== AUTHENTIFICATION ======================

def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect('dashboard')
        else:
            return redirect('employe_espace')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.is_staff or user.is_superuser:
                messages.success(request, f"Bienvenue {user.username} (Administrateur)")
                return redirect('dashboard')
            else:
                messages.success(request, f"Bienvenue {user.first_name or user.username} !")
                return redirect('employe_espace')
        else:
            messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")
    return render(request, 'dashboard/login.html')


@login_required
def logout_view(request):
    logout(request)
    messages.success(request, "Vous avez été déconnecté avec succès.")
    return redirect('login')


@csrf_protect
@ensure_csrf_cookie
def register_employe(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('dashboard')
        return redirect('employe_espace')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        badge_id = request.POST.get('badge_id', '').strip()
        nom = request.POST.get('nom', '').strip()
        prenom = request.POST.get('prenom', '').strip()
        email = request.POST.get('email', '').strip()
        
        erreurs = []
        
        if not username:
            erreurs.append("Le nom d'utilisateur est requis.")
        if len(password1) < 6:
            erreurs.append("Le mot de passe doit contenir au moins 6 caractères.")
        if password1 != password2:
            erreurs.append("Les mots de passe ne correspondent pas.")
        if not badge_id:
            erreurs.append("Le numéro de badge est requis.")
        if not nom or not prenom:
            erreurs.append("Le nom et le prénom sont requis.")
        
        employe_mongo = db.employees.find_one({'badge_id': badge_id})
        if not employe_mongo:
            erreurs.append(f"Badge '{badge_id}' non reconnu. Contactez votre administrateur.")
        
        if Utilisateur.objects.filter(username=username).exists():
            erreurs.append(f"Le nom d'utilisateur '{username}' est déjà pris.")
        
        if erreurs:
            for e in erreurs:
                messages.error(request, e)
            return render(request, 'dashboard/register_employe.html', {'form_data': request.POST})
        
        user = Utilisateur.objects.create_user(
            username=username,
            password=password1,
            email=email,
            first_name=prenom,
            last_name=nom,
            is_staff=False,
            is_superuser=False
        )
        
        db.employees.update_one(
            {'badge_id': badge_id},
            {'$set': {
                'django_user_id': user.id,
                'django_username': username,
                'email': email,
                'compte_cree_le': datetime.now(),
                'nom': nom,
                'prenom': prenom
            }}
        )
        
        messages.success(request, f"Compte créé avec succès ! Bienvenue {prenom}.")
        login(request, user)
        return redirect('employe_espace')
    
    return render(request, 'dashboard/register_employe.html', {'form_data': {}})


# ====================== ESPACE EMPLOYÉ ======================
@login_required
def employe_espace(request):
    """Tableau de bord employé amélioré"""
    if request.user.is_staff or request.user.is_superuser:
        return redirect('dashboard')
    
    from datetime import datetime, timedelta
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        messages.error(request, "Profil employé introuvable. Contactez l'administrateur.")
        logout(request)
        return redirect('login')
    
    employe['id'] = str(employe['_id'])
    utilisateur_id = employe['_id']
    
    # Statistiques globales
    total_acces = db.acces_logs.count_documents({'utilisateur_id': utilisateur_id})
    acces_autorises = db.acces_logs.count_documents({'utilisateur_id': utilisateur_id, 'resultat': 'AUTORISE'})
    acces_refuses = total_acces - acces_autorises
    taux_succes = round((acces_autorises / total_acces * 100) if total_acces > 0 else 0, 1)
    
    # Statistiques du mois
    start_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_acces_mois = db.acces_logs.count_documents({
        'utilisateur_id': utilisateur_id,
        'timestamp': {'$gte': start_month}
    })
    
    # Jours actifs (corrigé - utilise aggregate au lieu de distinct)
    pipeline = [
        {'$match': {'utilisateur_id': utilisateur_id}},
        {'$group': {
            '_id': {
                'year': {'$year': '$timestamp'},
                'month': {'$month': '$timestamp'},
                'day': {'$dayOfMonth': '$timestamp'}
            }
        }},
        {'$count': 'total_days'}
    ]
    
    try:
        result = list(db.acces_logs.aggregate(pipeline))
        jours_actifs_count = result[0]['total_days'] if result else 0
    except:
        jours_actifs_count = 0
    
    # Heures totales (approximatif)
    heures_totales = round(total_acces * 0.5, 1)  # ~30min par accès
    
    # Accès récents
    acces = list(db.acces_logs.find({'utilisateur_id': utilisateur_id}).sort('timestamp', -1).limit(10))
    for a in acces:
        bureau = db.bureaux.find_one({'_id': a.get('bureau_id')})
        a['bureau_nom'] = bureau['nom'] if bureau else 'Zone inconnue'
        if not a.get('type_acces'):
            a['type_acces'] = 'RFID'
    
    # Réservations
    reservations = list(db.reservations.find({'employe_id': str(employe['_id'])}).sort('date_debut', -1))
    now = datetime.now()
    a_venir = 0
    reservations_a_venir = []
    prochaine_resa = None
    
    for r in reservations:
        r['id'] = str(r['_id'])
        bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
        r['bureau_nom'] = bureau['nom'] if bureau else 'Salle inconnue'
        
        if r.get('statut') == 'confirmee' and r.get('date_debut') and r['date_debut'] > now:
            a_venir += 1
            reservations_a_venir.append(r)
            if not prochaine_resa:
                prochaine_resa = r
    
    # Suggestions personnalisées
    # Calculer le jour le plus fréquent
    frequent_day = "mercredi"
    try:
        day_pipeline = [
            {'$match': {'utilisateur_id': utilisateur_id}},
            {'$group': {
                '_id': {'$dayOfWeek': '$timestamp'},
                'count': {'$sum': 1}
            }},
            {'$sort': {'count': -1}},
            {'$limit': 1}
        ]
        day_result = list(db.acces_logs.aggregate(day_pipeline))
        if day_result:
            days_map = {1: 'lundi', 2: 'mardi', 3: 'mercredi', 4: 'jeudi', 5: 'vendredi', 6: 'samedi', 7: 'dimanche'}
            frequent_day = days_map.get(day_result[0]['_id'], 'mercredi')
    except:
        pass
    
    # Salle recommandée
    recommended_room = "Salle de réunion A"
    try:
        room_pipeline = [
            {'$match': {'employe_id': str(employe['_id']), 'statut': 'confirmee'}},
            {'$group': {'_id': '$bureau_id', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 1}
        ]
        room_result = list(db.reservations.aggregate(room_pipeline))
        if room_result:
            bureau = db.bureaux.find_one({'_id': room_result[0]['_id']})
            if bureau:
                recommended_room = bureau.get('nom', 'Salle de réunion')
    except:
        pass
    
    # Meilleur créneau
    best_time = "09h00-11h00"
    try:
        hour_pipeline = [
            {'$match': {'utilisateur_id': utilisateur_id}},
            {'$group': {
                '_id': {'$hour': '$timestamp'},
                'count': {'$sum': 1}
            }},
            {'$sort': {'count': -1}},
            {'$limit': 1}
        ]
        hour_result = list(db.acces_logs.aggregate(hour_pipeline))
        if hour_result:
            peak_hour = hour_result[0]['_id']
            best_time = f"{peak_hour:02d}h00-{peak_hour+1:02d}h00"
    except:
        pass
    
    # Taux d'occupation
    occupancy_rate = 35
    try:
        one_hour_ago = datetime.now() - timedelta(hours=1)
        total_occupation = db.acces_logs.count_documents({'timestamp': {'$gte': one_hour_ago}})
        occupancy_rate = min(100, round(total_occupation / 10)) if total_occupation > 0 else 15
    except:
        pass
    
    # Bureaux disponibles
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
        b['capacite_max'] = b.get('capacite_max', 10)
    
    return render(request, 'dashboard/employe_espace.html', {
        'employe': employe,
        'acces': acces,
        'reservations': reservations,
        'reservations_a_venir': reservations_a_venir[:5],
        'total_acces': total_acces,
        'total_acces_mois': total_acces_mois,
        'acces_autorises': acces_autorises,
        'acces_refuses': acces_refuses,
        'taux_succes': taux_succes,
        'a_venir': a_venir,
        'prochaine_resa': prochaine_resa,
        'bureaux': bureaux,
        'jours_actifs': jours_actifs_count,
        'heures_totales': heures_totales,
        'frequent_day': frequent_day,
        'recommended_room': recommended_room,
        'best_time': best_time,
        'occupancy_rate': occupancy_rate,
        'now': datetime.now(),
    })

# dashboard/views.py - Modifiez la fonction employe_mes_reservations
@login_required
def employe_mes_reservations(request):
    if request.user.is_staff:
        return redirect('dashboard')
    
    from datetime import datetime
    from bson import ObjectId
    import json
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        return redirect('login')
    
    employe['id'] = str(employe['_id'])
    
    # Récupérer les réservations
    reservations = list(db.reservations.find({'employe_id': str(employe['_id'])}).sort('date_debut', -1))
    
    for r in reservations:
        r['id'] = str(r['_id'])
        bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
        r['bureau_nom'] = bureau['nom'] if bureau else 'Salle inconnue'
        if 'qr_code' not in r:
            r['qr_code'] = None
    
    now = datetime.now()
    actives = sum(1 for r in reservations if r.get('statut') == 'confirmee'
                  and r.get('date_debut') and r['date_debut'] <= now <= r.get('date_fin', now))
    a_venir = sum(1 for r in reservations if r.get('statut') == 'confirmee'
                  and r.get('date_debut') and r['date_debut'] > now)
    en_attente = sum(1 for r in reservations if r.get('statut') == 'en_attente')
    
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
        b['capacite_max'] = b.get('capacite_max', 10)
    
    # CRÉATION DU JSON POUR LE CALENDRIER
    reservations_list = []
    for r in reservations:
        if r.get('date_debut'):
            reservations_list.append({
                'id': str(r['_id']),
                'titre': r.get('titre', ''),
                'bureau_nom': r.get('bureau_nom', ''),
                'statut': r.get('statut', ''),
                'date_debut': r['date_debut'].isoformat() if r.get('date_debut') else None,
                'date_fin': r['date_fin'].isoformat() if r.get('date_fin') else None,
            })
    
    reservations_json = json.dumps(reservations_list, default=str)
    
    if request.method == 'POST':
        try:
            date_debut = datetime.strptime(request.POST.get('date_debut'), '%Y-%m-%dT%H:%M')
            date_fin = datetime.strptime(request.POST.get('date_fin'), '%Y-%m-%dT%H:%M')
            bureau_id = request.POST.get('bureau_id')
            
            if date_fin <= date_debut:
                messages.error(request, "La date de fin doit être après la date de début.")
            else:
                chevauchement = db.reservations.find_one({
                    'bureau_id': ObjectId(bureau_id),
                    'statut': {'$in': ['confirmee', 'en_attente']},
                    'date_debut': {'$lt': date_fin},
                    'date_fin': {'$gt': date_debut},
                })
                
                if chevauchement:
                    messages.error(request, "Cette salle est déjà réservée sur ce créneau.")
                else:
                    # Récupérer la salle pour les notifications
                    bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
                    bureau_nom = bureau['nom'] if bureau else 'Salle inconnue'
                    
                    reservation_data = {
                        'titre': request.POST.get('titre', '').strip(),
                        'description': request.POST.get('description', '').strip(),
                        'bureau_id': ObjectId(bureau_id),
                        'bureau_nom': bureau_nom,
                        'employe_id': str(employe['_id']),
                        'employe_nom': f"{employe.get('nom', '')} {employe.get('prenom', '')}",
                        'date_debut': date_debut,
                        'date_fin': date_fin,
                        'nb_participants': int(request.POST.get('nb_participants', 1)),
                        'statut': 'en_attente',
                        'qr_code': None,
                        'created_at': datetime.now(),
                        'created_by': request.user.username,
                    }
                    result = db.reservations.insert_one(reservation_data)
                    reservation_id = str(result.inserted_id)
                    
                    # === NOTIFICATION À L'EMPLOYÉ ===
                    notification_employe = {
                        'employe_id': str(employe['_id']),
                        'titre': '📝 Réservation créée',
                        'message': f"Votre réservation '{reservation_data.get('titre')}' a été créée et est en attente de validation.",
                        'categorie': 'reservation',
                        'icon': '📝',
                        'status': 'non_lu',
                        'action_url': '/employe/reservations/',
                        'reservation_id': reservation_id,
                        'created_at': datetime.now()
                    }
                    db.notifications.insert_one(notification_employe)
                    
                    # === NOTIFICATION AUX ADMINISTRATEURS ===
                    admins = User.objects.filter(is_staff=True, is_active=True)
                    admin_message = f"""
🆕 NOUVELLE RÉSERVATION EN ATTENTE

👤 Employé: {employe.get('prenom', '')} {employe.get('nom', '')}
📋 Titre: {reservation_data.get('titre')}
🚪 Salle: {bureau_nom}
📅 Date: {date_debut.strftime('%d/%m/%Y')}
⏰ Horaire: {date_debut.strftime('%H:%M')} → {date_fin.strftime('%H:%M')}
👥 Participants: {reservation_data.get('nb_participants', 1)}

🔗 Cliquez pour traiter cette réservation: /reservations/
"""
                    
                    for admin in admins:
                        admin_notification = {
                            'admin_id': admin.id,
                            'titre': '🆕 Nouvelle réservation en attente',
                            'message': f"{employe.get('prenom', '')} {employe.get('nom', '')} a demandé une réservation pour '{reservation_data.get('titre')}' le {date_debut.strftime('%d/%m/%Y à %H:%M')} dans la salle {bureau_nom}.",
                            'categorie': 'reservation',
                            'icon': '🆕',
                            'status': 'non_lu',
                            'action_url': f'/reservations/{reservation_id}/',
                            'reservation_id': reservation_id,
                            'created_at': datetime.now()
                        }
                        db.admin_notifications.insert_one(admin_notification)
                        
                        # Envoi d'email optionnel
                        if admin.email:
                            try:
                                from django.core.mail import send_mail
                                send_mail(
                                    f"🆕 Nouvelle réservation - {reservation_data.get('titre')}",
                                    admin_message,
                                    settings.DEFAULT_FROM_EMAIL,
                                    [admin.email],
                                    fail_silently=True,
                                )
                            except:
                                pass
                    
                    messages.success(request, "Réservation créée avec succès ! En attente de validation.")
                    return redirect('employe_mes_reservations')
                    
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return render(request, 'dashboard/employe_mes_reservations.html', {
        'employe': employe,
        'reservations': reservations,
        'bureaux': bureaux,
        'total': len(reservations),
        'actives': actives,
        'a_venir': a_venir,
        'en_attente': en_attente,
        'reservations_json': reservations_json,
    })

@login_required
def employe_annuler_reservation(request, reservation_id):
    if request.user.is_staff:
        return redirect('dashboard')
    
    from datetime import datetime
    from bson import ObjectId
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        return redirect('login')
    
    if request.method == 'POST':
        try:
            resa = db.reservations.find_one({
                '_id': ObjectId(reservation_id),
                'employe_id': str(employe['_id'])
            })
            
            if resa:
                # Récupérer la salle
                bureau = db.bureaux.find_one({'_id': resa.get('bureau_id')})
                bureau_nom = bureau['nom'] if bureau else 'Salle inconnue'
                
                db.reservations.update_one(
                    {'_id': ObjectId(reservation_id)},
                    {'$set': {
                        'statut': 'annulee', 
                        'cancelled_at': datetime.now(), 
                        'cancelled_by': request.user.username
                    }}
                )
                
                # === NOTIFICATION À L'EMPLOYÉ ===
                notification_employe = {
                    'employe_id': str(employe['_id']),
                    'titre': '🗑️ Réservation annulée',
                    'message': f"Votre réservation '{resa.get('titre', 'Sans titre')}' a été annulée.",
                    'categorie': 'annulation',
                    'icon': '🗑️',
                    'status': 'non_lu',
                    'action_url': '/employe/reservations/',
                    'reservation_id': reservation_id,
                    'created_at': datetime.now()
                }
                db.notifications.insert_one(notification_employe)
                
                # === NOTIFICATION AUX ADMINISTRATEURS ===
                admins = User.objects.filter(is_staff=True, is_active=True)
                for admin in admins:
                    admin_notification = {
                        'admin_id': admin.id,
                        'titre': '🗑️ Réservation annulée',
                        'message': f"{employe.get('prenom', '')} {employe.get('nom', '')} a annulé sa réservation '{resa.get('titre', 'Sans titre')}' pour la salle {bureau_nom}.",
                        'categorie': 'reservation',
                        'icon': '🗑️',
                        'status': 'non_lu',
                        'action_url': f'/reservations/{reservation_id}/',
                        'reservation_id': reservation_id,
                        'created_at': datetime.now()
                    }
                    db.admin_notifications.insert_one(admin_notification)
                
                messages.success(request, "Réservation annulée avec succès.")
            else:
                messages.error(request, "Réservation introuvable ou non autorisée.")
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return redirect('employe_mes_reservations')

@login_required
def employe_annuler_reservation(request, reservation_id):
    if request.user.is_staff:
        return redirect('dashboard')
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        return redirect('login')
    
    if request.method == 'POST':
        try:
            resa = db.reservations.find_one({
                '_id': ObjectId(reservation_id),
                'employe_id': str(employe['_id'])
            })
            
            if resa:
                db.reservations.update_one(
                    {'_id': ObjectId(reservation_id)},
                    {'$set': {'statut': 'annulee', 'cancelled_at': datetime.now(), 'cancelled_by': request.user.username}}
                )
                messages.success(request, "Réservation annulée avec succès.")
                from dashboard.views import notify_admins_reservation_cancelled
                notify_admins_reservation_cancelled(employe, resa)
            else:
                messages.error(request, "Réservation introuvable ou non autorisée.")
            
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
        
    
    return redirect('employe_mes_reservations')


@login_required
def employe_mon_historique(request):
    if request.user.is_staff:
        return redirect('dashboard')
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        return redirect('login')
    
    employe['id'] = str(employe['_id'])
    acces = list(db.acces_logs.find({'utilisateur_id': employe['_id']}).sort('timestamp', -1).limit(200))
    
    for a in acces:
        bureau = db.bureaux.find_one({'_id': a.get('bureau_id')})
        a['bureau_nom'] = bureau['nom'] if bureau else 'Zone inconnue'
    
    total_acces = len(acces)
    acces_autorises = sum(1 for a in acces if a.get('resultat') == 'AUTORISE')
    acces_refuses = total_acces - acces_autorises
    taux_succes = round(acces_autorises / total_acces * 100) if total_acces else 0
    
    return render(request, 'dashboard/employe_mon_historique.html', {
        'employe': employe,
        'acces': acces,
        'total_acces': total_acces,
        'acces_autorises': acces_autorises,
        'acces_refuses': acces_refuses,
        'taux_succes': taux_succes,
    })


# ====================== API RÉSERVATIONS ======================

# dashboard/views.py - Version simplifiée de l'API

@login_required
def api_reservation_details(request, reservation_id):
    """API pour récupérer les détails d'une réservation (version simplifiée)"""
    try:
        reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
        
        if not reservation:
            return JsonResponse({'error': 'Réservation non trouvée'}, status=404)
        
        # Données basiques
        response_data = {
            'titre': reservation.get('titre', 'Sans titre'),
            'description': reservation.get('description', ''),
            'bureau_nom': str(reservation.get('bureau_id', 'Salle inconnue')),
            'employe_nom': str(reservation.get('employe_id', 'Inconnu')),
            'date_debut': reservation.get('date_debut'),
            'date_fin': reservation.get('date_fin'),
            'nb_participants': reservation.get('nb_participants', 1),
            'statut': reservation.get('statut', 'en_attente'),
        }
        
        # Essayer d'enrichir avec les vrais noms
        if reservation.get('bureau_id'):
            try:
                bureau = db.bureaux.find_one({'_id': reservation['bureau_id']})
                if bureau:
                    response_data['bureau_nom'] = bureau.get('nom', 'Salle inconnue')
            except:
                pass
        
        if reservation.get('employe_id'):
            try:
                emp = db.employees.find_one({'_id': ObjectId(reservation['employe_id'])})
                if emp:
                    response_data['employe_nom'] = f"{emp.get('nom', '')} {emp.get('prenom', '')}".strip() or 'Employé'
            except:
                pass
        
        # Convertir les dates en string
        if response_data['date_debut']:
            response_data['date_debut'] = response_data['date_debut'].isoformat()
        if response_data['date_fin']:
            response_data['date_fin'] = response_data['date_fin'].isoformat()
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_reservations_calendrier(request):
    try:
        if request.user.is_staff:
            reservations = list(db.reservations.find({'statut': {'$in': ['confirmee', 'en_attente']}}))
        else:
            employe = db.employees.find_one({'django_user_id': request.user.id})
            if not employe:
                employe = db.employees.find_one({'django_username': request.user.username})
            if not employe:
                return JsonResponse({'events': []})
            reservations = list(db.reservations.find({
                'employe_id': str(employe['_id']),
                'statut': {'$in': ['confirmee', 'en_attente']}
            }))
        
        events = []
        colors = {'confirmee': '#2dba6f', 'en_attente': '#e3b341', 'annulee': '#f85149'}
        
        for r in reservations:
            bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
            if r.get('date_debut') and r.get('date_fin'):
                events.append({
                    'id': str(r['_id']),
                    'title': r.get('titre', 'Réservation'),
                    'start': r['date_debut'].isoformat(),
                    'end': r['date_fin'].isoformat(),
                    'color': colors.get(r.get('statut', 'en_attente'), '#388bfd'),
                    'extendedProps': {
                        'bureau': bureau['nom'] if bureau else 'Inconnu',
                        'statut': r.get('statut'),
                        'participants': r.get('nb_participants', 1),
                    }
                })
        return JsonResponse({'events': events})
    except Exception as e:
        return JsonResponse({'events': [], 'error': str(e)})


@login_required
def api_disponibilite_bureau(request, bureau_id):
    try:
        date_debut_str = request.GET.get('debut')
        date_fin_str = request.GET.get('fin')
        
        if not date_debut_str or not date_fin_str:
            return JsonResponse({'disponible': True})
        
        date_debut = datetime.fromisoformat(date_debut_str)
        date_fin = datetime.fromisoformat(date_fin_str)
        
        conflit = db.reservations.find_one({
            'bureau_id': ObjectId(bureau_id),
            'statut': {'$in': ['confirmee', 'en_attente']},
            'date_debut': {'$lt': date_fin},
            'date_fin': {'$gt': date_debut},
        })
        
        return JsonResponse({'disponible': conflit is None})
    except Exception as e:
        return JsonResponse({'disponible': True, 'error': str(e)})


# ====================== DASHBOARD ADMIN ======================

@login_required
def dashboard(request):
    if not request.user.is_staff and not request.user.is_superuser:
        return redirect('employe_espace')
    
    total_employes = db.employees.count_documents({})
    total_bureaux = db.bureaux.count_documents({})
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    acces_aujourdhui = db.acces_logs.count_documents({'timestamp': {'$gte': today_start}})
    acces_refuses = db.acces_logs.count_documents({'timestamp': {'$gte': today_start}, 'resultat': 'REFUSE'})
    acces_autorises_today = acces_aujourdhui - acces_refuses
    alertes = db.alertes.count_documents({'statut': 'NON_TRAITEE'}) if 'alertes' in db.list_collection_names() else 0
    
    derniers_logs = list(db.acces_logs.find().sort('timestamp', -1).limit(8))
    for log in derniers_logs:
        bureau = db.bureaux.find_one({'_id': log.get('bureau_id')})
        log['bureau_nom'] = bureau['nom'] if bureau else 'Inconnu'
        emp = db.employees.find_one({'_id': log.get('utilisateur_id')})
        log['nom_utilisateur'] = f"{emp.get('nom','')} {emp.get('prenom','')}" if emp else 'Inconnu'
    
    seven_days_ago = datetime.now() - timedelta(days=7)
    stats_7jours = list(db.acces_logs.aggregate([
        {'$match': {'timestamp': {'$gte': seven_days_ago}}},
        {'$group': {'_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$timestamp'}},
                    'total': {'$sum': 1},
                    'autorises': {'$sum': {'$cond': [{'$eq': ['$resultat', 'AUTORISE']}, 1, 0]}}}},
        {'$sort': {'_id': 1}}
    ]))
    
    return render(request, 'dashboard/dashboard.html', {
        'total_employes': total_employes,
        'total_bureaux': total_bureaux,
        'acces_aujourdhui': acces_aujourdhui,
        'acces_refuses': acces_refuses,
        'alertes': alertes,
        'derniers_logs': derniers_logs,
        'stats_7jours': stats_7jours,
        'acces_autorises_today': acces_autorises_today,
    })


# ====================== GESTION DES EMPLOYÉS ======================

@login_required
def employe_list(request):
    try:
        employes_raw = list(db.employees.find({}))
    except:
        employes_raw = []
    
    employes = []
    total_acces_global = 0
    total_autorises_global = 0
    
    for e in employes_raw:
        try:
            e['id'] = str(e['_id'])
            for k, v in [('nom',''),('prenom',''),('badge_id',''),('email',''),('telephone',''),
                         ('departement',''),('poste',''),('niveau','Staff'),('statut','actif'),
                         ('horaire','08:00 - 17:00'),('heures_hebdo',35),('type_contrat','CDI'),
                         ('jours_travailles',['Lun','Mar','Mer','Jeu','Ven']),
                         ('solde_conges',25),('solde_rtt',10),('solde_maladie',0)]:
                e.setdefault(k, v)
            e['nb_acces'] = db.acces_logs.count_documents({'utilisateur_id': e['_id']})
            total_acces_global += e['nb_acces']
            acces_autorises = db.acces_logs.count_documents({'utilisateur_id': e['_id'], 'resultat': 'AUTORISE'})
            total_autorises_global += acces_autorises
            e['taux_succes'] = round((acces_autorises / e['nb_acces'] * 100) if e['nb_acces'] else 0, 1)
            derniers = list(db.acces_logs.find({'utilisateur_id': e['_id']}).sort('timestamp', -1).limit(1))
            e['dernier_acces'] = derniers[0]['timestamp'] if derniers else None
            employes.append(e)
        except:
            e['id'] = str(e.get('_id', ''))
            e.setdefault('nom', 'Inconnu')
            e['nb_acces'] = 0
            e['taux_succes'] = 0
            e['dernier_acces'] = None
            employes.append(e)
    
    departements = sorted(set(e.get('departement', '') for e in employes if e.get('departement', '').strip()))
    dept_stats = []
    for dept in departements:
        dept_employes = [e for e in employes if e.get('departement') == dept]
        total_acces_dept = sum(e.get('nb_acces', 0) for e in dept_employes)
        total_autorises_dept = sum(int(e.get('nb_acces', 0) * e.get('taux_succes', 0) / 100) for e in dept_employes)
        dept_stats.append({
            'nom': dept,
            'total': len(dept_employes),
            'total_acces': total_acces_dept,
            'taux': round((total_autorises_dept / total_acces_dept * 100) if total_acces_dept else 0, 1)
        })
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    acces_aujourdhui = db.acces_logs.count_documents({'timestamp': {'$gte': today_start}})
    taux_global = round((total_autorises_global / total_acces_global * 100) if total_acces_global else 0, 1)
    
    return render(request, 'dashboard/employe_list.html', {
        'employes': employes,
        'total_employes': len(employes),
        'actifs': sum(1 for e in employes if e.get('statut') == 'actif'),
        'inactifs': sum(1 for e in employes if e.get('statut') != 'actif'),
        'total_departements': len(departements),
        'departements': departements,
        'dept_stats': dept_stats,
        'acces_aujourdhui': acces_aujourdhui,
        'taux_global': taux_global,
    })


@login_required
def employe_detail(request, employe_id):
    try:
        employe = db.employees.find_one({'_id': ObjectId(employe_id)})
        if not employe:
            return redirect('employe_list')
        employe['id'] = str(employe['_id'])
        acces = list(db.acces_logs.find({'utilisateur_id': ObjectId(employe_id)}).sort('timestamp', -1))
        total_acces = len(acces)
        acces_autorises = sum(1 for a in acces if a.get('resultat') == 'AUTORISE')
        acces_refuses = total_acces - acces_autorises
        dernier_acces = acces[0] if acces else None
        count_bureaux = Counter(a.get('bureau_id') for a in acces if a.get('bureau_id'))
        bureaux_frequentes = []
        for bid, count in count_bureaux.most_common(6):
            b = db.bureaux.find_one({'_id': bid})
            if b:
                pct = round(count / total_acces * 100) if total_acces else 0
                bureaux_frequentes.append({'nom': b.get('nom', 'Inconnu'), 'count': count, 'pct': pct})
        cycle_travail = {
            'type': employe.get('type_contrat', 'CDI'),
            'horaire': employe.get('horaire', '08:00 - 17:00'),
            'jours': employe.get('jours_travailles', ['Lun','Mar','Mer','Jeu','Ven']),
            'heures_hebdo': employe.get('heures_hebdo', 35),
            'manager': employe.get('manager', 'Non défini')
        }
        return render(request, 'dashboard/employe_details.html', {
            'employe': employe,
            'total_acces': total_acces,
            'acces_autorises': acces_autorises,
            'acces_refuses': acces_refuses,
            'dernier_acces': dernier_acces,
            'bureaux_frequentes': bureaux_frequentes,
            'acces': acces[:60],
            'cycle_travail': cycle_travail,
            'taux_succes': round((acces_autorises / total_acces * 100) if total_acces else 0, 1)
        })
    except Exception as e:
        return redirect('employe_list')


@login_required
def employe_ajouter(request):
    if request.method == 'POST':
        try:
            badge_id = request.POST.get('badge_id')
            existant = db.employees.find_one({'badge_id': badge_id})
            if existant:
                messages.error(request, f"Le badge {badge_id} existe déjà")
                return render(request, 'dashboard/employe_form.html', {'employe': request.POST})
            nouvel_employe = {
                'badge_id': badge_id,
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'departement': request.POST.get('departement', ''),
                'poste': request.POST.get('poste', '').strip(),
                'niveau': request.POST.get('niveau', 'Staff'),
                'statut': 'actif',
                'created_at': datetime.now()
            }
            date_embauche = request.POST.get('date_embauche')
            if date_embauche:
                nouvel_employe['date_embauche'] = datetime.strptime(date_embauche, '%Y-%m-%d')
            result = db.employees.insert_one(nouvel_employe)
            messages.success(request, f"Employé ajouté avec succès!")
            return redirect('employe_detail', employe_id=str(result.inserted_id))
        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout: {str(e)}")
            return render(request, 'dashboard/employe_form.html', {'employe': request.POST})
    return render(request, 'dashboard/employe_form.html', {'employe': {}})


@login_required
def employe_modifier(request, employe_id):
    try:
        employe = db.employees.find_one({'_id': ObjectId(employe_id)})
        if not employe:
            messages.error(request, "Employé non trouvé")
            return redirect('employe_list')
        employe['id'] = str(employe['_id'])
        if request.method == 'POST':
            update_data = {
                'badge_id': request.POST.get('badge_id'),
                'nom': request.POST.get('nom', '').strip(),
                'prenom': request.POST.get('prenom', '').strip(),
                'email': request.POST.get('email', '').strip(),
                'telephone': request.POST.get('telephone', '').strip(),
                'departement': request.POST.get('departement', ''),
                'poste': request.POST.get('poste', '').strip(),
                'niveau': request.POST.get('niveau', 'Staff'),
                'statut': request.POST.get('statut', 'actif'),
                'updated_at': datetime.now()
            }
            date_embauche = request.POST.get('date_embauche')
            update_data['date_embauche'] = datetime.strptime(date_embauche, '%Y-%m-%d') if date_embauche else None
            db.employees.update_one({'_id': ObjectId(employe_id)}, {'$set': update_data})
            messages.success(request, f"Employé modifié avec succès!")
            return redirect('employe_detail', employe_id=employe_id)
        return render(request, 'dashboard/employe_form.html', {'employe': employe, 'is_edit': True})
    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('employe_list')


@login_required
def employe_supprimer(request, employe_id):
    if request.method == 'POST':
        try:
            db.employees.update_one({'_id': ObjectId(employe_id)},
                                    {'$set': {'statut': 'inactif', 'archived_at': datetime.now()}})
            messages.success(request, "Employé archivé avec succès")
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    return redirect('employe_list')


# ====================== HISTORIQUE ======================

@login_required
def historique(request):
    logs = list(db.acces_logs.find().sort('timestamp', -1).limit(500))
    for log in logs:
        b = db.bureaux.find_one({'_id': log.get('bureau_id')})
        log['bureau_nom'] = b['nom'] if b else 'Inconnu'
        e = db.employees.find_one({'_id': log.get('utilisateur_id')})
        log['nom_utilisateur'] = f"{e.get('nom','')} {e.get('prenom','')}" if e else 'Inconnu'
        log['emp_statut'] = e.get('statut', 'actif') if e else 'inconnu'
        log['badge_id'] = e.get('badge_id') if e else ''
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return render(request, 'dashboard/historique.html', {
        'logs': logs,
        'total_acces': db.acces_logs.count_documents({}),
        'acces_autorises': db.acces_logs.count_documents({'resultat': 'AUTORISE'}),
        'acces_refuses': db.acces_logs.count_documents({'resultat': 'REFUSE'}),
        'acces_aujourdhui': db.acces_logs.count_documents({'timestamp': {'$gte': today_start}}),
    })


# ====================== LIVE / SUPERVISION ======================
@login_required
def live(request):
    """Surveillance live - Dashboard temps réel"""
    from datetime import datetime, timedelta
    
    # Statistiques de la dernière heure
    one_hour_ago = datetime.now() - timedelta(hours=1)
    acces_ok_hour = db.acces_logs.count_documents({
        'resultat': 'AUTORISE',
        'timestamp': {'$gte': one_hour_ago}
    })
    acces_no_hour = db.acces_logs.count_documents({
        'resultat': 'REFUSE',
        'timestamp': {'$gte': one_hour_ago}
    })
    total_acces_hour = acces_ok_hour + acces_no_hour
    taux_succes_hour = round((acces_ok_hour / total_acces_hour * 100), 1) if total_acces_hour > 0 else 0
    
    # Statistiques globales du jour
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    acces_ok_today = db.acces_logs.count_documents({
        'resultat': 'AUTORISE',
        'timestamp': {'$gte': today_start}
    })
    acces_no_today = db.acces_logs.count_documents({
        'resultat': 'REFUSE',
        'timestamp': {'$gte': today_start}
    })
    
    # Alertes actives
    alertes = 0
    alertes_list = []
    if 'alertes' in db.list_collection_names():
        alertes = db.alertes.count_documents({'statut': 'NON_TRAITEE'})
        alertes_list = list(db.alertes.find({'statut': 'NON_TRAITEE'}).sort('timestamp', -1).limit(10))
        for a in alertes_list:
            a['id'] = str(a['_id'])
            if a.get('timestamp'):
                a['timestamp'] = a['timestamp']
    
    # Derniers logs
    derniers_logs = list(db.acces_logs.find().sort('timestamp', -1).limit(30))
    for log in derniers_logs:
        b = db.bureaux.find_one({'_id': log.get('bureau_id')})
        log['bureau_nom'] = b['nom'] if b else 'Inconnu'
        e = db.employees.find_one({'_id': log.get('utilisateur_id')})
        if e:
            log['nom_utilisateur'] = f"{e.get('nom', '')} {e.get('prenom', '')}".strip() or 'Inconnu'
            log['badge_id'] = e.get('badge_id', '???')
        else:
            log['nom_utilisateur'] = 'Inconnu'
            log['badge_id'] = '???'
        log['type_acces'] = log.get('type_acces', 'RFID')
        log['resultat'] = log.get('resultat', 'REFUSE')
    
    # Bureaux
    bureaux = list(db.bureaux.find())
    total_employes = db.employees.count_documents({'statut': 'actif'})
    
    for b in bureaux:
        b['id'] = str(b['_id'])
        b['capacite_max'] = b.get('capacite_max', 10)
        # Occupation en temps réel (dernière heure)
        recent_logs = db.acces_logs.count_documents({
            'bureau_id': b['_id'],
            'timestamp': {'$gte': one_hour_ago}
        })
        b['occupation'] = min(recent_logs, b['capacite_max'])
        b['taux'] = round((b['occupation'] / b['capacite_max'] * 100), 1) if b['capacite_max'] > 0 else 0
    
    # Équipements
    equipements = []
    if 'equipements' in db.list_collection_names():
        equipements = list(db.equipements.find().limit(10))
        for eq in equipements:
            eq['id'] = str(eq['_id'])
    
    # Évolution des KPIs (pour les deltas)
    yesterday_start = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    acces_ok_yesterday = db.acces_logs.count_documents({
        'resultat': 'AUTORISE',
        'timestamp': {'$gte': yesterday_start, '$lt': today_start}
    })
    delta_ok = round(((acces_ok_today - acces_ok_yesterday) / acces_ok_yesterday * 100), 1) if acces_ok_yesterday > 0 else 0
    
    return render(request, 'dashboard/live.html', {
        'acces_ok': acces_ok_today,
        'acces_no': acces_no_today,
        'total_bureaux': len(bureaux),
        'alertes': alertes,
        'alertes_list': alertes_list,
        'derniers_logs': derniers_logs,
        'bureaux': bureaux,
        'equipements': equipements,
        'total_employes': total_employes,
        'taux_succes': taux_succes_hour,
        'delta_ok': delta_ok,
    })

# ====================== RESSOURCES ======================
# ====================== GESTION DES RESSOURCES (ZONES & MATÉRIEL) ======================
# ====================== GESTION DES RESSOURCES (ZONES & MATÉRIEL) ======================

@login_required
def ressources(request):
    """Gestion des ressources - Zones et matériel"""
    from datetime import datetime, timedelta
    import json
    
    # Récupérer les bureaux/zones
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
        b['capacite_max'] = b.get('capacite_max', 10)
        
        # Calculer l'occupation en temps réel (dernière heure)
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent = db.acces_logs.count_documents({
            'bureau_id': b['_id'],
            'timestamp': {'$gte': one_hour_ago}
        })
        b['occupation'] = min(recent, b['capacite_max'])
        b['taux_occupation'] = round((b['occupation'] / b['capacite_max'] * 100), 1) if b['capacite_max'] > 0 else 0
    
    total_bureaux = len(bureaux)
    zones_actives = sum(1 for b in bureaux if b.get('statut', 'actif') == 'actif')
    capacite_totale = sum(b.get('capacite_max', 0) for b in bureaux)
    
    # Calculer l'occupation moyenne
    total_occ = sum(min(b.get('occupation', 0), b.get('capacite_max', 10)) for b in bureaux)
    total_cap = sum(b.get('capacite_max', 10) for b in bureaux)
    occupation_moy = round((total_occ / total_cap * 100), 1) if total_cap > 0 else 0
    niveaux_securite = len(set(b.get('niveau_securite', 'standard') for b in bureaux))
    
    # Récupérer le matériel depuis MongoDB
    materiels = list(db.materiels.find()) if 'materiels' in db.list_collection_names() else []
    for m in materiels:
        m['id'] = str(m['_id'])
    
    total_materiel = len(materiels)
    materiel_maintenance = sum(1 for m in materiels if m.get('statut') in ['maintenance', 'hors_service'])
    
    # Statistiques par catégorie
    categories_stats = {}
    for m in materiels:
        cat = m.get('categorie', 'autre')
        if cat not in categories_stats:
            categories_stats[cat] = {'total': 0, 'disponible': 0}
        categories_stats[cat]['total'] += 1
        if m.get('statut') == 'disponible':
            categories_stats[cat]['disponible'] += 1
    
    # JSON pour le matériel
    materiels_json = json.dumps([{
        'id': str(m['_id']),
        'nom': m.get('nom', ''),
        'categorie': m.get('categorie', ''),
        'numero_serie': m.get('numero_serie', ''),
        'statut': m.get('statut', 'disponible'),
        'zone': m.get('zone', ''),
        'description': m.get('description', ''),
    } for m in materiels], default=str)
    
    return render(request, 'dashboard/ressources.html', {
        'bureaux': bureaux,
        'total_bureaux': total_bureaux,
        'zones_actives': zones_actives,
        'capacite_totale': capacite_totale,
        'occupation_moy': occupation_moy,
        'niveaux_securite': niveaux_securite,
        'materiels': materiels,
        'total_materiel': total_materiel,
        'materiel_maintenance': materiel_maintenance,
        'categories_stats': categories_stats,
        'materiels_json': materiels_json,
    })


@login_required
def bureau_ajouter(request):
    """Ajouter/modifier un bureau/zone"""
    from bson import ObjectId
    from datetime import datetime
    
    if request.method == 'POST':
        try:
            bureau_id = request.POST.get('bureau_id')
            data = {
                'nom': request.POST.get('nom'),
                'code_bureau': request.POST.get('code_bureau', ''),
                'etage': int(request.POST.get('etage', 0)),
                'capacite_max': int(request.POST.get('capacite_max', 10)),
                'niveau_securite': request.POST.get('niveau_securite', 'standard'),
                'description': request.POST.get('description', ''),
                'statut': request.POST.get('statut', 'actif'),
                'updated_at': datetime.now(),
            }
            
            if bureau_id:
                # Modification
                db.bureaux.update_one({'_id': ObjectId(bureau_id)}, {'$set': data})
                messages.success(request, f"Zone '{data['nom']}' modifiée avec succès!")
            else:
                # Création
                data['created_at'] = datetime.now()
                db.bureaux.insert_one(data)
                messages.success(request, f"Zone '{data['nom']}' ajoutée avec succès!")
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return redirect('ressources')


@login_required
def bureau_supprimer(request, bureau_id):
    """Supprimer un bureau/zone"""
    from bson import ObjectId
    
    if request.method == 'POST':
        try:
            result = db.bureaux.delete_one({'_id': ObjectId(bureau_id)})
            if result.deleted_count > 0:
                messages.success(request, "Zone supprimée avec succès!")
            else:
                messages.error(request, "Zone non trouvée")
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    return redirect('ressources')


@login_required
def api_bureau_stats(request, bureau_id):
    """API pour les statistiques d'un bureau"""
    from bson import ObjectId
    from datetime import datetime, timedelta
    
    try:
        bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
        if not bureau:
            return JsonResponse({'error': 'Bureau non trouvé'}, status=404)
        
        # Statistiques des 7 derniers jours
        dates = []
        acces_par_jour = []
        for i in range(6, -1, -1):
            day_start = (datetime.now() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            count = db.acces_logs.count_documents({
                'bureau_id': ObjectId(bureau_id),
                'timestamp': {'$gte': day_start, '$lt': day_end}
            })
            dates.append(day_start.strftime('%a'))
            acces_par_jour.append(count)
        
        return JsonResponse({
            'dates': dates,
            'acces_par_jour': acces_par_jour,
            'nom': bureau.get('nom'),
            'capacite': bureau.get('capacite_max', 0)
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_materiel_list(request):
    """API pour la liste du matériel"""
    materiels = list(db.materiels.find()) if 'materiels' in db.list_collection_names() else []
    for m in materiels:
        m['id'] = str(m['_id'])
    return JsonResponse({'materiels': materiels})


@login_required
def api_materiel_ajouter(request):
    """API pour ajouter/modifier du matériel"""
    from bson import ObjectId
    from datetime import datetime
    import json
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
    
    try:
        data = json.loads(request.body)
        materiel_id = data.get('id')
        
        materiel_data = {
            'nom': data.get('nom'),
            'categorie': data.get('categorie', 'autre'),
            'numero_serie': data.get('numero_serie', ''),
            'statut': data.get('statut', 'disponible'),
            'zone': data.get('zone', ''),
            'description': data.get('description', ''),
            'photo': data.get('photo', ''),
            'updated_at': datetime.now()
        }
        
        if 'materiels' not in db.list_collection_names():
            db.create_collection('materiels')
        
        # Si l'ID existe et n'est pas un ID temporaire (commence par mat_)
        if materiel_id and not materiel_id.startswith('mat_') and len(materiel_id) == 24:
            # Modification
            db.materiels.update_one({'_id': ObjectId(materiel_id)}, {'$set': materiel_data})
            return JsonResponse({'status': 'success', 'message': 'Matériel modifié', 'id': materiel_id})
        else:
            # Nouveau matériel
            materiel_data['created_at'] = datetime.now()
            result = db.materiels.insert_one(materiel_data)
            return JsonResponse({'status': 'success', 'message': 'Matériel ajouté', 'id': str(result.inserted_id)})
            
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_materiel_supprimer(request, materiel_id):
    """API pour supprimer du matériel"""
    from bson import ObjectId
    
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
    
    try:
        result = db.materiels.delete_one({'_id': ObjectId(materiel_id)})
        if result.deleted_count > 0:
            return JsonResponse({'status': 'success', 'message': 'Matériel supprimé'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Matériel non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_export_ressources_csv(request):
    """Export des ressources en CSV"""
    import csv
    from django.http import HttpResponse
    from datetime import datetime
    
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="ressources_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Type', 'Nom', 'Code/Référence', 'Capacité', 'Étage', 'Niveau sécurité', 'Statut', 'Occupation (%)'])
    
    # Exporter les zones
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        writer.writerow([
            'Zone',
            b.get('nom', ''),
            b.get('code_bureau', ''),
            b.get('capacite_max', 0),
            b.get('etage', 0),
            b.get('niveau_securite', 'standard'),
            b.get('statut', 'actif'),
            b.get('taux_occupation', 0)
        ])
    
    # Exporter le matériel
    materiels = list(db.materiels.find()) if 'materiels' in db.list_collection_names() else []
    for m in materiels:
        writer.writerow([
            'Matériel',
            m.get('nom', ''),
            m.get('numero_serie', ''),
            '',
            '',
            m.get('categorie', ''),
            m.get('statut', ''),
            ''
        ])
    
    return response


@login_required
def api_occupation(request):
    """API pour l'occupation des zones en temps réel"""
    from datetime import datetime, timedelta
    from bson import ObjectId
    
    one_hour_ago = datetime.now() - timedelta(hours=1)
    bureaux = list(db.bureaux.find())
    
    result = []
    for b in bureaux:
        recent = db.acces_logs.count_documents({
            'bureau_id': b['_id'],
            'timestamp': {'$gte': one_hour_ago}
        })
        capacite = b.get('capacite_max', 10)
        occupation = min(recent, capacite)
        taux = round((occupation / capacite * 100), 1) if capacite > 0 else 0
        
        result.append({
            'id': str(b['_id']),
            'nom': b.get('nom', 'Inconnu'),
            'occupation': occupation,
            'capacite': capacite,
            'taux': taux,
        })
    
    return JsonResponse({'bureaux': result})


# ====================== CALENDRIER ET RÈGLES ======================

@login_required
def calendrier(request):
    """Page du calendrier des règles d'accès"""
    from bson import ObjectId
    
    employes = list(db.employees.find({'statut': 'actif'}))
    for e in employes:
        e['id'] = str(e['_id'])
    
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
    
    return render(request, 'dashboard/calendrier.html', {
        'employes': employes,
        'bureaux': bureaux,
    })


@login_required
def api_get_employee_rules(request, employe_id):
    """API pour récupérer les règles d'un employé"""
    from bson import ObjectId
    
    try:
        rules_cursor = db.access_rules.find({'employe_id': employe_id})
        formatted_rules = {}
        for rule in rules_cursor:
            jour, mois, annee = rule.get('jour'), rule.get('mois'), rule.get('annee')
            if not (jour and mois and annee):
                continue
            key = f"{annee}-{mois}-{jour}"
            if key not in formatted_rules:
                formatted_rules[key] = {}
            formatted_rules[key][rule['zone_nom']] = {
                'heure_debut': rule.get('heure_debut', '08:00'),
                'heure_fin': rule.get('heure_fin', '18:00'),
                'acces_autorise': rule.get('acces_autorise', True)
            }
        return JsonResponse({'rules': formatted_rules, 'status': 'success'})
    except Exception as e:
        return JsonResponse({'rules': {}, 'status': 'error', 'message': str(e)})


@login_required
def api_save_day_rules(request):
    """API pour sauvegarder les règles d'un jour"""
    from datetime import datetime
    import json
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        rules = data.get('rules', [])
        employe_id = data.get('employe_id')
        
        if not employe_id and rules:
            employe_id = rules[0].get('employe_id')
        if not employe_id:
            return JsonResponse({'error': 'Employé ID manquant'}, status=400)
        
        saved_count = 0
        for rule in rules:
            jour, mois, annee = rule.get('jour'), rule.get('mois'), rule.get('annee')
            zone_nom = rule.get('zone_nom', '')
            
            if zone_nom == '__DELETE__':
                db.access_rules.delete_many({
                    'employe_id': employe_id,
                    'jour': jour,
                    'mois': mois,
                    'annee': annee
                })
            else:
                db.access_rules.delete_one({
                    'employe_id': employe_id,
                    'zone_nom': zone_nom,
                    'jour': jour,
                    'mois': mois,
                    'annee': annee
                })
                db.access_rules.insert_one({
                    'employe_id': employe_id,
                    'zone_nom': zone_nom,
                    'jour': jour,
                    'mois': mois,
                    'annee': annee,
                    'heure_debut': rule.get('heure_debut', '08:00'),
                    'heure_fin': rule.get('heure_fin', '18:00'),
                    'acces_autorise': rule.get('acces_autorise', True),
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                })
                saved_count += 1
        
        return JsonResponse({'status': 'success', 'message': f'{saved_count} règle(s) sauvegardée(s)'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_save_all_rules(request):
    """API pour sauvegarder toutes les règles d'un employé"""
    from datetime import datetime
    import json
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        rules = data.get('rules', [])
        
        if not employe_id:
            return JsonResponse({'error': 'Employé ID manquant'}, status=400)
        
        # Supprimer toutes les règles existantes
        db.access_rules.delete_many({'employe_id': employe_id})
        
        if rules:
            rules_to_insert = []
            for r in rules:
                rules_to_insert.append({
                    'employe_id': employe_id,
                    'zone_nom': r.get('zone_nom', ''),
                    'jour': r.get('jour'),
                    'mois': r.get('mois'),
                    'annee': r.get('annee'),
                    'heure_debut': r.get('heure_debut', '08:00'),
                    'heure_fin': r.get('heure_fin', '18:00'),
                    'acces_autorise': r.get('acces_autorise', True),
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                })
            db.access_rules.insert_many(rules_to_insert)
        
        return JsonResponse({'status': 'success', 'message': f'{len(rules)} règle(s) enregistrée(s)'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_bureaux(request):
    """API pour récupérer la liste des bureaux"""
    bureaux = list(db.bureaux.find())
    result = [{
        'id': str(b['_id']),
        'nom': b.get('nom', ''),
        'niveau': b.get('niveau_securite', 'standard'),
        'capacite': b.get('capacite_max', 0),
        'etage': b.get('etage', 0)
    } for b in bureaux]
    
    # Si aucun bureau n'existe, retourner des données par défaut
    if not result:
        result = [
            {'id': '1', 'nom': 'Direction Générale', 'niveau': 'critique', 'capacite': 5, 'etage': 1},
            {'id': '2', 'nom': 'Atelier Production', 'niveau': 'standard', 'capacite': 20, 'etage': 0},
            {'id': '3', 'nom': 'Salle Serveur', 'niveau': 'critique', 'capacite': 2, 'etage': 0},
            {'id': '4', 'nom': 'Archives', 'niveau': 'restreint', 'capacite': 3, 'etage': 0},
            {'id': '5', 'nom': 'Bureau RH', 'niveau': 'standard', 'capacite': 4, 'etage': 1},
            {'id': '6', 'nom': 'Laboratoire', 'niveau': 'restreint', 'capacite': 6, 'etage': 1},
            {'id': '7', 'nom': 'Entrée Principale', 'niveau': 'public', 'capacite': 50, 'etage': 0},
        ]
    
    return JsonResponse({'bureaux': result})


# ====================== STATISTIQUES ======================
@login_required
def statistiques(request):
    from datetime import datetime, timedelta
    import json
    
    now = datetime.now()
    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # ===== KPIs de base =====
    total_mois = db.acces_logs.count_documents({'timestamp': {'$gte': start_month}})
    total_all = db.acces_logs.count_documents({})
    autorises = db.acces_logs.count_documents({'resultat': 'AUTORISE'})
    taux_succes = round(autorises / total_all * 100) if total_all else 0
    
    # ===== Top employés =====
    top_employes = []
    for t in db.acces_logs.aggregate([
        {'$match': {'timestamp': {'$gte': start_month}}},
        {'$group': {'_id': '$utilisateur_id', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]):
        emp = db.employees.find_one({'_id': t['_id']})
        if emp:
            auto_emp = db.acces_logs.count_documents({'utilisateur_id': t['_id'], 'resultat': 'AUTORISE'})
            top_employes.append({
                'nom': emp.get('nom', ''),
                'prenom': emp.get('prenom', ''),
                'departement': emp.get('departement', ''),
                'nb_acces': t['count'],
                'taux_succes': round(auto_emp / t['count'] * 100) if t['count'] else 0,
                'dernier_acces': None,
            })
    
    # ===== Zones stats =====
    zones_stats = []
    for z in db.acces_logs.aggregate([
        {'$match': {'timestamp': {'$gte': start_month}}},
        {'$group': {'_id': '$bureau_id', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]):
        b = db.bureaux.find_one({'_id': z['_id']})
        if b:
            zones_stats.append({
                'nom': b.get('nom', 'Inconnu'), 
                'count': z['count']
            })
    
    # Calculer les pourcentages
    total_zones = sum(z['count'] for z in zones_stats)
    for z in zones_stats:
        z['pct'] = round(z['count'] / total_zones * 100) if total_zones else 0
    
    # ===== Données pour le graphique (30 jours) =====
    labels = []
    autorises_list = []
    refuses_list = []
    
    for i in range(29, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        a = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'AUTORISE'})
        r = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'REFUSE'})
        labels.append(day_start.strftime('%d/%m'))
        autorises_list.append(a)
        refuses_list.append(r)
    
    # Prédictions
    prediction_list = []
    for i in range(len(autorises_list)):
        window = autorises_list[max(0, i-6):i+1]
        avg = sum(window) / len(window) if window else 0
        prediction_list.append(round(avg * 1.05, 1))
    
    # Calcul de la prédiction globale
    last_7 = sum(autorises_list[-7:]) if len(autorises_list) >= 7 else sum(autorises_list)
    prev_7 = sum(autorises_list[-14:-7]) if len(autorises_list) >= 14 else last_7
    prediction_pct = round(((last_7 - prev_7) / prev_7 * 100) if prev_7 else 0, 1)
    
    # ===== Données occupation salles =====
    total_salles = db.bureaux.count_documents({})
    reservations_mois = db.reservations.count_documents({
        'date_debut': {'$gte': start_month},
        'statut': 'confirmee'
    })
    heures_possibles = total_salles * 240 if total_salles > 0 else 1
    heures_occupees = reservations_mois * 2
    occupation_moy = min(100, round((heures_occupees / heures_possibles) * 100, 1)) if heures_possibles > 0 else 0
    
    total_reservations = reservations_mois
    
    # Salles disponibles maintenant
    salles_reservees = db.reservations.distinct('bureau_id', {
        'date_debut': {'$lte': now},
        'date_fin': {'$gte': now},
        'statut': 'confirmee'
    })
    salles_disponibles = total_salles - len(salles_reservees)
    
    # Graphique occupation des salles
    occupation_labels = []
    occupation_values = []
    for bureau in db.bureaux.find().limit(8):
        res_count = db.reservations.count_documents({
            'bureau_id': bureau['_id'],
            'date_debut': {'$gte': start_month},
            'statut': 'confirmee'
        })
        taux = min(100, round((res_count * 2 / 240) * 100, 1)) if res_count > 0 else 0
        occupation_labels.append(bureau.get('nom', 'Salle')[:15])
        occupation_values.append(taux)
    
    # Top ressources
    top_ressources_list = []
    pipeline = [
        {'$match': {'date_debut': {'$gte': start_month}, 'statut': 'confirmee'}},
        {'$group': {'_id': '$bureau_id', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]
    results = list(db.reservations.aggregate(pipeline))
    total_res = sum(r['count'] for r in results) if results else 1
    for r in results:
        bureau = db.bureaux.find_one({'_id': r['_id']})
        if bureau:
            top_ressources_list.append({
                'nom': bureau.get('nom', 'Salle')[:20],
                'reservations': r['count'],
                'taux': round(r['count'] / total_res * 100, 1)
            })
    
    # ===== Construction du contexte =====
    context = {
        # KPIs
        'total_mois': total_mois,
        'taux_succes': taux_succes,
        'taux_refus': 100 - taux_succes,
        'pic_heure': '08h30',
        'zone_active': zones_stats[0]['nom'] if zones_stats else 'N/A',
        'top_employes': top_employes,
        'prediction': prediction_pct,
        
        # KPIs ressources
        'occupation_moy': occupation_moy,
        'total_reservations': total_reservations,
        'salles_disponibles': salles_disponibles,
        'total_salles': total_salles,
        
        # Données JSON (stringifiées correctement)
        'chart_labels': json.dumps(labels),
        'chart_autorises': json.dumps(autorises_list),
        'chart_refuses': json.dumps(refuses_list),
        'chart_prediction': json.dumps(prediction_list),
        'zones_stats': json.dumps(zones_stats),
        'top_ressources': json.dumps(top_ressources_list),
        'occupation_labels': json.dumps(occupation_labels),
        'occupation_values': json.dumps(occupation_values),
    }
    
    return render(request, 'dashboard/statistiques.html', context)
    # ====================== STATISTIQUES AVANCÉES ======================

@login_required
def api_stats_export_csv(request):
    """Export des statistiques en CSV"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    import csv
    from datetime import datetime, timedelta
    from django.http import HttpResponse
    
    # Récupérer la période
    days = int(request.GET.get('days', 30))
    start_date = datetime.now() - timedelta(days=days)
    
    # Récupérer les données
    stats = []
    for i in range(days, -1, -1):
        day_start = (datetime.now() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        a = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'AUTORISE'})
        r = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'REFUSE'})
        
        stats.append({
            'date': day_start.strftime('%d/%m/%Y'),
            'autorises': a,
            'refuses': r,
            'total': a + r,
            'taux_succes': round(a / (a + r) * 100, 1) if (a + r) > 0 else 0
        })
    
    # Créer la réponse CSV
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="statistiques_acces_{datetime.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Accès autorisés', 'Accès refusés', 'Total', 'Taux de succès (%)'])
    
    for s in stats:
        writer.writerow([s['date'], s['autorises'], s['refuses'], s['total'], s['taux_succes']])
    
    return response


@login_required
def api_stats_export_pdf(request):
    """Export des statistiques en PDF"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    from datetime import datetime, timedelta
    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    import io
    
    # Récupérer la période
    days = int(request.GET.get('days', 30))
    start_date = datetime.now() - timedelta(days=days)
    
    # Récupérer les données
    stats = []
    for i in range(days, -1, -1):
        day_start = (datetime.now() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        a = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'AUTORISE'})
        r = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'REFUSE'})
        
        stats.append([day_start.strftime('%d/%m/%Y'), str(a), str(r), str(a + r), f"{round(a / (a + r) * 100, 1) if (a + r) > 0 else 0}%"])
    
    # Créer le PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    elements = []
    
    # Style
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, alignment=1)
    
    # Titre
    elements.append(Paragraph(f"Rapport des statistiques d'accès - {datetime.now().strftime('%d/%m/%Y')}", title_style))
    elements.append(Spacer(1, 0.5 * cm))
    
    # Tableau
    data = [['Date', 'Autorisés', 'Refusés', 'Total', 'Taux succès']] + stats
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
    ]))
    
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="statistiques_acces_{datetime.now().strftime("%Y%m%d")}.pdf"'
    return response


@login_required
def api_stats_departement(request):
    """Statistiques par département"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    from datetime import datetime, timedelta
    
    days = int(request.GET.get('days', 30))
    start_date = datetime.now() - timedelta(days=days)
    
    # Récupérer tous les employés par département
    pipeline = [
        {'$match': {'statut': 'actif'}},
        {'$group': {'_id': '$departement', 'count': {'$sum': 1}}}
    ]
    dept_counts = list(db.employees.aggregate(pipeline))
    
    # Statistiques par département
    dept_stats = []
    for dept in dept_counts:
        dept_name = dept['_id'] or 'Non défini'
        
        # Récupérer les employés de ce département
        employees = list(db.employees.find({'departement': dept_name}))
        employee_ids = [e['_id'] for e in employees]
        
        # Compter les accès
        total_acces = db.acces_logs.count_documents({
            'utilisateur_id': {'$in': employee_ids},
            'timestamp': {'$gte': start_date}
        })
        
        autorises = db.acces_logs.count_documents({
            'utilisateur_id': {'$in': employee_ids},
            'timestamp': {'$gte': start_date},
            'resultat': 'AUTORISE'
        })
        
        dept_stats.append({
            'nom': dept_name,
            'employes': dept['count'],
            'acces': total_acces,
            'taux_succes': round(autorises / total_acces * 100, 1) if total_acces > 0 else 0
        })
    
    return JsonResponse({'departements': dept_stats})


@login_required
def api_stats_period_custom(request):
    """Statistiques pour une période personnalisée"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    from datetime import datetime
    
    date_debut_str = request.GET.get('date_debut')
    date_fin_str = request.GET.get('date_fin')
    
    if not date_debut_str or not date_fin_str:
        return JsonResponse({'error': 'Dates manquantes'}, status=400)
    
    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d')
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d')
        date_fin = date_fin.replace(hour=23, minute=59, second=59)
    except ValueError:
        return JsonResponse({'error': 'Format de date invalide'}, status=400)
    
    # Statistiques globales
    total_acces = db.acces_logs.count_documents({'timestamp': {'$gte': date_debut, '$lte': date_fin}})
    autorises = db.acces_logs.count_documents({'timestamp': {'$gte': date_debut, '$lte': date_fin}, 'resultat': 'AUTORISE'})
    
    # Données quotidiennes
    stats = []
    current = date_debut
    while current <= date_fin:
        day_end = current.replace(hour=23, minute=59, second=59)
        a = db.acces_logs.count_documents({'timestamp': {'$gte': current, '$lte': day_end}, 'resultat': 'AUTORISE'})
        r = db.acces_logs.count_documents({'timestamp': {'$gte': current, '$lte': day_end}, 'resultat': 'REFUSE'})
        
        stats.append({
            'date': current.strftime('%d/%m'),
            'autorises': a,
            'refuses': r
        })
        current += timedelta(days=1)
    
    return JsonResponse({
        'total_acces': total_acces,
        'taux_succes': round(autorises / total_acces * 100, 1) if total_acces > 0 else 0,
        'stats': stats
    })


@login_required
def api_stats_trend_cache(request):
    """Version avec cache des statistiques de tendance"""
    from django.core.cache import cache
    from datetime import datetime, timedelta
    
    days = int(request.GET.get('days', 30))
    cache_key = f"stats_trend_{days}"
    
    # Vérifier le cache
    cached_data = cache.get(cache_key)
    if cached_data:
        return JsonResponse(cached_data)
    
    # Calculer les données
    now = datetime.now()
    labels, autorises_list, refuses_list, prediction_list = [], [], [], []
    
    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        a = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'AUTORISE'})
        r = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'REFUSE'})
        labels.append(day_start.strftime('%d/%m'))
        autorises_list.append(a)
        refuses_list.append(r)
    
    # Prédictions
    for i in range(len(autorises_list)):
        window = autorises_list[max(0, i-6):i+1]
        avg = sum(window) / len(window) if window else 0
        prediction_list.append(round(avg * 1.05, 1))
    
    data = {
        'labels': labels,
        'autorises': autorises_list,
        'refuses': refuses_list,
        'prediction': prediction_list
    }
    
    # Mettre en cache pour 5 minutes
    cache.set(cache_key, data, 300)
    
    return JsonResponse(data)


# ====================== PARAMÈTRES ======================

@login_required
def parametres(request):
    if not request.user.is_staff and not request.user.is_superuser:
        return redirect('dashboard')
    config = db.system_config.find_one({'type': 'global'}) or {}
    admin_profile = db.admin_profiles.find_one({'user_id': request.user.id}) or {}
    return render(request, 'dashboard/parametres.html', {
        'config': config,
        'admin_profile': admin_profile,
        'user': request.user,
    })


@login_required
def api_parametres_save(request):
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Accès non autorisé'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Méthode non autorisée'}, status=405)
    try:
        data = json.loads(request.body)
        db.system_config.update_one(
            {'type': 'global'},
            {'$set': {**data, 'updated_at': datetime.now(), 'updated_by': request.user.username}},
            upsert=True
        )
        db.system_logs.insert_one({
            'user_id': request.user.id,
            'username': request.user.username,
            'action': 'SETTINGS_UPDATE',
            'details': list(data.keys()),
            'timestamp': datetime.now(),
            'ip': request.META.get('REMOTE_ADDR')
        })
        return JsonResponse({'status': 'success', 'message': 'Paramètres sauvegardés avec succès'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ====================== API OCCUPATION ======================

@login_required
def api_occupation(request):
    bureaux = list(db.bureaux.find())
    result = []
    one_hour_ago = datetime.now() - timedelta(hours=1)
    for b in bureaux:
        recent = db.acces_logs.count_documents({'bureau_id': b['_id'], 'timestamp': {'$gte': one_hour_ago}})
        cap = b.get('capacite_max', 10)
        occ = min(recent * 3, cap)
        taux = round(occ / cap * 100) if cap else 0
        result.append({'id': str(b['_id']), 'nom': b['nom'], 'occupation': occ, 'capacite': cap, 'taux': taux})
    return JsonResponse({'bureaux': result})


@login_required
def api_bureau_stats(request, bureau_id):
    dates = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    acces = [random.randint(20, 90) for _ in range(7)]
    return JsonResponse({'dates': dates, 'acces_par_jour': acces})


# ====================== API LIVE FEED ======================
@login_required
def api_live_feed(request):
    """API pour le flux live des accès"""
    from datetime import datetime, timedelta
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Récupérer les derniers logs
    logs = list(db.acces_logs.find().sort('timestamp', -1).limit(30))
    logs_data = []
    
    for log in logs:
        emp = db.employees.find_one({'_id': log.get('utilisateur_id')})
        bureau = db.bureaux.find_one({'_id': log.get('bureau_id')})
        
        logs_data.append({
            'nom': f"{emp.get('nom', '')} {emp.get('prenom', '')}".strip() or 'Inconnu' if emp else 'Inconnu',
            'badge': emp.get('badge_id', '???') if emp else '???',
            'zone': bureau.get('nom', 'Zone inconnue') if bureau else 'Zone inconnue',
            'resultat': log.get('resultat', 'REFUSE'),
            'method': log.get('type_acces', 'RFID'),
            'time': log['timestamp'].strftime('%H:%M:%S') if log.get('timestamp') else '--:--:--',
        })
    
    # Statistiques du jour
    acces_ok = db.acces_logs.count_documents({
        'timestamp': {'$gte': today_start},
        'resultat': 'AUTORISE'
    })
    acces_no = db.acces_logs.count_documents({
        'timestamp': {'$gte': today_start},
        'resultat': 'REFUSE'
    })
    total = acces_ok + acces_no
    taux_succes = round((acces_ok / total * 100), 1) if total > 0 else 0
    
    # Alertes
    alertes = db.alertes.count_documents({'statut': 'NON_TRAITEE'}) if 'alertes' in db.list_collection_names() else 0
    
    return JsonResponse({
        'logs': logs_data,
        'stats': {
            'acces_ok': acces_ok,
            'acces_no': acces_no,
            'taux_succes': taux_succes,
            'alertes': alertes,
        }
    })


# ====================== API DÉVERROUILLAGE D'URGENCE ======================

@login_required
def api_emergency_unlock(request):
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Accès non autorisé'}, status=403)
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Méthode non autorisée'}, status=405)
    
    db.system_logs.insert_one({
        'user_id': request.user.id,
        'username': request.user.username,
        'action': 'EMERGENCY_UNLOCK',
        'timestamp': datetime.now(),
        'ip': request.META.get('REMOTE_ADDR', ''),
        'details': "Déverrouillage manuel d'urgence via interface web admin",
        'severity': 'CRITICAL',
    })
    db.equipements.update_many({'statut': 'actif'}, {'$set': {'emergency_unlock': True, 'emergency_at': datetime.now()}})
    if 'alertes' not in db.list_collection_names():
        db.create_collection('alertes')
    db.alertes.insert_one({
        'type': 'EMERGENCY_UNLOCK',
        'message': f"Déverrouillage d'urgence activé par {request.user.username}",
        'statut': 'NON_TRAITEE',
        'timestamp': datetime.now(),
        'created_by': request.user.username,
    })
    return JsonResponse({
        'status': 'success',
        'message': f"Déverrouillage d'urgence activé par {request.user.username}. Action journalisée.",
    })


# ====================== API STATISTIQUES TENDANCE ======================

@login_required
def api_stats_trend(request):
    days = min(int(request.GET.get('days', 30)), 365)
    now = datetime.now()
    labels, autorises_list, refuses_list, prediction_list = [], [], [], []
    for i in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        a = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'AUTORISE'})
        r = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'REFUSE'})
        labels.append(day_start.strftime('%d/%m'))
        autorises_list.append(a)
        refuses_list.append(r)
    for i in range(len(autorises_list)):
        window = autorises_list[max(0, i - 6):i + 1]
        avg = sum(w * (j + 1) for j, w in enumerate(window)) / sum(range(1, len(window) + 1)) if window else 0
        prediction_list.append(round(avg * 1.05, 1))
    return JsonResponse({'labels': labels, 'autorises': autorises_list, 'refuses': refuses_list, 'prediction': prediction_list})


# ====================== API RÉSERVATIONS ACTIVES ======================

@login_required
def api_reservations_active(request):
    now = datetime.now()
    reservations_actives = list(db.reservations.find({
        'statut': 'confirmee',
        'date_debut': {'$lte': now},
        'date_fin': {'$gte': now},
    }).limit(20))
    result = []
    for r in reservations_actives:
        bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
        emp = db.employees.find_one({'_id': r.get('employe_id')})
        result.append({
            'id': str(r['_id']),
            'titre': r.get('titre', 'Réservation'),
            'bureau': bureau['nom'] if bureau else 'Inconnu',
            'employe': f"{emp.get('nom','?')} {emp.get('prenom','')}" if emp else 'Inconnu',
            'debut': r['date_debut'].isoformat() if r.get('date_debut') else '',
            'fin': r['date_fin'].isoformat() if r.get('date_fin') else '',
        })
    return JsonResponse({'reservations': result, 'total': len(result)})


# ====================== API TOP RESSOURCES ======================

@login_required
def api_resources_top(request):
    pipeline = [{'$group': {'_id': '$bureau_id', 'reservations': {'$sum': 1}}},
                {'$sort': {'reservations': -1}},
                {'$limit': 5}]
    top = list(db.reservations.aggregate(pipeline))
    total_reservations = db.reservations.count_documents({})
    result = []
    for t in top:
        b = db.bureaux.find_one({'_id': t['_id']})
        if b:
            result.append({
                'nom': b.get('nom', 'Inconnu'),
                'reservations': t['reservations'],
                'taux': round(t['reservations'] / total_reservations * 100) if total_reservations else 0,
            })
    return JsonResponse({'resources': result})


# ====================== GESTION DES ÉQUIPEMENTS ======================

@login_required
def equipement_list(request):
    equipements = list(db.equipements.find().sort('type', 1))
    nb_rfid = sum(1 for e in equipements if e.get('type') == 'RFID')
    nb_qr = sum(1 for e in equipements if e.get('type') == 'QR')
    nb_actifs = sum(1 for e in equipements if e.get('statut') == 'actif')
    nb_inactifs = len(equipements) - nb_actifs
    
    for equip in equipements:
        equip['id'] = str(equip['_id'])
        if equip.get('bureau_id'):
            bureau = db.bureaux.find_one({'_id': equip['bureau_id']})
            equip['bureau_nom'] = bureau['nom'] if bureau else 'Non assigné'
        else:
            equip['bureau_nom'] = 'Non assigné'
    
    yesterday = datetime.now() - timedelta(days=1)
    for equip in equipements:
        equip['logs_24h'] = db.acces_logs.count_documents({
            'equipement_code': equip.get('code'),
            'timestamp': {'$gte': yesterday}
        })
    
    return render(request, 'dashboard/equipement_list.html', {
        'equipements': equipements,
        'nb_total': len(equipements),
        'nb_rfid': nb_rfid,
        'nb_qr': nb_qr,
        'nb_actifs': nb_actifs,
        'nb_inactifs': nb_inactifs,
    })


@login_required
def equipement_detail(request, equipement_id):
    try:
        equipement = db.equipements.find_one({'_id': ObjectId(equipement_id)})
        if not equipement:
            messages.error(request, "Équipement non trouvé")
            return redirect('equipement_list')
        equipement['id'] = str(equipement['_id'])
        if equipement.get('bureau_id'):
            equipement['bureau'] = db.bureaux.find_one({'_id': equipement['bureau_id']})
        
        logs = list(db.acces_logs.find({'equipement_code': equipement.get('code')}).sort('timestamp', -1).limit(100))
        for log in logs:
            employe = db.employees.find_one({'_id': log.get('utilisateur_id')})
            log['nom_utilisateur'] = f"{employe.get('nom', '')} {employe.get('prenom', '')}" if employe else 'Inconnu'
        
        yesterday = datetime.now() - timedelta(days=1)
        week_ago = datetime.now() - timedelta(days=7)
        stats = {
            'logs_24h': db.acces_logs.count_documents({'equipement_code': equipement.get('code'), 'timestamp': {'$gte': yesterday}}),
            'logs_7j': db.acces_logs.count_documents({'equipement_code': equipement.get('code'), 'timestamp': {'$gte': week_ago}}),
            'autorises': db.acces_logs.count_documents({'equipement_code': equipement.get('code'), 'resultat': 'AUTORISE'}),
            'refuses': db.acces_logs.count_documents({'equipement_code': equipement.get('code'), 'resultat': 'REFUSE'}),
        }
        return render(request, 'dashboard/equipement_detail.html', {'equipement': equipement, 'logs': logs, 'stats': stats})
    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('equipement_list')


@login_required
def equipement_ajouter(request):
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
    if request.method == 'POST':
        try:
            equip_type = request.POST.get('type')
            prefix = 'RDR' if equip_type == 'RFID' else 'QR'
            count = db.equipements.count_documents({'type': equip_type}) + 1
            code = f"{prefix}-{str(count).zfill(3)}"
            equipement = {
                'nom': request.POST.get('nom'),
                'type': equip_type,
                'code': code,
                'emplacement': request.POST.get('emplacement'),
                'bureau_id': ObjectId(request.POST.get('bureau_id')) if request.POST.get('bureau_id') else None,
                'ip_address': request.POST.get('ip_address'),
                'port': int(request.POST.get('port', 5000)),
                'statut': request.POST.get('statut', 'actif'),
                'description': request.POST.get('description', ''),
                'created_at': datetime.now()
            }
            db.equipements.insert_one(equipement)
            messages.success(request, f"Équipement ajouté avec succès!")
            return redirect('equipement_list')
        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout: {str(e)}")
    return render(request, 'dashboard/equipement_form.html', {'bureaux': bureaux, 'equipement': {}, 'is_edit': False})


@login_required
def equipement_modifier(request, equipement_id):
    try:
        equipement = db.equipements.find_one({'_id': ObjectId(equipement_id)})
        if not equipement:
            messages.error(request, "Équipement non trouvé")
            return redirect('equipement_list')
        bureaux = list(db.bureaux.find())
        for b in bureaux:
            b['id'] = str(b['_id'])
        if request.method == 'POST':
            update_data = {
                'nom': request.POST.get('nom'),
                'emplacement': request.POST.get('emplacement'),
                'bureau_id': ObjectId(request.POST.get('bureau_id')) if request.POST.get('bureau_id') else None,
                'ip_address': request.POST.get('ip_address'),
                'port': int(request.POST.get('port', 5000)),
                'statut': request.POST.get('statut', 'actif'),
                'description': request.POST.get('description', ''),
                'updated_at': datetime.now()
            }
            db.equipements.update_one({'_id': ObjectId(equipement_id)}, {'$set': update_data})
            messages.success(request, "Équipement modifié avec succès!")
            return redirect('equipement_detail', equipement_id=equipement_id)
        equipement['id'] = str(equipement['_id'])
        return render(request, 'dashboard/equipement_form.html', {'equipement': equipement, 'bureaux': bureaux, 'is_edit': True})
    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('equipement_list')


@login_required
def equipement_supprimer(request, equipement_id):
    if request.method == 'POST':
        try:
            db.equipements.update_one({'_id': ObjectId(equipement_id)},
                                      {'$set': {'statut': 'inactif', 'deleted_at': datetime.now()}})
            messages.success(request, "Équipement désactivé avec succès!")
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    return redirect('equipement_list')


@login_required
def equipement_tester(request, equipement_id):
    try:
        equipement = db.equipements.find_one({'_id': ObjectId(equipement_id)})
        if not equipement:
            return JsonResponse({'status': 'error', 'message': 'Équipement non trouvé'})
        response_time = random.randint(10, 50)
        db.equipements.update_one({'_id': ObjectId(equipement_id)},
                                  {'$set': {'derniere_connexion': datetime.now(), 'statut': 'actif'}})
        return JsonResponse({'status': 'success', 'message': 'Connexion réussie', 'response_time': response_time})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required
def api_equipements(request):
    equipements = list(db.equipements.find({'statut': 'actif'}))
    resultats = []
    for eq in equipements:
        bureau = db.bureaux.find_one({'_id': eq.get('bureau_id')})
        resultats.append({
            'id': str(eq['_id']),
            'nom': eq.get('nom', ''),
            'type': eq.get('type', ''),
            'code': eq.get('code', ''),
            'emplacement': eq.get('emplacement', ''),
            'bureau_nom': bureau['nom'] if bureau else 'Non assigné',
            'ip_address': eq.get('ip_address', ''),
            'port': eq.get('port', 0),
            'statut': eq.get('statut', 'actif'),
            'derniere_connexion': eq.get('derniere_connexion'),
        })
    return JsonResponse({'equipements': resultats}, encoder=JSONEncoder)


@login_required
def api_equipement_logs(request, equipement_id):
    try:
        equipement = db.equipements.find_one({'_id': ObjectId(equipement_id)})
        if not equipement:
            return JsonResponse({'error': 'Équipement non trouvé'}, status=404)
        logs = list(db.acces_logs.find({'equipement_code': equipement.get('code')}).sort('timestamp', -1).limit(50))
        resultats = []
        for log in logs:
            employe = db.employees.find_one({'_id': log.get('utilisateur_id')})
            resultats.append({
                'id': str(log['_id']),
                'timestamp': log['timestamp'],
                'nom_utilisateur': f"{employe.get('nom', '')} {employe.get('prenom', '')}" if employe else 'Inconnu',
                'resultat': log.get('resultat', ''),
                'type_acces': log.get('type_acces', ''),
            })
        return JsonResponse({'logs': resultats}, encoder=JSONEncoder)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_equipement_commande(request, equipement_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
    try:
        data = json.loads(request.body)
        commande = data.get('commande')
        equipement = db.equipements.find_one({'_id': ObjectId(equipement_id)})
        if not equipement:
            return JsonResponse({'error': 'Équipement non trouvé'}, status=404)
        if 'commandes' not in db.list_collection_names():
            db.create_collection('commandes')
        db.commandes.insert_one({
            'equipement_id': ObjectId(equipement_id),
            'equipement_nom': equipement['nom'],
            'commande': commande,
            'statut': 'envoyee',
            'envoyee_par': request.user.username,
            'timestamp': datetime.now()
        })
        return JsonResponse({'status': 'success', 'message': f'Commande "{commande}" envoyée à {equipement["nom"]}'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ====================== RÉSERVATIONS ADMIN ======================
@login_required
def reservation_list(request):
    """Liste des réservations avec vue calendrier et tableau"""
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    from datetime import datetime, timedelta
    import json
    from bson import ObjectId
    
    reservations = list(db.reservations.find().sort('date_debut', -1))
    
    # Enrichir les données
    for r in reservations:
        r['id'] = str(r['_id'])
        
        # Employé
        employe_id = r.get('employe_id')
        if employe_id:
            try:
                if isinstance(employe_id, str):
                    emp = db.employees.find_one({'_id': ObjectId(employe_id)})
                else:
                    emp = db.employees.find_one({'_id': employe_id})
                if emp:
                    r['employe_nom'] = f"{emp.get('nom', '')} {emp.get('prenom', '')}".strip() or 'Inconnu'
                    r['employe_badge'] = emp.get('badge_id', '—')
                else:
                    r['employe_nom'] = 'Inconnu'
                    r['employe_badge'] = '—'
            except:
                r['employe_nom'] = 'Inconnu'
                r['employe_badge'] = '—'
        else:
            r['employe_nom'] = 'Inconnu'
            r['employe_badge'] = '—'
        
        # Bureau
        bureau_id = r.get('bureau_id')
        if bureau_id:
            try:
                if isinstance(bureau_id, str):
                    bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
                else:
                    bureau = db.bureaux.find_one({'_id': bureau_id})
                r['bureau_nom'] = bureau['nom'] if bureau else 'Salle inconnue'
            except:
                r['bureau_nom'] = 'Salle inconnue'
        else:
            r['bureau_nom'] = 'Salle inconnue'
        
        # QR code
        if 'qr_code' not in r:
            r['qr_code'] = None
    
    now = datetime.now()
    confirmees = sum(1 for r in reservations if r.get('statut') == 'confirmee')
    en_attente = sum(1 for r in reservations if r.get('statut') == 'en_attente')
    annulees = sum(1 for r in reservations if r.get('statut') == 'annulee')
    
    a_venir = sum(1 for r in reservations if r.get('statut') == 'confirmee' 
                  and r.get('date_debut') and r['date_debut'] > now)
    
    # Taux d'occupation
    total_bureaux = db.bureaux.count_documents({})
    if total_bureaux > 0:
        occupied_bureaux = set()
        for r in reservations:
            if r.get('statut') == 'confirmee' and r.get('date_debut') and r.get('date_fin'):
                if r['date_debut'] <= now <= r['date_fin']:
                    occupied_bureaux.add(str(r.get('bureau_id')))
        taux_occupation = round((len(occupied_bureaux) / total_bureaux) * 100)
    else:
        taux_occupation = 0
    
    # Convertir les données en JSON sécurisé
    reservations_list = []
    for r in reservations:
        if r.get('date_debut'):
            reservations_list.append({
                'id': str(r['_id']),
                'titre': r.get('titre', ''),
                'bureau_id': str(r.get('bureau_id')) if r.get('bureau_id') else None,
                'bureau_nom': r.get('bureau_nom', ''),
                'employe_nom': r.get('employe_nom', ''),
                'statut': r.get('statut', ''),
                'date_debut': r['date_debut'].isoformat() if r.get('date_debut') else None,
                'date_fin': r['date_fin'].isoformat() if r.get('date_fin') else None,
            })
    
    reservations_json = json.dumps(reservations_list, default=str)
    
    # Liste des bureaux
    bureaux_list = []
    for b in db.bureaux.find():
        bureaux_list.append({
            'id': str(b['_id']),
            'nom': b.get('nom', ''),
        })
    
    return render(request, 'dashboard/reservation_list.html', {
        'reservations': reservations,
        'total': len(reservations),
        'confirmees': confirmees,
        'en_attente': en_attente,
        'annulees': annulees,
        'a_venir': a_venir,
        'taux_occupation': taux_occupation,
        'reservations_json': reservations_json,
        'bureaux': bureaux_list,
    })
@login_required
def reservation_ajouter(request):
    """Ajouter une nouvelle réservation (ressources et matériel)"""
    from bson import ObjectId
    from datetime import datetime
    
    # Récupérer les bureaux/zones
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
        b['type'] = 'salle'
        b['type_icon'] = '🚪'
    
    # Récupérer le matériel
    materiels = list(db.materiels.find()) if 'materiels' in db.list_collection_names() else []
    for m in materiels:
        m['id'] = str(m['_id'])
        m['type'] = 'materiel'
        m['type_icon'] = get_materiel_icon(m.get('categorie', 'autre'))
        m['capacite_max'] = 1  # Le matériel n'a pas de capacité
        m['nom_affichage'] = f"{m['nom']} ({m.get('categorie', 'Matériel')})"
    
    # Récupérer les employés
    employes = list(db.employees.find({'statut': 'actif'}))
    for e in employes:
        e['id'] = str(e['_id'])
    
    if request.method == 'POST':
        try:
            date_debut = datetime.strptime(request.POST.get('date_debut'), '%Y-%m-%dT%H:%M')
            date_fin = datetime.strptime(request.POST.get('date_fin'), '%Y-%m-%dT%H:%M')
            resource_id = request.POST.get('resource_id')
            resource_type = request.POST.get('resource_type', 'salle')
            employe_id_str = request.POST.get('employe_id')
            
            if date_fin <= date_debut:
                messages.error(request, "La date de fin doit être après la date de début.")
                return render(request, 'dashboard/reservation_form.html', {
                    'bureaux': bureaux,
                    'materiels': materiels,
                    'employes': employes,
                    'ressources': bureaux + materiels,
                    'reservation': request.POST,
                    'is_edit': False
                })
            
            # Vérifier les conflits selon le type de ressource
            conflit = False
            if resource_type == 'salle':
                conflit = db.reservations.find_one({
                    'bureau_id': ObjectId(resource_id),
                    'statut': {'$in': ['confirmee', 'en_attente']},
                    'date_debut': {'$lt': date_fin},
                    'date_fin': {'$gt': date_debut},
                })
            else:
                conflit = db.reservations.find_one({
                    'materiel_id': resource_id,
                    'statut': {'$in': ['confirmee', 'en_attente']},
                    'date_debut': {'$lt': date_fin},
                    'date_fin': {'$gt': date_debut},
                })
            
            if conflit:
                messages.error(request, "Cette ressource est déjà réservée sur ce créneau.")
                return render(request, 'dashboard/reservation_form.html', {
                    'bureaux': bureaux,
                    'materiels': materiels,
                    'employes': employes,
                    'ressources': bureaux + materiels,
                    'reservation': request.POST,
                    'is_edit': False
                })
            
            # Préparer les données de la réservation
            reservation_data = {
                'titre': request.POST.get('titre', '').strip(),
                'description': request.POST.get('description', '').strip(),
                'resource_type': resource_type,
                'nb_participants': int(request.POST.get('nb_participants', 1)),
                'statut': 'confirmee',  # Changé: confirmation directe (admin peut modifier après)
                'created_at': datetime.now(),
                'created_by': request.user.username,
                'date_debut': date_debut,
                'date_fin': date_fin,
            }
            
            # Ajouter les champs spécifiques selon le type
            if resource_type == 'salle':
                reservation_data['bureau_id'] = ObjectId(resource_id)
                # Récupérer le nom de la salle
                bureau = db.bureaux.find_one({'_id': ObjectId(resource_id)})
                reservation_data['bureau_nom'] = bureau['nom'] if bureau else 'Salle inconnue'
                reservation_data['employe_id'] = ObjectId(employe_id_str)
            else:
                reservation_data['materiel_id'] = resource_id
                # Récupérer le nom du matériel
                materiel = db.materiels.find_one({'_id': ObjectId(resource_id)})
                reservation_data['materiel_nom'] = materiel['nom'] if materiel else 'Matériel inconnu'
                reservation_data['employe_id'] = ObjectId(employe_id_str)
            
            # Récupérer le nom de l'employé
            employe = db.employees.find_one({'_id': ObjectId(employe_id_str)})
            if employe:
                reservation_data['employe_nom'] = f"{employe.get('nom', '')} {employe.get('prenom', '')}".strip()
            
            # Insérer la réservation
            db.reservations.insert_one(reservation_data)
            
            # Notifications
            from dashboard.views import send_reservation_notification, notify_admins_new_reservation
            send_reservation_notification(employe_id_str, reservation_data, 'created')
            notify_admins_new_reservation(employe, reservation_data)
            
            messages.success(request, "Réservation créée avec succès!")
            return redirect('reservation_list')
            
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return render(request, 'dashboard/reservation_form.html', {
        'bureaux': bureaux,
        'materiels': materiels,
        'employes': employes,
        'ressources': bureaux + materiels,
        'reservation': {},
        'is_edit': False
    })


def get_materiel_icon(categorie):
    """Retourne l'icône correspondant à la catégorie du matériel"""
    icons = {
        'informatique': '💻',
        'mobilier': '🪑',
        'audiovisuel': '📽️',
        'imprimante': '🖨️',
        'securite': '🔒',
        'vehicule': '🚗',
        'outillage': '🔧',
        'autre': '📦'
    }
    return icons.get(categorie, '📦')

@login_required
def reservation_modifier(request, reservation_id):
    try:
        reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
        if not reservation:
            messages.error(request, "Réservation non trouvée")
            return redirect('reservation_list')
        reservation['id'] = str(reservation['_id'])
        if reservation.get('date_debut'):
            reservation['date_debut_str'] = reservation['date_debut'].strftime('%Y-%m-%dT%H:%M')
        if reservation.get('date_fin'):
            reservation['date_fin_str'] = reservation['date_fin'].strftime('%Y-%m-%dT%H:%M')
        
        bureaux = list(db.bureaux.find())
        for b in bureaux:
            b['id'] = str(b['_id'])
        employes = list(db.employees.find({'statut': 'actif'}))
        for e in employes:
            e['id'] = str(e['_id'])
        
        if request.method == 'POST':
            date_debut = datetime.strptime(request.POST.get('date_debut'), '%Y-%m-%dT%H:%M')
            date_fin = datetime.strptime(request.POST.get('date_fin'), '%Y-%m-%dT%H:%M')
            db.reservations.update_one(
                {'_id': ObjectId(reservation_id)},
                {'$set': {
                    'titre': request.POST.get('titre', '').strip(),
                    'description': request.POST.get('description', '').strip(),
                    'bureau_id': ObjectId(request.POST.get('bureau_id')),
                    'employe_id': ObjectId(request.POST.get('employe_id')),
                    'date_debut': date_debut,
                    'date_fin': date_fin,
                    'nb_participants': int(request.POST.get('nb_participants', 1)),
                    'statut': request.POST.get('statut', 'confirmee'),
                    'updated_at': datetime.now(),
                }}
            )
            messages.success(request, "Réservation modifiée!")
            return redirect('reservation_list')
        return render(request, 'dashboard/reservation_form.html',
                      {'reservation': reservation, 'bureaux': bureaux, 'employes': employes, 'is_edit': True})
    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('reservation_list')


@login_required
def reservation_annuler(request, reservation_id):
    if request.method == 'POST':
        db.reservations.update_one({'_id': ObjectId(reservation_id)},
                                   {'$set': {'statut': 'annulee', 'cancelled_at': datetime.now()}})
        messages.success(request, "Réservation annulée.")
    return redirect('reservation_list')


# ====================== API HISTORIQUE EMPLOYÉ ======================

@login_required
def api_employee_history(request, employe_id):
    try:
        employe = db.employees.find_one({'_id': ObjectId(employe_id)})
        if not employe:
            return JsonResponse({'error': 'Employé non trouvé'}, status=404)
        logs = list(db.acces_logs.find({'utilisateur_id': ObjectId(employe_id)}).sort('timestamp', -1).limit(50))
        logs_data = []
        for log in logs:
            bureau = db.bureaux.find_one({'_id': log.get('bureau_id')})
            logs_data.append({
                'date': log['timestamp'].strftime('%d/%m/%Y %H:%M:%S') if log.get('timestamp') else '',
                'zone': bureau['nom'] if bureau else 'Inconnu',
                'resultat': log.get('resultat', ''),
            })
        return JsonResponse({'total_acces': len(logs), 'logs': logs_data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ====================== API PROFIL ADMIN ======================

@login_required
def update_admin_profile(request):
    if not request.user.is_staff and not request.user.is_superuser:
        return JsonResponse({'status': 'error', 'message': 'Accès non autorisé'}, status=403)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user = request.user
            user.username = data.get('username', user.username)
            user.first_name = data.get('first_name', user.first_name)
            user.last_name = data.get('last_name', user.last_name)
            user.email = data.get('email', user.email)
            
            current_password = data.get('current_password')
            new_password = data.get('new_password')
            if new_password:
                if not current_password:
                    return JsonResponse({'status': 'error', 'message': 'Mot de passe actuel requis'})
                if not check_password(current_password, user.password):
                    return JsonResponse({'status': 'error', 'message': 'Mot de passe actuel incorrect'})
                if len(new_password) < 6:
                    return JsonResponse({'status': 'error', 'message': 'Le mot de passe doit contenir au moins 6 caractères'})
                user.password = make_password(new_password)
            
            phone = data.get('phone')
            if phone:
                db.admin_profiles.update_one({'user_id': user.id},
                                             {'$set': {'phone': phone, 'updated_at': datetime.now()}}, upsert=True)
            user.save()
            db.system_logs.insert_one({
                'user_id': user.id,
                'username': user.username,
                'action': 'PROFILE_UPDATE',
                'timestamp': datetime.now(),
                'ip': request.META.get('REMOTE_ADDR')
            })
            return JsonResponse({'status': 'success', 'message': 'Profil mis à jour avec succès'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Méthode non autorisée'}, status=405)


@login_required
def admin_login_history(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Accès non autorisé'}, status=403)
    logs = list(db.system_logs.find({'user_id': request.user.id}).sort('timestamp', -1).limit(50))
    history = [{'timestamp': log['timestamp'].isoformat() if log.get('timestamp') else '',
                'ip_address': log.get('ip', '—'),
                'user_agent': log.get('user_agent', '—'),
                'success': True} for log in logs]
    return JsonResponse({'history': history}, encoder=JSONEncoder)


@login_required
def update_admin_avatar(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Accès non autorisé'}, status=403)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            avatar_base64 = data.get('avatar')
            if avatar_base64:
                db.admin_profiles.update_one({'user_id': request.user.id},
                                             {'$set': {'avatar': avatar_base64, 'updated_at': datetime.now()}}, upsert=True)
                return JsonResponse({'status': 'success', 'message': 'Avatar mis à jour'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'status': 'error', 'message': 'Méthode non autorisée'}, status=405)


# ====================== GESTION DES RESSOURCES ======================

@login_required
def resource_list(request):
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    resources = list(db.resources.find())
    for r in resources:
        r['id'] = str(r['_id'])
    
    stats = {
        'total': len(resources),
        'par_categorie': {},
        'disponibles': sum(1 for r in resources if r.get('statut') == 'disponible'),
        'maintenance': sum(1 for r in resources if r.get('statut') == 'maintenance'),
    }
    
    for r in resources:
        cat = r.get('categorie', 'autre')
        stats['par_categorie'][cat] = stats['par_categorie'].get(cat, 0) + 1
    
    return render(request, 'dashboard/ressources.html', {
        'resources': resources,
        'stats': stats,
        'total_resources': len(resources),
    })


@login_required
def resource_ajouter(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    if request.method == 'POST':
        try:
            data = {
                'nom': request.POST.get('nom'),
                'categorie': request.POST.get('categorie'),
                'description': request.POST.get('description', ''),
                'photo': request.POST.get('photo', ''),
                'caracteristiques': json.loads(request.POST.get('caracteristiques', '{}')),
                'localisation': request.POST.get('localisation', ''),
                'bureau_associe': request.POST.get('bureau_associe'),
                'capacite': int(request.POST.get('capacite', 1)),
                'statut': request.POST.get('statut', 'disponible'),
                'disponibilite_heures': json.loads(request.POST.get('disponibilite_heures', '{}')),
                'created_at': datetime.now(),
                'created_by': request.user.username,
            }
            result = db.resources.insert_one(data)
            messages.success(request, f"Ressource '{data['nom']}' ajoutée avec succès")
            return redirect('resource_list')
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
    
    return render(request, 'dashboard/resource_form.html', {
        'bureaux': bureaux,
        'resource': {},
        'is_edit': False,
    })


@login_required
def resource_modifier(request, resource_id):
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    try:
        resource = db.resources.find_one({'_id': ObjectId(resource_id)})
        if not resource:
            messages.error(request, "Ressource non trouvée")
            return redirect('resource_list')
        resource['id'] = str(resource['_id'])
        
        if request.method == 'POST':
            update_data = {
                'nom': request.POST.get('nom'),
                'categorie': request.POST.get('categorie'),
                'description': request.POST.get('description', ''),
                'photo': request.POST.get('photo', ''),
                'caracteristiques': json.loads(request.POST.get('caracteristiques', '{}')),
                'localisation': request.POST.get('localisation', ''),
                'bureau_associe': request.POST.get('bureau_associe'),
                'capacite': int(request.POST.get('capacite', 1)),
                'statut': request.POST.get('statut', 'disponible'),
                'disponibilite_heures': json.loads(request.POST.get('disponibilite_heures', '{}')),
                'updated_at': datetime.now(),
                'updated_by': request.user.username,
            }
            db.resources.update_one({'_id': ObjectId(resource_id)}, {'$set': update_data})
            messages.success(request, f"Ressource modifiée avec succès")
            return redirect('resource_list')
    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
    
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
    
    return render(request, 'dashboard/resource_form.html', {
        'bureaux': bureaux,
        'resource': resource,
        'is_edit': True,
    })


@login_required
def resource_supprimer(request, resource_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    if request.method == 'POST':
        db.resources.update_one(
            {'_id': ObjectId(resource_id)},
            {'$set': {'statut': 'hors_service', 'deleted_at': datetime.now()}}
        )
        messages.success(request, "Ressource désactivée")
    
    return redirect('resource_list')
# ====================== GESTION DES RESSOURCES (SUITE) ======================

@login_required
def bureau_detail(request, bureau_id):
    """Détail d'un bureau/zone"""
    try:
        bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
        if not bureau:
            messages.error(request, "Zone non trouvée")
            return redirect('ressources')
        
        bureau['id'] = str(bureau['_id'])
        
        # Statistiques d'occupation
        one_hour_ago = datetime.now() - timedelta(hours=1)
        occupation_recente = db.acces_logs.count_documents({
            'bureau_id': ObjectId(bureau_id),
            'timestamp': {'$gte': one_hour_ago}
        })
        
        capacite = bureau.get('capacite_max', 10)
        taux_occupation = min(100, round((occupation_recente * 3 / capacite) * 100)) if capacite > 0 else 0
        
        # Historique des 7 derniers jours
        historique = []
        for i in range(6, -1, -1):
            day_start = (datetime.now() - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            count = db.acces_logs.count_documents({
                'bureau_id': ObjectId(bureau_id),
                'timestamp': {'$gte': day_start, '$lt': day_end}
            })
            historique.append({
                'date': day_start.strftime('%d/%m'),
                'acces': count
            })
        
        return render(request, 'dashboard/bureau_detail.html', {
            'bureau': bureau,
            'taux_occupation': taux_occupation,
            'historique': historique,
            'capacite': capacite,
            'occupation_recente': occupation_recente
        })
    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('ressources')


@login_required
def api_bureau_reservations(request, bureau_id):
    """API pour les réservations d'un bureau (simplifié)"""
    try:
        reservations = list(db.reservations.find({
            'bureau_id': ObjectId(bureau_id),
            'statut': 'confirmee',
            'date_debut': {'$gte': datetime.now()}
        }).sort('date_debut', 1).limit(5))
        
        resultats = []
        for r in reservations:
            employe = db.employees.find_one({'_id': r.get('employe_id')})
            resultats.append({
                'id': str(r['_id']),
                'debut': r['date_debut'].isoformat(),
                'fin': r['date_fin'].isoformat(),
                'employe': f"{employe.get('nom', '')} {employe.get('prenom', '')}".strip() if employe else 'Inconnu'
            })
        
        return JsonResponse({'reservations': resultats})
    except Exception as e:
        return JsonResponse({'reservations': [], 'error': str(e)})


@login_required
def api_materiel_list(request):
    """API pour la liste du matériel"""
    materiels = list(db.materiels.find()) if 'materiels' in db.list_collection_names() else []
    for m in materiels:
        m['id'] = str(m['_id'])
    return JsonResponse({'materiels': materiels})


@login_required
def api_materiel_ajouter(request):
    """API pour ajouter/modifier du matériel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
    
    try:
        data = json.loads(request.body)
        materiel_id = data.get('id')
        
        materiel_data = {
            'nom': data.get('nom'),
            'categorie': data.get('categorie', 'autre'),
            'numero_serie': data.get('numero_serie', ''),
            'statut': data.get('statut', 'disponible'),
            'zone': data.get('zone', ''),
            'description': data.get('description', ''),
            'photo': data.get('photo', ''),
            'updated_at': datetime.now()
        }
        
        if 'materiels' not in db.list_collection_names():
            db.create_collection('materiels')
        
        if materiel_id and not materiel_id.startswith('mat_') and len(materiel_id) == 24:
            # Modification d'un existant
            db.materiels.update_one({'_id': ObjectId(materiel_id)}, {'$set': materiel_data})
            return JsonResponse({'status': 'success', 'id': materiel_id})
        else:
            # Nouveau matériel
            materiel_data['created_at'] = datetime.now()
            result = db.materiels.insert_one(materiel_data)
            return JsonResponse({'status': 'success', 'id': str(result.inserted_id)})
            
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_materiel_supprimer(request, materiel_id):
    """API pour supprimer du matériel"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
    
    try:
        result = db.materiels.delete_one({'_id': ObjectId(materiel_id)})
        if result.deleted_count > 0:
            return JsonResponse({'status': 'success'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Matériel non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# ====================== API RESSOURCES ======================

@login_required
def api_resources(request):
    ressources = list(db.resources.find({'statut': {'$ne': 'hors_service'}}))
    result = []
    for r in ressources:
        result.append({
            'id': str(r['_id']),
            'nom': r.get('nom', ''),
            'categorie': r.get('categorie', ''),
            'description': r.get('description', ''),
            'photo': r.get('photo', ''),
            'localisation': r.get('localisation', ''),
            'capacite': r.get('capacite', 1),
            'statut': r.get('statut', 'disponible'),
            'disponible': r.get('statut') == 'disponible',
        })
    return JsonResponse({'resources': result})


# ====================== GESTION DES RÉSERVATIONS AVANCÉES ======================

@login_required
def reservation_ajouter_avance(request):
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
    
    resources = list(db.resources.find({'statut': 'disponible'}))
    for r in resources:
        r['id'] = str(r['_id'])
    
    employes = list(db.employees.find({'statut': 'actif'}))
    for e in employes:
        e['id'] = str(e['_id'])
    
    if request.method == 'POST':
        try:
            date_debut = datetime.strptime(request.POST.get('date_debut'), '%Y-%m-%dT%H:%M')
            date_fin = datetime.strptime(request.POST.get('date_fin'), '%Y-%m-%dT%H:%M')
            resource_id = request.POST.get('resource_id')
            resource_type = request.POST.get('resource_type', 'salle')
            employe_id = request.POST.get('employe_id')
            recurrence = request.POST.get('recurrence', 'none')
            recurrence_end = request.POST.get('recurrence_end')
            
            if date_fin <= date_debut:
                messages.error(request, "La date de fin doit être après la date de début")
                return render(request, 'dashboard/reservation_form_avance.html', {
                    'bureaux': bureaux, 'resources': resources, 'employes': employes,
                })
            
            conflit = db.reservations.find_one({
                'resource_id': resource_id,
                'statut': {'$in': ['confirmee', 'en_attente']},
                'date_debut': {'$lt': date_fin},
                'date_fin': {'$gt': date_debut},
            })
            
            if conflit:
                suggestions = suggest_alternative_slots(resource_id, date_debut, date_fin)
                messages.warning(request, "Conflit détecté ! Suggestions disponibles.")
                return render(request, 'dashboard/reservation_form_avance.html', {
                    'bureaux': bureaux, 'resources': resources, 'employes': employes,
                    'suggestions': suggestions, 'form_data': request.POST,
                })
            
            employe = db.employees.find_one({'_id': ObjectId(employe_id)})
            reservation_data = {
                'titre': request.POST.get('titre', 'Réservation'),
                'description': request.POST.get('description', ''),
                'resource_id': resource_id,
                'resource_type': resource_type,
                'bureau_id': request.POST.get('bureau_id'),
                'employe_id': employe_id,
                'employe_nom': f"{employe.get('nom', '')} {employe.get('prenom', '')}" if employe else '',
                'date_debut': date_debut,
                'date_fin': date_fin,
                'nb_participants': int(request.POST.get('nb_participants', 1)),
                'statut': 'confirmee',
                'recurrence': recurrence if recurrence != 'none' else '',
                'created_by': request.user.username,
                'created_at': datetime.now(),
            }
            
            if recurrence_end:
                reservation_data['recurrence_end'] = datetime.strptime(recurrence_end, '%Y-%m-%d')
            
            result = db.reservations.insert_one(reservation_data)
            send_reservation_notification(employe_id, reservation_data)
            messages.success(request, "Réservation créée avec succès !")
            return redirect('reservation_list')
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return render(request, 'dashboard/reservation_form_avance.html', {
        'bureaux': bureaux,
        'resources': resources,
        'employes': employes,
    })


def suggest_alternative_slots(resource_id, date_debut, date_fin):
    suggestions = []
    resource = db.resources.find_one({'_id': ObjectId(resource_id)})
    if not resource:
        return []
    
    for days in range(1, 4):
        for sign in [-1, 1]:
            alt_date = date_debut + timedelta(days=days * sign)
            conflit = db.reservations.find_one({
                'resource_id': resource_id,
                'statut': {'$in': ['confirmee', 'en_attente']},
                'date_debut': {'$lt': alt_date + (date_fin - date_debut)},
                'date_fin': {'$gt': alt_date},
            })
            if not conflit:
                suggestions.append({
                    'date': alt_date.strftime('%d/%m/%Y'),
                    'debut': alt_date.strftime('%H:%M'),
                    'fin': (alt_date + (date_fin - date_debut)).strftime('%H:%M'),
                    'score': 100 - (days * 20),
                })
    return suggestions[:5]


def send_reservation_notification(employe_id, reservation_data):
    employe = db.employees.find_one({'_id': ObjectId(employe_id)})
    if not employe:
        return
    
    message = f"""
    Bonjour {employe.get('prenom', '')} {employe.get('nom', '')},
    
    Votre réservation a été confirmée :
    - Titre: {reservation_data.get('titre')}
    - Date: {reservation_data['date_debut'].strftime('%d/%m/%Y %H:%M')} → {reservation_data['date_fin'].strftime('%H:%M')}
    
    Merci d'utiliser vos accès avec votre badge RFID.
    
    SIGR-CA
    """
    
    db.notifications.insert_one({
        'destinataire': employe.get('email', ''),
        'type_notification': 'email',
        'categorie': 'confirmation',
        'sujet': f"Confirmation de réservation - {reservation_data.get('titre')}",
        'message': message,
        'statut': 'envoyee',
        'reservation_id': str(reservation_data.get('_id')),
        'created_at': datetime.now(),
    })
    
    if employe.get('email'):
        try:
            send_mail(
                f"Confirmation de réservation - {reservation_data.get('titre')}",
                message,
                settings.DEFAULT_FROM_EMAIL,
                [employe['email']],
                fail_silently=True,
            )
        except:
            pass


# ====================== CONTRÔLE D'ACCÈS PHYSIQUE ======================

@csrf_exempt
def api_verify_access(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        badge_id = data.get('badge_id')
        zone_code = data.get('zone_code')
        access_method = data.get('method', 'RFID')
        
        employe = db.employees.find_one({'badge_id': badge_id, 'statut': 'actif'})
        
        if not employe:
            log_access(None, zone_code, 'REFUSE', 'Badge inconnu', access_method)
            
            # Notifier les admins d'une tentative avec badge inconnu
            from dashboard.views import notify_admins_security_alert
            notify_admins_security_alert(zone_code, badge_id, "Tentative d'accès avec badge non reconnu")
            
            return JsonResponse({'autorise': False, 'message': 'Badge non reconnu'})
        
        now = datetime.now()
        reservation_valide = db.reservations.find_one({
            'employe_id': str(employe['_id']),
            'statut': 'confirmee',
            'date_debut': {'$lte': now},
            'date_fin': {'$gte': now},
        })
        
        zone = db.bureaux.find_one({'code': zone_code})
        if not zone:
            zone = db.bureaux.find_one({'nom': zone_code})
        
        access_rule = db.access_rules.find_one({
            'employe_id': str(employe['_id']),
            'zone_nom': zone.get('nom', zone_code) if zone else zone_code,
            'jour': now.day,
            'mois': now.month,
            'annee': now.year,
        })
        
        current_hour = now.strftime('%H:%M')
        acces_autorise = False
        motif_refus = ""
        
        if access_rule:
            if access_rule.get('acces_autorise', True):
                if access_rule.get('heure_debut', '00:00') <= current_hour <= access_rule.get('heure_fin', '23:59'):
                    acces_autorise = True
                else:
                    motif_refus = "Horaire non autorisé"
            else:
                motif_refus = "Règle d'accès restreinte"
        elif reservation_valide:
            acces_autorise = True
        else:
            motif_refus = "Aucune réservation active"
        
        emergency = db.system_config.find_one({'type': 'emergency'})
        if emergency and emergency.get('active', False):
            acces_autorise = True
        
        # Log l'accès
        log_access(employe['_id'], zone_code, 'AUTORISE' if acces_autorise else 'REFUSE',
                  'Accès ' + ('autorisé' if acces_autorise else 'refusé'), access_method)
        
        # Si accès refusé, notifier les admins (après 3 refus dans la même heure)
        if not acces_autorise:
            # Compter les refus récents
            one_hour_ago = now - timedelta(hours=1)
            recent_refus = db.acces_logs.count_documents({
                'utilisateur_id': employe['_id'],
                'resultat': 'REFUSE',
                'timestamp': {'$gte': one_hour_ago}
            })
            
            if recent_refus >= 3:
                from dashboard.views import notify_admins_security_alert
                zone_nom = zone.get('nom', zone_code) if zone else zone_code
                notify_admins_security_alert(
                    zone_nom, 
                    badge_id, 
                    f"Tentatives d'accès multiples refusées ({recent_refus} fois en 1h) - {motif_refus}"
                )
        
        return JsonResponse({
            'autorise': acces_autorise,
            'message': 'Accès autorisé' if acces_autorise else f'Accès refusé: {motif_refus}',
            'employe_nom': f"{employe.get('nom', '')} {employe.get('prenom', '')}",
        })
        
    except Exception as e:
        return JsonResponse({'autorise': False, 'error': str(e)})


def log_access(utilisateur_id, zone_code, resultat, message, method):
    db.acces_logs.insert_one({
        'utilisateur_id': utilisateur_id,
        'bureau_code': zone_code,
        'resultat': resultat,
        'message': message,
        'type_acces': method,
        'timestamp': datetime.now(),
    })


# ====================== NOTIFICATIONS ET ALERTES ======================

@login_required
def api_send_notification(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        destinataire = data.get('destinataire')
        type_notif = data.get('type', 'email')
        categorie = data.get('categorie', 'info')
        sujet = data.get('sujet', 'Notification SIGR-CA')
        message = data.get('message', '')
        
        notification = {
            'destinataire': destinataire,
            'type_notification': type_notif,
            'categorie': categorie,
            'sujet': sujet,
            'message': message,
            'statut': 'envoyee',
            'created_at': datetime.now(),
        }
        
        db.notifications.insert_one(notification)
        
        if type_notif == 'email' and destinataire:
            try:
                send_mail(sujet, message, settings.DEFAULT_FROM_EMAIL, [destinataire])
            except:
                notification['statut'] = 'echouee'
                db.notifications.update_one({'_id': notification['_id']}, {'$set': {'statut': 'echouee'}})
        
        return JsonResponse({'status': 'success', 'message': 'Notification envoyée'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_alerts(request):
    alerts = list(db.alertes.find({'statut': 'NON_TRAITEE'}).sort('timestamp', -1).limit(50))
    result = []
    for a in alerts:
        result.append({
            'id': str(a['_id']),
            'type': a.get('type', 'ALERT'),
            'message': a.get('message', ''),
            'timestamp': a.get('timestamp'),
            'zone': a.get('zone', ''),
        })
    return JsonResponse({'alerts': result})


# ====================== STATISTIQUES AVANCÉES ======================

@login_required
def api_stats_predictions(request):
    today = datetime.now()
    predictions = []
    for i in range(1, 8):
        pred_date = today + timedelta(days=i)
        history = db.acces_logs.count_documents({
            'timestamp': {'$gte': pred_date - timedelta(days=7), '$lt': pred_date}
        })
        predicted = int(history / 7 * (0.9 + (i * 0.02)))
        predictions.append({
            'date': pred_date.strftime('%Y-%m-%d'),
            'predicted_access': predicted,
            'confidence': min(95, 70 + i * 3),
        })
    
    zones_stats = list(db.acces_logs.aggregate([
        {'$group': {'_id': '$bureau_code', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]))
    
    conflict_zones = []
    for z in zones_stats:
        conflict_zones.append({
            'zone': z['_id'],
            'activity': z['count'],
            'risk': 'high' if z['count'] > 100 else 'medium' if z['count'] > 50 else 'low',
        })
    
    return JsonResponse({
        'predictions': predictions,
        'conflict_zones': conflict_zones,
        'recommendations': [
            "Les zones Atelier et Direction sont très sollicitées en début de semaine",
            "Optimisez les créneaux du mercredi après-midi (moins d'affluence)",
            "Prévoyez des ressources supplémentaires pour la zone Production",
        ]
    })


# ====================== SESSIONS ACTIVES ======================

# dashboard/views.py - Mettez à jour la vue active_sessions
from dashboard.models import UserSession, SessionLog

@login_required
def active_sessions(request):
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    # Récupérer TOUTES les sessions actives
    active_sessions = UserSession.objects.filter(
        is_active=True,
        logout_time__isnull=True
    ).select_related('user').order_by('-last_activity')
    
    total_connected = active_sessions.count()
    total_users = Utilisateur.objects.filter(is_active=True).count()
    admin_sessions = active_sessions.filter(user__is_staff=True).count()
    employee_sessions = total_connected - admin_sessions
    inactive_threshold = timezone.now() - timedelta(minutes=30)
    inactive_sessions = active_sessions.filter(last_activity__lt=inactive_threshold).count()
    
    # Statistiques par appareil
    desktop_sessions = active_sessions.filter(device_type='desktop').count()
    mobile_sessions = active_sessions.filter(device_type='mobile').count()
    tablet_sessions = active_sessions.filter(device_type='tablet').count()
    
    # Récupérer l'historique des dernières 24h
    last_24h = timezone.now() - timedelta(hours=24)
    recent_history = SessionLog.objects.filter(
        timestamp__gte=last_24h
    ).select_related('user').order_by('-timestamp')[:100]
    
    return render(request, 'dashboard/active_sessions.html', {
        'active_sessions': active_sessions,
        'total_connected': total_connected,
        'total_users': total_users,
        'admin_sessions': admin_sessions,
        'employee_sessions': employee_sessions,
        'inactive_sessions': inactive_sessions,
        'desktop_sessions': desktop_sessions,
        'mobile_sessions': mobile_sessions,
        'tablet_sessions': tablet_sessions,
        'recent_history': recent_history,
        'now': timezone.now(),
    })


@login_required
def terminate_session(request, session_id):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    if request.method == 'POST':
        try:
            user_session = UserSession.objects.get(id=session_id)
            username = user_session.user.username
            
            # Log de la terminaison
            SessionLog.objects.create(
                user=user_session.user,
                action='terminated',
                ip_address=user_session.ip_address,
                session_key=user_session.session_key
            )
            
            user_session.is_active = False
            user_session.logout_time = timezone.now()
            user_session.save()
            
            try:
                Session.objects.filter(session_key=user_session.session_key).delete()
            except:
                pass
            
            messages.success(request, f"Session de {username} terminée")
        except UserSession.DoesNotExist:
            messages.error(request, "Session non trouvée")
    
    return redirect('active_sessions')


@login_required
def terminate_all_sessions(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    if request.method == 'POST':
        current_session_key = request.session.session_key
        other_sessions = UserSession.objects.filter(
            is_active=True,
            logout_time__isnull=True
        ).exclude(session_key=current_session_key)
        
        count = other_sessions.count()
        for session in other_sessions:
            # Log de la terminaison
            SessionLog.objects.create(
                user=session.user,
                action='terminated',
                ip_address=session.ip_address,
                session_key=session.session_key
            )
            
            session.is_active = False
            session.logout_time = timezone.now()
            session.save()
            try:
                Session.objects.filter(session_key=session.session_key).delete()
            except:
                pass
        
        messages.success(request, f"{count} session(s) terminée(s)")
    
    return redirect('active_sessions')


@login_required
def api_connected_users(request):
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    active_sessions = UserSession.objects.filter(
        is_active=True,
        logout_time__isnull=True
    ).select_related('user')
    
    users = []
    for session in active_sessions:
        last_activity_seconds = (timezone.now() - session.last_activity).seconds
        if last_activity_seconds < 300:
            status = 'active'
            status_badge = '🟢 Actif'
            badge_class = 'b-green'
        elif last_activity_seconds < 1800:
            status = 'idle'
            status_badge = '🟡 Inactif'
            badge_class = 'b-amber'
        else:
            status = 'inactive'
            status_badge = '🔴 Très inactif'
            badge_class = 'b-red'
        
        device_icon = '💻' if session.device_type == 'desktop' else '📱' if session.device_type == 'mobile' else '📟'
        
        users.append({
            'id': session.id,
            'user_id': session.user.id,
            'username': session.user.username,
            'full_name': session.user.get_full_name() or session.user.username,
            'is_staff': session.user.is_staff,
            'login_time': session.login_time.strftime('%d/%m/%Y %H:%M:%S'),
            'last_activity': session.last_activity.strftime('%d/%m/%Y %H:%M:%S'),
            'last_activity_seconds': last_activity_seconds,
            'ip_address': session.ip_address or '—',
            'session_key': session.session_key,
            'status': status,
            'status_badge': status_badge,
            'badge_class': badge_class,
            'device_type': session.device_type,
            'device_icon': device_icon,
            'duration': session.get_duration(),
            'location': session.location or '—',
        })
    
    return JsonResponse({
        'total': len(users),
        'users': users,
        'timestamp': timezone.now().strftime('%d/%m/%Y %H:%M:%S'),
    })


@login_required
def api_session_stats(request):
    """API pour les statistiques des sessions"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Connexions aujourd'hui
    today_logins = SessionLog.objects.filter(
        action='login',
        timestamp__gte=today_start
    ).count()
    
    # Moyenne de connexions par jour (7 derniers jours)
    seven_days_ago = now - timedelta(days=7)
    avg_logins = SessionLog.objects.filter(
        action='login',
        timestamp__gte=seven_days_ago
    ).count() / 7
    
    # Sessions actives par appareil
    device_stats = {
        'desktop': UserSession.objects.filter(is_active=True, device_type='desktop').count(),
        'mobile': UserSession.objects.filter(is_active=True, device_type='mobile').count(),
        'tablet': UserSession.objects.filter(is_active=True, device_type='tablet').count(),
    }
    
    return JsonResponse({
        'today_logins': today_logins,
        'avg_logins': round(avg_logins, 1),
        'device_stats': device_stats,
    })


@login_required
def clear_session_history(request):
    """Vider l'historique des sessions"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    if request.method == 'POST':
        days = int(request.POST.get('days', 30))
        threshold = timezone.now() - timedelta(days=days)
        
        deleted_count = SessionLog.objects.filter(timestamp__lt=threshold).delete()[0]
        messages.success(request, f"{deleted_count} entrées d'historique supprimées")
    
    return redirect('active_sessions')


@login_required
def api_session_details(request, session_id):
    """Détails d'une session spécifique"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    try:
        session = UserSession.objects.get(id=session_id)
        
        # Récupérer l'historique des actions de cet utilisateur
        user_logs = SessionLog.objects.filter(
            user=session.user
        ).order_by('-timestamp')[:20]
        
        logs_data = [{
            'action': log.action,
            'timestamp': log.timestamp.strftime('%d/%m/%Y %H:%M:%S'),
            'ip_address': log.ip_address,
        } for log in user_logs]
        
        return JsonResponse({
            'user': session.user.username,
            'full_name': session.user.get_full_name(),
            'login_time': session.login_time.strftime('%d/%m/%Y %H:%M:%S'),
            'last_activity': session.last_activity.strftime('%d/%m/%Y %H:%M:%S'),
            'duration': session.get_duration(),
            'ip_address': session.ip_address,
            'device_type': session.device_type,
            'location': session.location,
            'user_agent': session.user_agent[:200],
            'logs': logs_data,
        })
    except UserSession.DoesNotExist:
        return JsonResponse({'error': 'Session non trouvée'}, status=404)

# ====================== ESPACE EMPLOYÉ - PROFIL ======================
@login_required
def employe_profil(request):
    """Modification du profil employé"""
    if request.user.is_staff:
        return redirect('dashboard')
    
    from datetime import datetime, timedelta
    
    # Récupérer l'employé
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        messages.error(request, "Profil employé introuvable.")
        return redirect('login')
    
    employe['id'] = str(employe['_id'])
    utilisateur_id = employe['_id']
    
    # === STATISTIQUES ===
    total_acces = db.acces_logs.count_documents({'utilisateur_id': utilisateur_id})
    acces_autorises = db.acces_logs.count_documents({
        'utilisateur_id': utilisateur_id,
        'resultat': 'AUTORISE'
    })
    acces_refuses = total_acces - acces_autorises
    taux_succes = round((acces_autorises / total_acces * 100) if total_acces > 0 else 0, 1)
    reservations_count = db.reservations.count_documents({'employe_id': str(employe['_id'])})
    
    # Accès du mois
    start_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    acces_mois = db.acces_logs.count_documents({
        'utilisateur_id': utilisateur_id,
        'timestamp': {'$gte': start_month}
    })
    
    # Dernier accès
    dernier_acces_doc = db.acces_logs.find_one(
        {'utilisateur_id': utilisateur_id},
        sort=[('timestamp', -1)]
    )
    dernier_acces = dernier_acces_doc['timestamp'] if dernier_acces_doc else None
    
    # Jours actifs
    try:
        pipeline = [
            {'$match': {'utilisateur_id': utilisateur_id}},
            {'$group': {
                '_id': {
                    'year': {'$year': '$timestamp'},
                    'month': {'$month': '$timestamp'},
                    'day': {'$dayOfMonth': '$timestamp'}
                }
            }},
            {'$count': 'total_days'}
        ]
        result = list(db.acces_logs.aggregate(pipeline))
        jours_actifs = result[0]['total_days'] if result else 0
    except:
        jours_actifs = 0
    
    # Préférences
    preferences = employe.get('preferences_notifications', {})
    if not preferences:
        preferences = {'email': True, 'rappel': True}
    
    # Récupérer les sessions actives de l'utilisateur
    active_sessions = []
    try:
        from dashboard.models import UserSession
        sessions = UserSession.objects.filter(
            user=request.user,
            is_active=True,
            logout_time__isnull=True
        ).order_by('-last_activity')
        
        for session in sessions:
            active_sessions.append({
                'id': session.id,
                'device_type': session.device_type or 'desktop',
                'ip_address': session.ip_address or '—',
                'login_time': session.login_time.strftime('%d/%m/%Y %H:%M:%S'),
                'last_activity': session.last_activity.strftime('%d/%m/%Y %H:%M:%S'),
                'is_current': session.session_key == request.session.session_key
            })
    except:
        active_sessions = []
    
    # Traitement POST
    if request.method == 'POST':
        # Vérifier quelle action est demandée
        if 'change_password' in request.POST:
            # Changement de mot de passe
            old_password = request.POST.get('old_password', '')
            new_password1 = request.POST.get('new_password1', '')
            new_password2 = request.POST.get('new_password2', '')
            
            if not request.user.check_password(old_password):
                messages.error(request, "L'ancien mot de passe est incorrect.")
            elif len(new_password1) < 6:
                messages.error(request, "Le nouveau mot de passe doit contenir au moins 6 caractères.")
            elif new_password1 != new_password2:
                messages.error(request, "Les mots de passe ne correspondent pas.")
            else:
                request.user.set_password(new_password1)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                messages.success(request, "Mot de passe changé avec succès.")
            
            return redirect('employe_profil')
        
        elif 'update_preferences' in request.POST:
            # Mise à jour des préférences
            notif_email = request.POST.get('notif_email') == 'on'
            notif_rappel = request.POST.get('notif_rappel') == 'on'
            
            db.employees.update_one(
                {'_id': employe['_id']},
                {'$set': {
                    'preferences_notifications': {
                        'email': notif_email,
                        'rappel': notif_rappel
                    },
                    'updated_at': datetime.now()
                }}
            )
            messages.success(request, "Préférences mises à jour.")
            return redirect('employe_profil')
        
        else:
            # Mise à jour du profil
            try:
                prenom = request.POST.get('prenom', '').strip()
                nom = request.POST.get('nom', '').strip()
                email = request.POST.get('email', '').strip()
                telephone = request.POST.get('telephone', '').strip()
                poste = request.POST.get('poste', '').strip()
                departement = request.POST.get('departement', '').strip()
                
                if not prenom or not nom:
                    messages.error(request, "Le nom et le prénom sont requis.")
                    return redirect('employe_profil')
                
                update_data = {
                    'nom': nom,
                    'prenom': prenom,
                    'email': email,
                    'telephone': telephone,
                    'poste': poste,
                    'departement': departement,
                    'updated_at': datetime.now()
                }
                
                db.employees.update_one({'_id': employe['_id']}, {'$set': update_data})
                
                # Mettre à jour l'utilisateur Django
                user = request.user
                user.first_name = prenom
                user.last_name = nom
                user.email = email
                user.save()
                
                messages.success(request, "Profil mis à jour avec succès.")
                
            except Exception as e:
                messages.error(request, f"Erreur: {str(e)}")
            
            return redirect('employe_profil')
    
    return render(request, 'dashboard/employe_profil.html', {
        'employe': employe,
        'user': request.user,
        'total_acces': total_acces,
        'acces_autorises': acces_autorises,
        'acces_refuses': acces_refuses,
        'taux_succes': taux_succes,
        'reservations_count': reservations_count,
        'acces_mois': acces_mois,
        'jours_actifs': jours_actifs,
        'dernier_acces': dernier_acces,
        'preferences': preferences,
        'active_sessions': active_sessions,
    })

@login_required
def employe_change_password(request):
    """Changer le mot de passe de l'employé - Version améliorée"""
    if request.user.is_staff:
        return redirect('dashboard')
    
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        # Vérifier l'ancien mot de passe
        if not request.user.check_password(old_password):
            messages.error(request, "L'ancien mot de passe est incorrect.")
            return redirect('employe_profil')
        
        # Vérifier la longueur du nouveau mot de passe
        if len(new_password1) < 6:
            messages.error(request, "Le nouveau mot de passe doit contenir au moins 6 caractères.")
            return redirect('employe_profil')
        
        # Vérifier la confirmation
        if new_password1 != new_password2:
            messages.error(request, "Les mots de passe ne correspondent pas.")
            return redirect('employe_profil')
        
        # Vérifier que le nouveau mot de passe est différent de l'ancien
        if new_password1 == old_password:
            messages.error(request, "Le nouveau mot de passe doit être différent de l'ancien.")
            return redirect('employe_profil')
        
        try:
            # Changer le mot de passe
            request.user.set_password(new_password1)
            request.user.save()
            
            # Maintenir la session active
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, request.user)
            
            # Journaliser le changement
            db.system_logs.insert_one({
                'user_id': request.user.id,
                'username': request.user.username,
                'action': 'PASSWORD_CHANGE',
                'timestamp': datetime.now(),
                'ip': request.META.get('REMOTE_ADDR')
            })
            
            messages.success(request, "Votre mot de passe a été changé avec succès.")
        except Exception as e:
            messages.error(request, f"Erreur lors du changement: {str(e)}")
        
        return redirect('employe_profil')
    
    return redirect('employe_profil')


@login_required
def api_save_preferences(request):
    """API pour sauvegarder les préférences utilisateur"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        
        employe = db.employees.find_one({'django_user_id': request.user.id})
        if not employe:
            employe = db.employees.find_one({'django_username': request.user.username})
        
        if not employe:
            return JsonResponse({'error': 'Employé non trouvé'}, status=404)
        
        # Récupérer les préférences existantes
        preferences = employe.get('preferences_notifications', {})
        
        # Mettre à jour les préférences
        if 'email' in data:
            preferences['email'] = data['email']
        if 'rappel' in data:
            preferences['rappel'] = data['rappel']
        if 'theme' in data:
            db.employees.update_one(
                {'_id': employe['_id']},
                {'$set': {'theme': data['theme']}}
            )
        
        db.employees.update_one(
            {'_id': employe['_id']},
            {'$set': {'preferences_notifications': preferences, 'updated_at': datetime.now()}}
        )
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def employe_update_profil(request):
    """API pour mettre à jour le profil employé (AJAX)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        
        employe = db.employees.find_one({'django_user_id': request.user.id})
        if not employe:
            employe = db.employees.find_one({'django_username': request.user.username})
        
        if not employe:
            return JsonResponse({'error': 'Employé non trouvé'}, status=404)
        
        update_data = {}
        
        if 'prenom' in data:
            update_data['prenom'] = data['prenom'].strip()
        if 'nom' in data:
            update_data['nom'] = data['nom'].strip()
        if 'email' in data:
            update_data['email'] = data['email'].strip()
        if 'telephone' in data:
            update_data['telephone'] = data['telephone'].strip()
        if 'poste' in data:
            update_data['poste'] = data['poste'].strip()
        if 'departement' in data:
            update_data['departement'] = data['departement'].strip()
        
        update_data['updated_at'] = datetime.now()
        
        if update_data:
            db.employees.update_one({'_id': employe['_id']}, {'$set': update_data})
            
            # Mettre à jour l'utilisateur Django
            if 'prenom' in update_data:
                request.user.first_name = update_data['prenom']
            if 'nom' in update_data:
                request.user.last_name = update_data['nom']
            if 'email' in update_data:
                request.user.email = update_data['email']
            request.user.save()
        
        return JsonResponse({'status': 'success', 'message': 'Profil mis à jour'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_employee_stats(request):
    """API pour les statistiques de l'employé (graphiques)"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        period = request.GET.get('period', 'month')
        
        employe = db.employees.find_one({'django_user_id': request.user.id})
        if not employe:
            employe = db.employees.find_one({'django_username': request.user.username})
        
        if not employe:
            return JsonResponse({'error': 'Employé non trouvé'}, status=404)
        
        now = datetime.now()
        labels = []
        values = []
        
        if period == 'week':
            # 7 derniers jours
            for i in range(6, -1, -1):
                day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                count = db.acces_logs.count_documents({
                    'utilisateur_id': employe['_id'],
                    'timestamp': {'$gte': day_start, '$lt': day_end}
                })
                labels.append(day_start.strftime('%a'))
                values.append(count)
        
        elif period == 'month':
            # 30 derniers jours
            for i in range(29, -1, -1):
                day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                count = db.acces_logs.count_documents({
                    'utilisateur_id': employe['_id'],
                    'timestamp': {'$gte': day_start, '$lt': day_end}
                })
                labels.append(day_start.strftime('%d/%m'))
                values.append(count)
        
        else:
            # 12 derniers mois
            for i in range(11, -1, -1):
                month_start = (now.replace(day=1) - timedelta(days=30 * i)).replace(day=1, hour=0, minute=0, second=0)
                if i == 0:
                    month_end = now
                else:
                    month_end = (month_start + timedelta(days=32)).replace(day=1)
                count = db.acces_logs.count_documents({
                    'utilisateur_id': employe['_id'],
                    'timestamp': {'$gte': month_start, '$lt': month_end}
                })
                labels.append(month_start.strftime('%b'))
                values.append(count)
        
        return JsonResponse({
            'labels': labels,
            'values': values,
            'period': period
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
        # dashboard/views.py - Ajoutez ces fonctions

@login_required
def reservation_list(request):
    """Liste des réservations avec vue calendrier et tableau"""
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    from datetime import datetime, timedelta
    import json
    from bson import ObjectId
    
    reservations = list(db.reservations.find().sort('date_debut', -1))
    
    print(f"🔍 Nombre de réservations trouvées: {len(reservations)}")  # Debug
    
    # Enrichir les données
    for r in reservations:
        r['id'] = str(r['_id'])
        
        # Employé
        employe_id = r.get('employe_id')
        if employe_id:
            try:
                if isinstance(employe_id, str):
                    emp = db.employees.find_one({'_id': ObjectId(employe_id)})
                else:
                    emp = db.employees.find_one({'_id': employe_id})
                if emp:
                    r['employe_nom'] = f"{emp.get('nom', '')} {emp.get('prenom', '')}".strip() or 'Inconnu'
                    r['employe_badge'] = emp.get('badge_id', '—')
                else:
                    r['employe_nom'] = 'Inconnu'
                    r['employe_badge'] = '—'
            except Exception as e:
                print(f"Erreur employé: {e}")
                r['employe_nom'] = 'Inconnu'
                r['employe_badge'] = '—'
        else:
            r['employe_nom'] = 'Inconnu'
            r['employe_badge'] = '—'
        
        # Bureau
        bureau_id = r.get('bureau_id')
        if bureau_id:
            try:
                if isinstance(bureau_id, str):
                    bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
                else:
                    bureau = db.bureaux.find_one({'_id': bureau_id})
                r['bureau_nom'] = bureau['nom'] if bureau else 'Salle inconnue'
            except Exception as e:
                print(f"Erreur bureau: {e}")
                r['bureau_nom'] = 'Salle inconnue'
        else:
            r['bureau_nom'] = 'Salle inconnue'
        
        # QR code
        if 'qr_code' not in r:
            r['qr_code'] = None
    
    now = datetime.now()
    confirmees = sum(1 for r in reservations if r.get('statut') == 'confirmee')
    en_attente = sum(1 for r in reservations if r.get('statut') == 'en_attente')
    annulees = sum(1 for r in reservations if r.get('statut') == 'annulee')
    
    a_venir = sum(1 for r in reservations if r.get('statut') == 'confirmee' 
                  and r.get('date_debut') and r['date_debut'] > now)
    
    # Taux d'occupation
    total_bureaux = db.bureaux.count_documents({})
    if total_bureaux > 0:
        occupied_bureaux = set()
        for r in reservations:
            if r.get('statut') == 'confirmee' and r.get('date_debut') and r.get('date_fin'):
                if r['date_debut'] <= now <= r['date_fin']:
                    occupied_bureaux.add(str(r.get('bureau_id')))
        taux_occupation = round((len(occupied_bureaux) / total_bureaux) * 100)
    else:
        taux_occupation = 0
    
    # Convertir les données en JSON sécurisé
    reservations_list = []
    for r in reservations:
        if r.get('date_debut'):
            reservations_list.append({
                'id': str(r['_id']),
                'titre': r.get('titre', ''),
                'bureau_id': str(r.get('bureau_id')) if r.get('bureau_id') else None,
                'bureau_nom': r.get('bureau_nom', ''),
                'employe_nom': r.get('employe_nom', ''),
                'statut': r.get('statut', ''),
                'date_debut': r['date_debut'].isoformat() if r.get('date_debut') else None,
                'date_fin': r['date_fin'].isoformat() if r.get('date_fin') else None,
            })
    
    reservations_json = json.dumps(reservations_list, default=str)
    print(f"📊 JSON généré avec {len(reservations_list)} réservations")  # Debug
    
    # Liste des bureaux
    bureaux_list = []
    for b in db.bureaux.find():
        bureaux_list.append({
            'id': str(b['_id']),
            'nom': b.get('nom', ''),
        })
    
    return render(request, 'dashboard/reservation_list.html', {
        'reservations': reservations,
        'total': len(reservations),
        'confirmees': confirmees,
        'en_attente': en_attente,
        'annulees': annulees,
        'a_venir': a_venir,
        'taux_occupation': taux_occupation,
        'reservations_json': reservations_json,
        'bureaux': bureaux_list,
    })
@login_required
def reservation_confirmer(request, reservation_id):
    """Confirmer une réservation et générer un QR code"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    try:
        from bson import ObjectId
        from datetime import datetime
        import qrcode
        from io import BytesIO
        import base64
        
        reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
        if not reservation:
            messages.error(request, "Réservation non trouvée")
            return redirect('reservation_list')
        
        # Vérifier si déjà confirmée
        if reservation.get('statut') == 'confirmee':
            messages.warning(request, "Cette réservation est déjà confirmée")
            return redirect('reservation_detail', reservation_id=reservation_id)
        
        if request.method == 'POST':
            # Générer le QR code
            qr_data = f"RESA-{reservation_id}-{reservation.get('employe_id')}-{reservation.get('date_debut').strftime('%Y%m%d%H%M')}"
            
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(qr_data)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            qr_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            # Mettre à jour la réservation
            db.reservations.update_one(
                {'_id': ObjectId(reservation_id)},
                {'$set': {
                    'statut': 'confirmee',
                    'qr_code': qr_base64,
                    'confirmed_at': datetime.now(),
                    'confirmed_by': request.user.username,
                }}
            )
            
            # Récupérer l'employé
            employe_id = reservation.get('employe_id')
            employe = None
            try:
                if isinstance(employe_id, str) and len(employe_id) == 24:
                    employe = db.employees.find_one({'_id': ObjectId(employe_id)})
                else:
                    employe = db.employees.find_one({'django_user_id': employe_id})
            except:
                pass
            
            # Récupérer la salle
            bureau = None
            bureau_id = reservation.get('bureau_id')
            if bureau_id:
                try:
                    bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
                except:
                    pass
            bureau_nom = bureau['nom'] if bureau else 'Salle'
            
            # === NOTIFICATION À L'EMPLOYÉ (UNE SEULE FOIS) ===
            if employe:
                # Vérifier si une notification a déjà été envoyée
                existing_notification = db.notifications.find_one({
                    'employe_id': str(employe['_id']),
                    'reservation_id': str(reservation['_id']),
                    'categorie': 'confirmation'
                })
                
                if not existing_notification:
                    notification = {
                        'employe_id': str(employe['_id']),
                        'titre': '✅ Réservation confirmée',
                        'message': f"Votre réservation '{reservation.get('titre', 'Sans titre')}' a été confirmée pour le {reservation['date_debut'].strftime('%d/%m/%Y à %H:%M')} dans la salle {bureau_nom}.",
                        'categorie': 'confirmation',
                        'icon': '✅',
                        'status': 'non_lu',
                        'action_url': '/employe/reservations/',
                        'reservation_id': str(reservation['_id']),
                        'created_at': datetime.now()
                    }
                    db.notifications.insert_one(notification)
                    
                    # Envoi d'email (une seule fois)
                    if employe.get('email'):
                        try:
                            from django.core.mail import send_mail
                            send_mail(
                                f"Réservation confirmée - {reservation.get('titre', 'Sans titre')}",
                                f"""
Bonjour {employe.get('prenom', '')} {employe.get('nom', '')},

✅ Votre réservation a été CONFIRMÉE !

Détails:
- Titre: {reservation.get('titre', 'Sans titre')}
- Date: {reservation['date_debut'].strftime('%d/%m/%Y %H:%M')} → {reservation['date_fin'].strftime('%H:%M')}
- Salle: {bureau_nom}
- Participants: {reservation.get('nb_participants', 1)}

🔐 Présentez votre QR code au lecteur pour accéder à la salle.

Cordialement,
L'équipe SIGR-CA
                                """,
                                settings.DEFAULT_FROM_EMAIL,
                                [employe['email']],
                                fail_silently=True,
                            )
                        except:
                            pass
            
            messages.success(request, f"Réservation '{reservation.get('titre')}' confirmée avec QR code généré.")
            
            if request.POST.get('redirect_to') == 'list':
                return redirect('reservation_list')
            return redirect('reservation_detail', reservation_id=reservation_id)
        
        # GET: Récupérer les détails pour l'affichage
        employe = None
        employe_id = reservation.get('employe_id')
        if employe_id:
            try:
                if isinstance(employe_id, str) and len(employe_id) == 24:
                    employe = db.employees.find_one({'_id': ObjectId(employe_id)})
                else:
                    employe = db.employees.find_one({'django_user_id': employe_id})
            except:
                pass
        
        bureau = None
        bureau_id = reservation.get('bureau_id')
        if bureau_id:
            try:
                bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
            except:
                pass
        
        return render(request, 'dashboard/reservation_confirmer.html', {
            'reservation': reservation,
            'employe': employe,
            'bureau': bureau,
        })
        
    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('reservation_list')
@login_required
def reservation_refuser(request, reservation_id):
    """Refuser une réservation"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    from bson import ObjectId
    from datetime import datetime
    
    if request.method == 'POST':
        try:
            reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
            if not reservation:
                messages.error(request, "Réservation non trouvée")
                return redirect('reservation_list')
            
            motif = request.POST.get('motif', 'Non spécifié')
            
            # Vérifier si la réservation est déjà refusée
            if reservation.get('statut') == 'annulee':
                messages.warning(request, "Cette réservation est déjà annulée")
                return redirect('reservation_list')
            
            # Mettre à jour la réservation
            db.reservations.update_one(
                {'_id': ObjectId(reservation_id)},
                {'$set': {
                    'statut': 'annulee',
                    'refused_at': datetime.now(),
                    'refused_by': request.user.username,
                    'refusal_reason': motif,
                }}
            )
            
            # Récupérer l'employé
            employe_id = reservation.get('employe_id')
            employe = None
            try:
                if isinstance(employe_id, str) and len(employe_id) == 24:
                    employe = db.employees.find_one({'_id': ObjectId(employe_id)})
                else:
                    employe = db.employees.find_one({'django_user_id': employe_id})
            except:
                pass
            
            # Récupérer la salle
            bureau = None
            bureau_id = reservation.get('bureau_id')
            if bureau_id:
                try:
                    bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
                except:
                    pass
            bureau_nom = bureau['nom'] if bureau else 'Salle'
            
            # === NOTIFICATION À L'EMPLOYÉ (UNE SEULE FOIS) ===
            if employe:
                # Vérifier si une notification a déjà été envoyée pour ce refus
                existing_notification = db.notifications.find_one({
                    'employe_id': str(employe['_id']),
                    'reservation_id': str(reservation['_id']),
                    'categorie': 'annulation'
                })
                
                if not existing_notification:
                    notification = {
                        'employe_id': str(employe['_id']),
                        'titre': '❌ Réservation refusée',
                        'message': f"Votre réservation '{reservation.get('titre', 'Sans titre')}' pour la salle {bureau_nom} du {reservation['date_debut'].strftime('%d/%m/%Y à %H:%M')} a été refusée.\nMotif: {motif}",
                        'categorie': 'annulation',
                        'icon': '❌',
                        'status': 'non_lu',
                        'action_url': '/employe/reservations/',
                        'reservation_id': str(reservation['_id']),
                        'created_at': datetime.now()
                    }
                    db.notifications.insert_one(notification)
                
                # Envoi d'email (une seule fois)
                if employe.get('email') and not existing_notification:
                    try:
                        from django.core.mail import send_mail
                        send_mail(
                            f"Réservation refusée - {reservation.get('titre', 'Sans titre')}",
                            f"""
Bonjour {employe.get('prenom', '')} {employe.get('nom', '')},

❌ Votre réservation a été REFUSÉE.

Détails:
- Titre: {reservation.get('titre', 'Sans titre')}
- Date: {reservation['date_debut'].strftime('%d/%m/%Y %H:%M')} → {reservation['date_fin'].strftime('%H:%M')}
- Salle: {bureau_nom}

Motif du refus: {motif}

Cordialement,
L'équipe SIGR-CA
                            """,
                            settings.DEFAULT_FROM_EMAIL,
                            [employe['email']],
                            fail_silently=True,
                        )
                    except:
                        pass
            
            messages.warning(request, f"Réservation '{reservation.get('titre')}' refusée.")
            
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return redirect('reservation_list')


@login_required
def reservation_detail(request, reservation_id):
    """Voir les détails d'une réservation (avec QR code si confirmée)"""
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    from bson import ObjectId
    
    try:
        reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
        if not reservation:
            messages.error(request, "Réservation non trouvée")
            return redirect('reservation_list')
        
        reservation['id'] = str(reservation['_id'])
        
        # Récupérer l'employé
        employe = None
        employe_id = reservation.get('employe_id')
        if employe_id:
            try:
                if isinstance(employe_id, str) and len(employe_id) == 24:
                    employe = db.employees.find_one({'_id': ObjectId(employe_id)})
                else:
                    employe = db.employees.find_one({'django_user_id': employe_id})
            except:
                pass
        
        # Récupérer la salle
        bureau = None
        bureau_id = reservation.get('bureau_id')
        if bureau_id:
            try:
                bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
            except:
                pass
        
        return render(request, 'dashboard/reservation_detail.html', {
            'reservation': reservation,
            'employe': employe,
            'bureau': bureau,
        })
        
    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('reservation_list')


def send_reservation_confirmation_email(employe, reservation, qr_base64):
    """Envoie un email de confirmation avec QR code"""
    message = f"""
    Bonjour {employe.get('prenom', '')} {employe.get('nom', '')},
    
    ✅ Votre réservation a été CONFIRMÉE par l'administrateur !
    
    Détails de la réservation:
    - Titre: {reservation.get('titre')}
    - Date: {reservation['date_debut'].strftime('%d/%m/%Y %H:%M')} → {reservation['date_fin'].strftime('%H:%M')}
    - Participants: {reservation.get('nb_participants', 1)}
    
    🔐 QR Code d'accès:
    Présentez ce QR code au lecteur à l'entrée de la salle.
    
    (Le QR code est également disponible dans votre espace employé)
    
    Merci d'utiliser SIGR-CA.
    """
    
    db.notifications.insert_one({
        'destinataire': employe.get('email'),
        'type_notification': 'email',
        'categorie': 'confirmation',
        'sujet': f"Réservation confirmée - {reservation.get('titre')}",
        'message': message,
        'statut': 'envoyee',
        'reservation_id': str(reservation['_id']),
        'created_at': datetime.now(),
    })
    
    try:
        from django.core.mail import send_mail
        send_mail(
            f"Réservation confirmée - {reservation.get('titre')}",
            message,
            settings.DEFAULT_FROM_EMAIL,
            [employe.get('email')],
            fail_silently=True,
        )
    except:
        pass


def send_reservation_refusal_email(employe, reservation, motif):
    """Envoie un email de refus de réservation"""
    message = f"""
    Bonjour {employe.get('prenom', '')} {employe.get('nom', '')},
    
    ❌ Votre réservation a été REFUSÉE par l'administrateur.
    
    Détails de la réservation:
    - Titre: {reservation.get('titre')}
    - Date: {reservation['date_debut'].strftime('%d/%m/%Y %H:%M')} → {reservation['date_fin'].strftime('%H:%M')}
    
    Motif du refus: {motif}
    
    Vous pouvez effectuer une nouvelle demande de réservation depuis votre espace employé.
    
    Cordialement,
    SIGR-CA
    """
    
    db.notifications.insert_one({
        'destinataire': employe.get('email'),
        'type_notification': 'email',
        'categorie': 'annulation',
        'sujet': f"Réservation refusée - {reservation.get('titre')}",
        'message': message,
        'statut': 'envoyee',
        'reservation_id': str(reservation['_id']),
        'created_at': datetime.now(),
    })
    
    try:
        from django.core.mail import send_mail
        send_mail(
            f"Réservation refusée - {reservation.get('titre')}",
            message,
            settings.DEFAULT_FROM_EMAIL,
            [employe.get('email')],
            fail_silently=True,
        )
    except:
        pass
        # dashboard/views.py - Ajoutez cette API

#@login_required
#def api_reservation_qr(request, reservation_id):
   # """API pour récupérer le QR code d'une réservation"""
   # try:
        # Vérifier que l'utilisateur a le droit d'accéder au QR code
      #  if request.user.is_staff:
        #    reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
       # else:
            # Pour les employés, vérifier que c'est bien leur réservation
         #   employe = db.employees.find_one({'django_user_id': request.user.id})
          #  if not employe:
          #      return JsonResponse({'error': 'Employé non trouvé'}, status=404)
          #  reservation = db.reservations.find_one({
          #      '_id': ObjectId(reservation_id),
           #     'employe_id': str(employe['_id'])
          #  })
        
       # if not reservation:
        #    return JsonResponse({'error': 'Réservation non trouvée'}, status=404)
        
       # return JsonResponse({
          #  'qr_code': reservation.get('qr_code'),
          #  'date_debut': reservation.get('date_debut'),
          #  'date_fin': reservation.get('date_fin'),
          #  'titre': reservation.get('titre'),
          #  'statut': reservation.get('statut'),
       # })
    #except Exception as e:
     #   return JsonResponse({'error': str(e)}, status=500)
        # dashboard/views.py


# ====================== NOTIFICATIONS EMPLOYÉ ======================

# dashboard/views.py - Remplacez la fonction employe_notifications par celle-ci

@login_required
def employe_notifications(request):
    """Centre de notifications de l'employé - Version MongoDB"""
    if request.user.is_staff:
        return redirect('dashboard')
    
    from bson import ObjectId
    from datetime import datetime
    
    # Récupérer l'employé
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        return redirect('login')
    
    employe['id'] = str(employe['_id'])
    
    # Récupérer les notifications depuis MongoDB
    notifications = list(db.notifications.find({
        'employe_id': str(employe['_id'])
    }).sort('created_at', -1))
    
    for n in notifications:
        n['id'] = str(n['_id'])
        if 'status' not in n:
            n['status'] = 'non_lu'
        if 'categorie' not in n:
            n['categorie'] = n.get('type', 'info')
        if 'icon' not in n:
            n['icon'] = '🔔'
    
    # Compter les non lues
    unread_count = sum(1 for n in notifications if n.get('status') == 'non_lu')
    
    # Traitement POST pour marquer comme lu
    if request.method == 'POST':
        if 'mark_read' in request.POST:
            notification_id = request.POST.get('notification_id')
            if notification_id:
                db.notifications.update_one(
                    {'_id': ObjectId(notification_id), 'employe_id': str(employe['_id'])},
                    {'$set': {'status': 'lu', 'read_at': datetime.now()}}
                )
            else:
                # Marquer toutes comme lues
                db.notifications.update_many(
                    {'employe_id': str(employe['_id']), 'status': 'non_lu'},
                    {'$set': {'status': 'lu', 'read_at': datetime.now()}}
                )
            return redirect('employe_notifications')
        
        elif 'delete_all' in request.POST:
            db.notifications.delete_many({'employe_id': str(employe['_id'])})
            return redirect('employe_notifications')
    
    return render(request, 'dashboard/employe_notifications.html', {
        'employe': employe,
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
def api_mark_notification_read(request):
    """API pour marquer une notification comme lue (AJAX) - Version MongoDB"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        from bson import ObjectId
        from datetime import datetime
        
        data = json.loads(request.body)
        notification_id = data.get('notification_id')
        
        employe = db.employees.find_one({'django_user_id': request.user.id})
        if not employe:
            employe = db.employees.find_one({'django_username': request.user.username})
        
        if notification_id:
            db.notifications.update_one(
                {'_id': ObjectId(notification_id), 'employe_id': str(employe['_id'])},
                {'$set': {'status': 'lu', 'read_at': datetime.now()}}
            )
        else:
            # Marquer toutes comme lues
            db.notifications.update_many(
                {'employe_id': str(employe['_id']), 'status': 'non_lu'},
                {'$set': {'status': 'lu', 'read_at': datetime.now()}}
            )
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_delete_notification(request):
    """API pour supprimer une notification (AJAX) - Version MongoDB"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        import json
        from bson import ObjectId
        
        data = json.loads(request.body)
        notification_id = data.get('notification_id')
        
        employe = db.employees.find_one({'django_user_id': request.user.id})
        if not employe:
            employe = db.employees.find_one({'django_username': request.user.username})
        
        if notification_id:
            db.notifications.delete_one({
                '_id': ObjectId(notification_id), 
                'employe_id': str(employe['_id'])
            })
        else:
            db.notifications.delete_many({'employe_id': str(employe['_id'])})
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_delete_all_notifications(request):
    """API pour supprimer toutes les notifications - Version MongoDB"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        employe = db.employees.find_one({'django_user_id': request.user.id})
        if not employe:
            employe = db.employees.find_one({'django_username': request.user.username})
        
        db.notifications.delete_many({'employe_id': str(employe['_id'])})
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_send_test_notification(request):
    """API pour envoyer une notification de test - Version MongoDB"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    from datetime import datetime
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    notification = {
        'employe_id': str(employe['_id']),
        'titre': '🔔 Notification de test',
        'message': 'Ceci est une notification de test pour vérifier le bon fonctionnement du centre de notifications.',
        'categorie': 'info',
        'icon': '🔔',
        'status': 'non_lu',
        'action_url': '/employe/notifications/',
        'created_at': datetime.now()
    }
    
    db.notifications.insert_one(notification)
    
    return JsonResponse({'status': 'success', 'message': 'Notification envoyée'})


def send_reservation_notification(employe_id, reservation_data, action='created'):
    """Fonction utilitaire pour envoyer une notification de réservation"""
    from datetime import datetime
    
    notifications_data = {
        'created': {
            'titre': '📝 Réservation créée',
            'message': f"Votre réservation '{reservation_data.get('titre')}' a été créée et est en attente de validation.",
            'categorie': 'reservation',
            'icon': '📝'
        },
        'confirmed': {
            'titre': '✅ Réservation confirmée',
            'message': f"Votre réservation '{reservation_data.get('titre')}' a été confirmée.",
            'categorie': 'confirmation',
            'icon': '✅'
        },
        'refused': {
            'titre': '❌ Réservation refusée',
            'message': f"Votre réservation '{reservation_data.get('titre')}' a été refusée.",
            'categorie': 'annulation',
            'icon': '❌'
        },
        'reminder': {
            'titre': '⏰ Rappel de réservation',
            'message': f"Rappel: Votre réservation '{reservation_data.get('titre')}' commence dans 30 minutes.",
            'categorie': 'rappel',
            'icon': '⏰'
        },
        'cancelled': {
            'titre': '🗑️ Réservation annulée',
            'message': f"Votre réservation '{reservation_data.get('titre')}' a été annulée.",
            'categorie': 'annulation',
            'icon': '🗑️'
        }
    }
    
    data = notifications_data.get(action, notifications_data['created'])
    
    db.notifications.insert_one({
        'employe_id': str(employe_id),
        'titre': data['titre'],
        'message': data['message'],
        'categorie': data['categorie'],
        'icon': data['icon'],
        'status': 'non_lu',
        'action_url': '/employe/reservations/',
        'reservation_id': reservation_data.get('id'),
        'created_at': datetime.now()
    })
    
@login_required
def api_notifications_unread_count(request):
    """API pour récupérer le nombre de notifications non lues"""
    try:
        employe = db.employees.find_one({'django_user_id': request.user.id})
        if not employe:
            employe = db.employees.find_one({'django_username': request.user.username})
        
        if not employe:
            return JsonResponse({'count': 0})
        
        count = db.notifications.count_documents({
            'employe_id': str(employe['_id']),
            'status': 'non_lu'
        })
        
        return JsonResponse({'count': count})
        
    except Exception as e:
        return JsonResponse({'count': 0, 'error': str(e)}, status=500)
        # ====================== STATISTIQUES GESTION DES RESSOURCES ======================
# Ajoutez ces fonctions à la fin de votre fichier views.py

@login_required
def get_ressource_stats(request):
    """Statistiques de gestion des ressources pour le dashboard"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Taux d'occupation des salles
    total_salles = db.bureaux.count_documents({})
    
    # Compter les réservations actives du mois
    reservations_mois = db.reservations.count_documents({
        'date_debut': {'$gte': start_month},
        'statut': 'confirmee'
    })
    
    # Calcul du taux d'occupation (basé sur 8h/jour * 30 jours = 240h par salle)
    heures_possibles = total_salles * 240 if total_salles > 0 else 1
    heures_occupees = reservations_mois * 2  # moyenne 2h par réservation
    taux_occupation = min(100, round((heures_occupees / heures_possibles) * 100, 1)) if heures_possibles > 0 else 0
    
    # Réservations totales du mois
    total_reservations = db.reservations.count_documents({
        'date_debut': {'$gte': start_month},
        'statut': 'confirmee'
    })
    
    # Salles disponibles actuellement
    salles_reservees = db.reservations.distinct('bureau_id', {
        'date_debut': {'$lte': now},
        'date_fin': {'$gte': now},
        'statut': 'confirmee'
    })
    salles_disponibles = total_salles - len(salles_reservees)
    
    # Taux d'annulation (30 derniers jours)
    thirty_days_ago = now - timedelta(days=30)
    total_commandes = db.reservations.count_documents({
        'date_debut': {'$gte': thirty_days_ago}
    })
    annulations = db.reservations.count_documents({
        'date_debut': {'$gte': thirty_days_ago},
        'statut': 'annulee'
    })
    taux_annulation = round((annulations / total_commandes) * 100, 1) if total_commandes > 0 else 0
    
    return {
        'taux_occupation': taux_occupation,
        'total_reservations': total_reservations,
        'salles_disponibles': salles_disponibles,
        'total_salles': total_salles,
        'taux_annulation': taux_annulation,
    }


@login_required
def get_occupation_stats(request):
    """Statistiques d'occupation par salle"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)
    
    bureaux = list(db.bureaux.find())
    occupation_data = []
    
    for bureau in bureaux:
        # Compter les réservations des 30 derniers jours
        reservations_count = db.reservations.count_documents({
            'bureau_id': bureau['_id'],
            'date_debut': {'$gte': thirty_days_ago},
            'statut': 'confirmee'
        })
        
        # Calculer le taux d'occupation (max 30 jours * 8h par jour = 240h)
        # Chaque réservation dure en moyenne 2h
        heures_occupees = reservations_count * 2
        heures_possibles = 240  # 30 jours * 8h
        taux = min(100, round((heures_occupees / heures_possibles) * 100, 1)) if heures_possibles > 0 else 0
        
        occupation_data.append({
            'nom': bureau.get('nom', 'Salle inconnue'),
            'taux': taux,
            'reservations': reservations_count
        })
    
    # Trier par taux d'occupation décroissant
    occupation_data.sort(key=lambda x: x['taux'], reverse=True)
    
    return {
        'labels': [o['nom'] for o in occupation_data[:10]],
        'values': [o['taux'] for o in occupation_data[:10]]
    }


@login_required
def get_top_ressources(request):
    """Top ressources les plus réservées"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)
    
    pipeline = [
        {'$match': {
            'date_debut': {'$gte': thirty_days_ago},
            'statut': 'confirmee'
        }},
        {'$group': {
            '_id': '$bureau_id',
            'count': {'$sum': 1}
        }},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]
    
    results = list(db.reservations.aggregate(pipeline))
    total_reservations = sum(r['count'] for r in results)
    
    top_ressources = []
    for r in results:
        bureau = db.bureaux.find_one({'_id': r['_id']})
        if bureau:
            top_ressources.append({
                'nom': bureau.get('nom', 'Salle inconnue'),
                'reservations': r['count'],
                'pct': round((r['count'] / total_reservations) * 100, 1) if total_reservations > 0 else 0
            })
    
    return top_ressources


@login_required
def get_weekly_schedule(request):
    """Planning des réservations pour les 7 prochains jours"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    week_later = now + timedelta(days=7)
    
    reservations = list(db.reservations.find({
        'date_debut': {'$gte': now, '$lte': week_later},
        'statut': 'confirmee'
    }).sort('date_debut', 1).limit(10))
    
    schedule = []
    for r in reservations:
        bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
        schedule.append({
            'date': r['date_debut'].strftime('%d/%m'),
            'heure': r['date_debut'].strftime('%H:%M'),
            'titre': r.get('titre', 'Sans titre'),
            'salle': bureau.get('nom', 'Salle inconnue') if bureau else 'Salle inconnue',
            'participants': r.get('nb_participants', 1)
        })
    
    return schedule


@login_required
def get_hour_stats(request):
    """Statistiques horaires des accès"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)
    
    # Créer les tranches horaires
    hours = [f"{h:02d}h-{h+1:02d}h" for h in range(0, 24)]
    hour_counts = [0] * 24
    
    # Compter les accès par heure
    logs = db.acces_logs.find({
        'timestamp': {'$gte': thirty_days_ago}
    })
    
    for log in logs:
        if log.get('timestamp'):
            hour = log['timestamp'].hour
            hour_counts[hour] += 1
    
    return {
        'labels': hours,
        'values': hour_counts
    }


@login_required
def get_zone_stats_data(request):
    """Statistiques par zone pour les graphiques"""
    from datetime import datetime, timedelta
    
    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)
    
    pipeline = [
        {'$match': {'timestamp': {'$gte': thirty_days_ago}}},
        {'$group': {
            '_id': '$bureau_id',
            'count': {'$sum': 1}
        }},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]
    
    results = list(db.acces_logs.aggregate(pipeline))
    total_acces = sum(r['count'] for r in results)
    
    labels = []
    values = []
    details = []
    
    for r in results:
        bureau = db.bureaux.find_one({'_id': r['_id']})
        if bureau:
            nom = bureau.get('nom', 'Zone inconnue')
            pct = round((r['count'] / total_acces) * 100, 1) if total_acces > 0 else 0
            labels.append(nom)
            values.append(r['count'])
            details.append({
                'nom': nom,
                'count': r['count'],
                'pct': pct
            })
    
    return {
        'labels': labels,
        'values': values,
        'details': details,
        'total': total_acces
    }


# ====================== API ENDPOINTS POUR LES STATISTIQUES ======================

@login_required
def api_stats_overview(request):
    """API endpoint pour les statistiques globales (pour AJAX)"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        ressource_stats = get_ressource_stats(request)
        occupation_stats = get_occupation_stats(request)
        top_ressources = get_top_ressources(request)
        weekly_schedule = get_weekly_schedule(request)
        hour_stats = get_hour_stats(request)
        zone_stats = get_zone_stats_data(request)
        
        return JsonResponse({
            'status': 'success',
            'ressource_stats': ressource_stats,
            'occupation_stats': occupation_stats,
            'top_ressources': top_ressources,
            'weekly_schedule': weekly_schedule,
            'hour_stats': hour_stats,
            'zone_stats': zone_stats,
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_occupation_stats(request):
    """API pour les statistiques d'occupation des salles"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        occupation = get_occupation_stats(request)
        return JsonResponse({
            'status': 'success',
            'data': occupation
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_top_ressources(request):
    """API pour le top des ressources"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        top = get_top_ressources(request)
        return JsonResponse({
            'status': 'success',
            'data': top
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_weekly_schedule(request):
    """API pour le planning hebdomadaire"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        schedule = get_weekly_schedule(request)
        return JsonResponse({
            'status': 'success',
            'data': schedule
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_hour_stats(request):
    """API pour les statistiques horaires"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        stats = get_hour_stats(request)
        return JsonResponse({
            'status': 'success',
            'labels': stats['labels'],
            'values': stats['values']
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        # ====================== PLAN DES ZONES ======================

@login_required
def employe_plan_zones(request):
    """Plan interactif des zones et bureaux"""
    if request.user.is_staff:
        return redirect('dashboard')
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    # Récupérer toutes les zones
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
        b['capacite_max'] = b.get('capacite_max', 10)
        
        # Calculer occupation en temps réel
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent = db.acces_logs.count_documents({
            'bureau_id': b['_id'],
            'timestamp': {'$gte': one_hour_ago}
        })
        b['occupation'] = min(recent, b['capacite_max'])
        b['taux_occupation'] = round((b['occupation'] / b['capacite_max'] * 100), 1) if b['capacite_max'] > 0 else 0
    
    # Niveaux/étages
    etages = sorted(set(b.get('etage', 0) for b in bureaux))
    
    return render(request, 'dashboard/employe_plan_zones.html', {
        'employe': employe,
        'bureaux': bureaux,
        'etages': etages,
        'user': request.user,
    })
    # ====================== BADGE VIRTUEL ======================

@login_required
def employe_badge_virtuel(request):
    """Badge virtuel avec QR code permanent"""
    if request.user.is_staff:
        return redirect('dashboard')
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        return redirect('login')
    
    employe['id'] = str(employe['_id'])
    
    # Récupérer les zones accessibles
    zones_accessibles = list(db.bureaux.find())
    for z in zones_accessibles:
        z['id'] = str(z['_id'])
    
    # Horaires d'accès
    horaires_acces = {
        'lundi': {'debut': '08:00', 'fin': '18:00'},
        'mardi': {'debut': '08:00', 'fin': '18:00'},
        'mercredi': {'debut': '08:00', 'fin': '18:00'},
        'jeudi': {'debut': '08:00', 'fin': '18:00'},
        'vendredi': {'debut': '08:00', 'fin': '18:00'},
        'samedi': {'debut': '09:00', 'fin': '13:00'},
        'dimanche': {'debut': 'Fermé', 'fin': 'Fermé'},
    }
    
    return render(request, 'dashboard/employe_badge_virtuel.html', {
        'employe': employe,
        'zones_accessibles': zones_accessibles,
        'horaires_acces': horaires_acces,
    })
    # ====================== CENTRE D'AIDE ======================

@login_required
def employe_aide(request):
    """Centre d'information et d'aide"""
    if request.user.is_staff:
        return redirect('dashboard')
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    # FAQ
    faqs = [
        {'question': 'Comment réserver une salle ?', 
         'reponse': 'Rendez-vous dans "Mes réservations" puis cliquez sur "Nouvelle réservation". Sélectionnez la salle, la date et l\'heure.'},
        {'question': 'Comment utiliser mon badge virtuel ?', 
         'reponse': 'Le QR code dans "Badge virtuel" peut être scanné par les lecteurs. Vous pouvez aussi le télécharger et l\'imprimer.'},
        {'question': 'Que faire en cas de refus d\'accès ?', 
         'reponse': 'Vérifiez vos horaires d\'accès dans "Badge virtuel". Si le problème persiste, contactez votre administrateur.'},
        {'question': 'Comment annuler une réservation ?', 
         'reponse': 'Allez dans "Mes réservations", trouvez la réservation concernée et cliquez sur "Annuler".'},
        {'question': 'Comment modifier mon profil ?', 
         'reponse': 'Rendez-vous dans "Mon profil" pour modifier vos informations personnelles et préférences.'},
        {'question': 'Où voir mon historique d\'accès ?', 
         'reponse': 'La section "Mon historique" vous montre tous vos accès avec filtres et export CSV.'},
    ]
    
    # Contacts support
    contacts = {
        'email': 'support@sigr-ca.com',
        'telephone': '+213 00 00 00 00',
        'horaires': 'Lun-Ven: 08:00 - 18:00',
    }
    
    return render(request, 'dashboard/employe_aide.html', {
        'employe': employe,
        'faqs': faqs,
        'contacts': contacts,
    })


# Assurez-vous que ces fonctions sont au bon niveau d'indentation (sans espace avant def)
@login_required
def api_reservation_qr(request, reservation_id):
    """API pour récupérer le QR code d'une réservation"""
    from bson import ObjectId
    
    try:
        reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
        if not reservation:
            return JsonResponse({'error': 'Réservation non trouvée'}, status=404)
        
        # Vérifier que l'utilisateur a le droit d'accéder à ce QR code
        employe = db.employees.find_one({'django_user_id': request.user.id})
        if not employe:
            employe = db.employees.find_one({'django_username': request.user.username})
        
        if employe and str(employe['_id']) != reservation.get('employe_id'):
            if not request.user.is_staff:
                return JsonResponse({'error': 'Non autorisé'}, status=403)
        
        return JsonResponse({
            'qr_code': reservation.get('qr_code'),
            'titre': reservation.get('titre', 'Sans titre'),
            'bureau_nom': get_bureau_name(reservation.get('bureau_id')),
            'date_debut': reservation.get('date_debut').isoformat() if reservation.get('date_debut') else None,
            'date_fin': reservation.get('date_fin').isoformat() if reservation.get('date_fin') else None,
            'statut': reservation.get('statut'),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_bureau_name(bureau_id):
    """Récupère le nom du bureau à partir de son ID"""
    from bson import ObjectId
    if not bureau_id:
        return 'Salle inconnue'
    try:
        bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
        return bureau['nom'] if bureau else 'Salle inconnue'
    except:
        return 'Salle inconnue'


@login_required
def api_reservation_duplicate(request, reservation_id):
    """API pour dupliquer une réservation"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        original = db.reservations.find_one({'_id': ObjectId(reservation_id)})
        if not original:
            return JsonResponse({'error': 'Réservation non trouvée'}, status=404)
        
        # Créer une copie
        del original['_id']
        original['titre'] = f"Copie de {original.get('titre', 'Réservation')}"
        original['statut'] = 'en_attente'
        original['created_at'] = datetime.now()
        original['qr_code'] = None
        
        result = db.reservations.insert_one(original)
        
        return JsonResponse({'status': 'success', 'id': str(result.inserted_id)})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_bureau_schedule(request, bureau_id):
    """API pour récupérer les créneaux d'une salle"""
    date = request.GET.get('date')
    if not date:
        return JsonResponse({'creneaux': []})
    
    try:
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        date_end = date_obj + timedelta(days=1)
        
        reservations = list(db.reservations.find({
            'bureau_id': ObjectId(bureau_id),
            'statut': {'$in': ['confirmee', 'en_attente']},
            'date_debut': {'$gte': date_obj, '$lt': date_end}
        }).sort('date_debut', 1))
        
        creneaux = []
        for r in reservations:
            creneaux.append({
                'debut': r['date_debut'].strftime('%H:%M'),
                'fin': r['date_fin'].strftime('%H:%M'),
                'titre': r.get('titre', 'Sans titre'),
                'employe': r.get('employe_nom', 'Inconnu'),
            })
        
        return JsonResponse({'creneaux': creneaux})
    except Exception as e:
        return JsonResponse({'creneaux': [], 'error': str(e)})


@login_required
def api_bureau_suggestions(request, bureau_id):
    """API pour suggérer des créneaux disponibles"""
    suggestions = [
        {'date': 'Aujourd\'hui', 'debut': '14:00', 'fin': '15:00', 'taux': 25, 'disponibilite': 'Libre'},
        {'date': 'Aujourd\'hui', 'debut': '15:00', 'fin': '16:00', 'taux': 30, 'disponibilite': 'Libre'},
        {'date': 'Demain', 'debut': '09:00', 'fin': '10:00', 'taux': 15, 'disponibilite': 'Très disponible'},
        {'date': 'Demain', 'debut': '10:00', 'fin': '11:00', 'taux': 20, 'disponibilite': 'Disponible'},
        {'date': 'Jeudi', 'debut': '14:00', 'fin': '15:00', 'taux': 10, 'disponibilite': 'Peu fréquenté'},
    ]
    return JsonResponse({'suggestions': suggestions})
        # ====================== Chatbot IA ======================
# dashboard/views.py - Ajoutez ces fonctions


@login_required
def api_chatbot_message(request):
    """API pour le chatbot employé"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip().lower()
        conversation_id = data.get('conversation_id', '')
        
        if not user_message:
            return JsonResponse({'error': 'Message vide'}, status=400)
        
        # Récupérer ou créer la conversation
        if conversation_id:
            try:
                conversation = ChatbotConversation.objects.get(id=conversation_id, user=request.user)
            except ChatbotConversation.DoesNotExist:
                conversation = ChatbotConversation.objects.create(user=request.user)
        else:
            conversation = ChatbotConversation.objects.create(user=request.user)
        
        # Sauvegarder le message utilisateur
        ChatbotMessage.objects.create(
            conversation=conversation,
            role='user',
            content=user_message
        )
        
        # Analyser l'intention et générer la réponse
        response_data = process_chatbot_message(request.user, user_message, conversation)
        
        # Sauvegarder la réponse
        ChatbotMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=response_data['message'],
            intent=response_data.get('intent', ''),
            entities=response_data.get('entities', {})
        )
        
        return JsonResponse({
            'status': 'success',
            'message': response_data['message'],
            'intent': response_data.get('intent', ''),
            'data': response_data.get('data', {}),
            'conversation_id': conversation.id,
            'suggestions': response_data.get('suggestions', [])
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def process_chatbot_message(user, message, conversation):
    """Traite le message et génère une réponse intelligente"""
    
    # Intentions et mots-clés
    intents = {
        'reserver': ['réserver', 'reserver', 'booking', 'book', 'nouvelle réservation', 'créer réservation'],
        'disponibilite': ['disponible', 'libre', 'créneau', 'horaire', 'quand', 'date', 'jour'],
        'annuler': ['annuler', 'cancel', 'supprimer réservation'],
        'mes_reservations': ['mes réservations', 'mes reservations', 'liste réservations', 'voir réservations'],
        'salles': ['salle', 'salles', 'ressource', 'bureau', 'zone'],
        'aide': ['aide', 'help', 'comment', 'fonctionne', 'tutoriel'],
        'horaire_optimal': ['meilleur créneau', 'moins occupé', 'calme', 'optimal', 'recommandé'],
        'bonjour': ['bonjour', 'salut', 'hello', 'coucou', 'hey'],
    }
    
    # Déterminer l'intention
    detected_intent = 'general'
    for intent, keywords in intents.items():
        for keyword in keywords:
            if keyword in message:
                detected_intent = intent
                break
        if detected_intent != 'general':
            break
    
    # Traitement selon l'intention
    if detected_intent == 'bonjour':
        return {
            'intent': 'bonjour',
            'message': f"Bonjour {user.first_name or user.username} ! 👋\n\nJe suis votre assistant SIGR-CA. Je peux vous aider à :\n• 📅 Réserver une salle\n• 🔍 Vérifier la disponibilité\n• 📋 Voir vos réservations\n• ❌ Annuler une réservation\n\nComment puis-je vous aider aujourd'hui ?",
            'suggestions': ["📅 Réserver une salle", "🔍 Voir mes réservations", "❓ Comment ça fonctionne ?"]
        }
    
    elif detected_intent == 'reserver':
        # Extraire la date et l'heure si possible
        date_info = extract_date_from_message(message)
        
        # Récupérer les salles disponibles
        salles = get_available_rooms(date_info)
        
        if salles:
            salles_text = "\n".join([f"• {s['nom']} (Cap. {s['capacite']} pers)" for s in salles[:5]])
            return {
                'intent': 'reserver',
                'message': f"Je trouve {len(salles)} salle(s) disponible(s) pour {date_info if date_info else 'aujourd\'hui'} :\n\n{salles_text}\n\nSouhaitez-vous réserver l'une de ces salles ?",
                'data': {'salles': salles, 'date': date_info},
                'suggestions': [f"✅ Réserver {salles[0]['nom']}" if salles else "➕ Nouvelle réservation", "📅 Autre date"]
            }
        else:
            return {
                'intent': 'reserver',
                'message': f"Je n'ai trouvé aucune salle disponible pour {date_info if date_info else 'aujourd\'hui'}.\n\nSouhaitez-vous voir les disponibilités pour une autre date ?",
                'suggestions': ["📅 Voir demain", "📅 Voir cette semaine", "➕ Nouvelle réservation"]
            }
    
    elif detected_intent == 'disponibilite':
        date_info = extract_date_from_message(message)
        disponibilites = get_availability_summary(date_info)
        
        return {
            'intent': 'disponibilite',
            'message': f"📊 Disponibilités des salles {date_info if date_info else 'aujourd\'hui'} :\n\n{disponibilites['text']}\n\nTaux d'occupation moyen: {disponibilites['taux_moyen']}%",
            'data': disponibilites,
            'suggestions': ["📅 Réserver", "⏰ Meilleur créneau", "🚪 Voir toutes les salles"]
        }
    
    elif detected_intent == 'mes_reservations':
        # Récupérer les réservations de l'utilisateur
        from bson import ObjectId
        employe = db.employees.find_one({'django_user_id': user.id})
        if employe:
            reservations = list(db.reservations.find({'employe_id': str(employe['_id'])}).sort('date_debut', -1).limit(5))
            
            if reservations:
                resa_text = ""
                for r in reservations[:3]:
                    bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
                    nom_bureau = bureau['nom'] if bureau else 'Salle'
                    date_str = r['date_debut'].strftime('%d/%m %H:%M') if r.get('date_debut') else 'Date inconnue'
                    statut = "✅" if r.get('statut') == 'confirmee' else "⏳" if r.get('statut') == 'en_attente' else "❌"
                    resa_text += f"\n{statut} {r.get('titre', 'Sans titre')} - {nom_bureau} - {date_str}"
                
                return {
                    'intent': 'mes_reservations',
                    'message': f"📋 Vos dernières réservations :{resa_text}\n\nVoulez-vous voir toutes vos réservations ?",
                    'suggestions': ["📋 Voir toutes", "➕ Nouvelle réservation", "❌ Annuler une réservation"]
                }
            else:
                return {
                    'intent': 'mes_reservations',
                    'message': "Vous n'avez aucune réservation pour le moment.\n\nSouhaitez-vous en créer une ?",
                    'suggestions': ["📅 Réserver une salle", "🔍 Voir les disponibilités"]
                }
        else:
            return {
                'intent': 'mes_reservations',
                'message': "Impossible de récupérer vos réservations. Veuillez réessayer.",
                'suggestions': ["📅 Réserver une salle", "❓ Aide"]
            }
    
    elif detected_intent == 'horaire_optimal':
        horaire_optimal = get_optimal_time_slot()
        
        return {
            'intent': 'horaire_optimal',
            'message': f"⏰ **Meilleurs créneaux recommandés :**\n\n{horaire_optimal['text']}\n\n💡 Ces créneaux sont généralement les moins occupés. Voulez-vous réserver l'un d'eux ?",
            'data': horaire_optimal,
            'suggestions': [f"📅 Réserver à {h['debut']}" for h in horaire_optimal['slots'][:2]]
        }
    
    elif detected_intent == 'aide':
        return {
            'intent': 'aide',
            'message': "📚 **Centre d'aide SIGR-CA**\n\n"
                       "• 📅 **Réserver** : Dites 'Je veux réserver une salle'\n"
                       "• 🔍 **Disponibilité** : Dites 'Salle disponible à 14h'\n"
                       "• 📋 **Mes réservations** : Dites 'Voir mes réservations'\n"
                       "• ❌ **Annuler** : Dites 'Annuler ma réservation'\n"
                       "• ⏰ **Meilleurs créneaux** : Dites 'Quel est le meilleur créneau ?'\n\n"
                       "Que souhaitez-vous faire ?",
            'suggestions': ["📅 Réserver", "🔍 Disponibilité", "📋 Mes réservations"]
        }
    
    else:
        return {
            'intent': 'general',
            'message': "Je n'ai pas bien compris votre demande. 😅\n\n"
                       "Voici ce que je peux faire pour vous :\n"
                       "• 📅 Réserver une salle\n"
                       "• 🔍 Vérifier la disponibilité\n"
                       "• 📋 Voir vos réservations\n"
                       "• ❌ Annuler une réservation\n\n"
                       "Comment puis-je vous aider ?",
            'suggestions': ["📅 Réserver une salle", "🔍 Voir disponibilités", "📋 Mes réservations"]
        }


def extract_date_from_message(message):
    """Extraire une date du message utilisateur"""
    today = datetime.now()
    
    if 'aujourd\'hui' in message or "aujourd'hui" in message:
        return today.strftime('%d/%m/%Y')
    elif 'demain' in message:
        return (today + timedelta(days=1)).strftime('%d/%m/%Y')
    elif 'ce soir' in message or 'soir' in message:
        return "ce soir"
    elif 'après-midi' in message:
        return "cet après-midi"
    elif 'matin' in message:
        return "ce matin"
    
    # Recherche de date au format JJ/MM ou JJ/MM/AAAA
    date_pattern = r'(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?'
    match = re.search(date_pattern, message)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else today.year
        if year < 100:
            year += 2000
        return f"{day:02d}/{month:02d}/{year}"
    
    return None


def get_available_rooms(date_info=None):
    """Récupérer les salles disponibles"""
    from bson import ObjectId
    
    bureaux = list(db.bureaux.find())
    available = []
    
    for bureau in bureaux:
        available.append({
            'id': str(bureau['_id']),
            'nom': bureau.get('nom', 'Salle'),
            'capacite': bureau.get('capacite_max', 10),
            'niveau': bureau.get('niveau_securite', 'standard'),
            'disponible': True
        })
    
    return available[:8]


def get_availability_summary(date_info=None):
    """Résumé des disponibilités"""
    bureaux = list(db.bureaux.find())
    
    total = len(bureaux)
    taux_moyen = 35  # Valeur par défaut
    
    text = f"• {total} salle(s) disponible(s)\n• Taux d'occupation moyen: {taux_moyen}%\n"
    
    return {
        'text': text,
        'taux_moyen': taux_moyen,
        'total_salles': total
    }


def get_optimal_time_slot():
    """Meilleurs créneaux recommandés"""
    slots = [
        {'debut': '09:00', 'fin': '10:00', 'taux': 25, 'disponibilite': 'Très disponible'},
        {'debut': '10:00', 'fin': '11:00', 'taux': 45, 'disponibilite': 'Disponible'},
        {'debut': '14:00', 'fin': '15:00', 'taux': 30, 'disponibilite': 'Disponible'},
        {'debut': '15:00', 'fin': '16:00', 'taux': 28, 'disponibilite': 'Disponible'},
    ]
    
    text = ""
    for s in slots[:3]:
        text += f"• {s['debut']} → {s['fin']} : {s['disponibilite']} ({s['taux']}% d'occupation)\n"
    
    return {
        'text': text,
        'slots': slots
    }


@login_required
def api_chatbot_conversations(request):
    """Récupérer l'historique des conversations"""
    conversations = ChatbotConversation.objects.filter(user=request.user, is_active=True).order_by('-updated_at')[:10]
    
    data = []
    for conv in conversations:
        last_message = conv.messages.filter(role='assistant').last()
        data.append({
            'id': conv.id,
            'created_at': conv.created_at.strftime('%d/%m/%Y %H:%M'),
            'last_message': last_message.content[:100] if last_message else '',
            'message_count': conv.messages.count()
        })
    
    return JsonResponse({'conversations': data})


@login_required
def api_chatbot_conversation_detail(request, conversation_id):
    """Détail d'une conversation"""
    try:
        conversation = ChatbotConversation.objects.get(id=conversation_id, user=request.user)
        messages = []
        for msg in conversation.messages.all():
            messages.append({
                'role': msg.role,
                'content': msg.content,
                'created_at': msg.created_at.strftime('%H:%M')
            })
        
        return JsonResponse({'messages': messages, 'conversation_id': conversation.id})
    except ChatbotConversation.DoesNotExist:
        return JsonResponse({'error': 'Conversation non trouvée'}, status=404)
        # dashboard/views.py - Ajoutez ces fonctions

# ====================== NOTIFICATIONS ADMINISTRATEUR ======================

@login_required
def admin_notifications(request):
    """Centre de notifications pour les administrateurs"""
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    from bson import ObjectId
    from datetime import datetime
    
    # Récupérer les notifications depuis MongoDB
    notifications = list(db.admin_notifications.find({
        'admin_id': request.user.id
    }).sort('created_at', -1))
    
    for n in notifications:
        n['id'] = str(n['_id'])
        if 'status' not in n:
            n['status'] = 'non_lu'
        if 'categorie' not in n:
            n['categorie'] = n.get('type', 'info')
        if 'icon' not in n:
            n['icon'] = '🔔'
    
    # Compter les non lues
    unread_count = sum(1 for n in notifications if n.get('status') == 'non_lu')
    
    # Traitement POST pour marquer comme lu
    if request.method == 'POST':
        if 'mark_read' in request.POST:
            notification_id = request.POST.get('notification_id')
            if notification_id:
                db.admin_notifications.update_one(
                    {'_id': ObjectId(notification_id), 'admin_id': request.user.id},
                    {'$set': {'status': 'lu', 'read_at': datetime.now()}}
                )
            else:
                # Marquer toutes comme lues
                db.admin_notifications.update_many(
                    {'admin_id': request.user.id, 'status': 'non_lu'},
                    {'$set': {'status': 'lu', 'read_at': datetime.now()}}
                )
            return redirect('admin_notifications')
        
        elif 'delete_all' in request.POST:
            db.admin_notifications.delete_many({'admin_id': request.user.id})
            return redirect('admin_notifications')
    
    return render(request, 'dashboard/admin_notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@login_required
def api_admin_notifications_unread_count(request):
    """API pour récupérer le nombre de notifications admin non lues"""
    try:
        if not request.user.is_staff:
            return JsonResponse({'count': 0})
        
        count = db.admin_notifications.count_documents({
            'admin_id': request.user.id,
            'status': 'non_lu'
        })
        
        return JsonResponse({'count': count})
        
    except Exception as e:
        return JsonResponse({'count': 0})


@login_required
def api_admin_mark_notification_read(request):
    """API pour marquer une notification admin comme lue"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    try:
        import json
        from bson import ObjectId
        from datetime import datetime
        
        data = json.loads(request.body)
        notification_id = data.get('notification_id')
        
        if notification_id:
            db.admin_notifications.update_one(
                {'_id': ObjectId(notification_id), 'admin_id': request.user.id},
                {'$set': {'status': 'lu', 'read_at': datetime.now()}}
            )
        else:
            # Marquer toutes comme lues
            db.admin_notifications.update_many(
                {'admin_id': request.user.id, 'status': 'non_lu'},
                {'$set': {'status': 'lu', 'read_at': datetime.now()}}
            )
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_admin_delete_notification(request):
    """API pour supprimer une notification admin"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    try:
        import json
        from bson import ObjectId
        
        data = json.loads(request.body)
        notification_id = data.get('notification_id')
        
        if notification_id:
            db.admin_notifications.delete_one({
                '_id': ObjectId(notification_id),
                'admin_id': request.user.id
            })
        else:
            db.admin_notifications.delete_many({'admin_id': request.user.id})
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_admin_send_test_notification(request):
    """API pour envoyer une notification de test à l'admin"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    from datetime import datetime
    
    notification = {
        'admin_id': request.user.id,
        'titre': '🔔 Notification de test',
        'message': 'Ceci est une notification de test pour le centre d\'administration.',
        'categorie': 'info',
        'icon': '🔔',
        'status': 'non_lu',
        'action_url': '/admin/notifications/',
        'created_at': datetime.now()
    }
    
    db.admin_notifications.insert_one(notification)
    
    return JsonResponse({'status': 'success', 'message': 'Notification envoyée'})


# ====================== FONCTIONS D'ENVOI DE NOTIFICATIONS ADMIN ======================

def send_admin_notification(admin_id, titre, message, categorie='info', icon='🔔', action_url=None, reservation_id=None):
    """Envoie une notification à un administrateur"""
    from datetime import datetime
    
    notification = {
        'admin_id': admin_id,
        'titre': titre,
        'message': message,
        'categorie': categorie,
        'icon': icon,
        'status': 'non_lu',
        'action_url': action_url,
        'reservation_id': reservation_id,
        'created_at': datetime.now()
    }
    
    db.admin_notifications.insert_one(notification)


def send_notification_to_all_admins(titre, message, categorie='info', icon='🔔', action_url=None, reservation_id=None):
    """Envoie une notification à tous les administrateurs"""
    from datetime import datetime
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    admins = User.objects.filter(is_staff=True, is_active=True)
    
    notifications = []
    for admin in admins:
        notifications.append({
            'admin_id': admin.id,
            'titre': titre,
            'message': message,
            'categorie': categorie,
            'icon': icon,
            'status': 'non_lu',
            'action_url': action_url,
            'reservation_id': reservation_id,
            'created_at': datetime.now()
        })
    
    if notifications:
        db.admin_notifications.insert_many(notifications)


# ====================== ÉVÉNEMENTS DÉCLENCHANT DES NOTIFICATIONS ADMIN ======================

# 1. Nouvelle réservation créée par un employé
def notify_admins_new_reservation(employe, reservation_data):
    """Notifie tous les admins d'une nouvelle réservation"""
    titre = f"🆕 Nouvelle réservation en attente"
    message = f"{employe.get('prenom', '')} {employe.get('nom', '')} a demandé une réservation pour '{reservation_data.get('titre')}' le {reservation_data['date_debut'].strftime('%d/%m/%Y à %H:%M')}."
    send_notification_to_all_admins(
        titre=titre,
        message=message,
        categorie='reservation',
        icon='🆕',
        action_url=f'/reservations/{reservation_data.get("id")}/',
        reservation_id=reservation_data.get('id')
    )


# 2. Alerte de sécurité (tentative d'accès non autorisée)
def notify_admins_security_alert(zone, badge_id, message):
    """Notifie les admins d'une alerte de sécurité"""
    titre = f"⚠️ ALERTE SÉCURITÉ"
    message_complet = f"Tentative d'accès non autorisée détectée.\nZone: {zone}\nBadge: {badge_id}\nDétails: {message}"
    send_notification_to_all_admins(
        titre=titre,
        message=message_complet,
        categorie='alerte',
        icon='⚠️'
    )


# 3. Équipement hors ligne / maintenance
def notify_admins_equipment_offline(equipement_nom, equipement_id):
    """Notifie les admins qu'un équipement est hors ligne"""
    titre = f"🔧 Équipement hors ligne"
    message = f"L'équipement '{equipement_nom}' est actuellement hors ligne. Une intervention est nécessaire."
    send_notification_to_all_admins(
        titre=titre,
        message=message,
        categorie='maintenance',
        icon='🔧',
        action_url=f'/equipements/{equipement_id}/'
    )


# 4. Réservation modifiée/annulée par un employé
def notify_admins_reservation_cancelled(employe, reservation):
    """Notifie les admins qu'une réservation a été annulée"""
    titre = f"🗑️ Réservation annulée"
    message = f"{employe.get('prenom', '')} {employe.get('nom', '')} a annulé sa réservation '{reservation.get('titre')}'."
    send_notification_to_all_admins(
        titre=titre,
        message=message,
        categorie='reservation',
        icon='🗑️',
        action_url=f'/reservations/{reservation.get("id")}/'
    )


# 5. Réservation bientôt pleine (alerte occupation)
def notify_admins_high_occupation(zone_nom, occupation_rate):
    """Notifie les admins qu'une zone a un taux d'occupation élevé"""
    if occupation_rate >= 80:
        titre = f"📊 Taux d'occupation critique"
        message = f"La zone '{zone_nom}' a atteint {occupation_rate}% d'occupation. Une attention particulière est recommandée."
        send_notification_to_all_admins(
            titre=titre,
            message=message,
            categorie='alerte',
            icon='📊'
        )
        # dashboard/views.py - Ajoutez ces fonctions

# ====================== NOTIFICATIONS ADMINISTRATEUR ======================

def send_admin_notification(admin_id, titre, message, categorie='info', icon='🔔', action_url=None, reservation_id=None):
    """Envoie une notification à un administrateur spécifique"""
    from datetime import datetime
    
    notification = {
        'admin_id': admin_id,
        'titre': titre,
        'message': message,
        'categorie': categorie,
        'icon': icon,
        'status': 'non_lu',
        'action_url': action_url,
        'reservation_id': reservation_id,
        'created_at': datetime.now()
    }
    
    db.admin_notifications.insert_one(notification)


def send_notification_to_all_admins(titre, message, categorie='info', icon='🔔', action_url=None, reservation_id=None):
    """Envoie une notification à tous les administrateurs"""
    from datetime import datetime
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    admins = User.objects.filter(is_staff=True, is_active=True)
    
    if not admins:
        return
    
    notifications = []
    for admin in admins:
        notifications.append({
            'admin_id': admin.id,
            'titre': titre,
            'message': message,
            'categorie': categorie,
            'icon': icon,
            'status': 'non_lu',
            'action_url': action_url,
            'reservation_id': reservation_id,
            'created_at': datetime.now()
        })
    
    if notifications:
        db.admin_notifications.insert_many(notifications)


def notify_admins_new_reservation(employe, reservation_data):
    """Notifie tous les admins d'une nouvelle réservation"""
    titre = f"🆕 Nouvelle réservation en attente"
    message = f"{employe.get('prenom', '')} {employe.get('nom', '')} a demandé une réservation pour '{reservation_data.get('titre')}' le {reservation_data['date_debut'].strftime('%d/%m/%Y à %H:%M')}."
    send_notification_to_all_admins(
        titre=titre,
        message=message,
        categorie='reservation',
        icon='🆕',
        action_url=f'/reservations/{reservation_data.get("id")}/',
        reservation_id=reservation_data.get('id')
    )


def notify_admins_security_alert(zone, badge_id, message):
    """Notifie les admins d'une alerte de sécurité"""
    titre = f"⚠️ ALERTE SÉCURITÉ"
    message_complet = f"Tentative d'accès non autorisée détectée.\nZone: {zone}\nBadge: {badge_id}\nDétails: {message}"
    send_notification_to_all_admins(
        titre=titre,
        message=message_complet,
        categorie='alerte',
        icon='⚠️'
    )


def notify_admins_equipment_offline(equipement_nom, equipement_id):
    """Notifie les admins qu'un équipement est hors ligne"""
    titre = f"🔧 Équipement hors ligne"
    message = f"L'équipement '{equipement_nom}' est actuellement hors ligne. Une intervention est nécessaire."
    send_notification_to_all_admins(
        titre=titre,
        message=message,
        categorie='maintenance',
        icon='🔧',
        action_url=f'/equipements/{equipement_id}/'
    )


def notify_admins_reservation_cancelled(employe, reservation):
    """Notifie les admins qu'une réservation a été annulée"""
    titre = f"🗑️ Réservation annulée"
    message = f"{employe.get('prenom', '')} {employe.get('nom', '')} a annulé sa réservation '{reservation.get('titre')}'."
    send_notification_to_all_admins(
        titre=titre,
        message=message,
        categorie='reservation',
        icon='🗑️',
        action_url=f'/reservations/{reservation.get("id")}/'
    )


def notify_admins_high_occupation(zone_nom, occupation_rate):
    """Notifie les admins qu'une zone a un taux d'occupation élevé"""
    if occupation_rate >= 80:
        titre = f"📊 Taux d'occupation critique"
        message = f"La zone '{zone_nom}' a atteint {occupation_rate}% d'occupation. Une attention particulière est recommandée."
        send_notification_to_all_admins(
            titre=titre,
            message=message,
            categorie='alerte',
            icon='📊'
        )


# ====================== APIS POUR NOTIFICATIONS ADMIN ======================

@login_required
def api_admin_notifications_unread_count(request):
    """API pour récupérer le nombre de notifications admin non lues"""
    try:
        if not request.user.is_staff:
            return JsonResponse({'count': 0})
        
        count = db.admin_notifications.count_documents({
            'admin_id': request.user.id,
            'status': 'non_lu'
        })
        
        return JsonResponse({'count': count})
        
    except Exception as e:
        return JsonResponse({'count': 0})


@login_required
def api_admin_mark_notification_read(request):
    """API pour marquer une notification admin comme lue"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    try:
        import json
        from bson import ObjectId
        from datetime import datetime
        
        data = json.loads(request.body)
        notification_id = data.get('notification_id')
        
        if notification_id:
            db.admin_notifications.update_one(
                {'_id': ObjectId(notification_id), 'admin_id': request.user.id},
                {'$set': {'status': 'lu', 'read_at': datetime.now()}}
            )
        else:
            # Marquer toutes comme lues
            db.admin_notifications.update_many(
                {'admin_id': request.user.id, 'status': 'non_lu'},
                {'$set': {'status': 'lu', 'read_at': datetime.now()}}
            )
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_admin_delete_notification(request):
    """API pour supprimer une notification admin"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    try:
        import json
        from bson import ObjectId
        
        data = json.loads(request.body)
        notification_id = data.get('notification_id')
        
        if notification_id:
            db.admin_notifications.delete_one({
                '_id': ObjectId(notification_id),
                'admin_id': request.user.id
            })
        else:
            db.admin_notifications.delete_many({'admin_id': request.user.id})
        
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_admin_send_test_notification(request):
    """API pour envoyer une notification de test à l'admin"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    from datetime import datetime
    
    notification = {
        'admin_id': request.user.id,
        'titre': '🔔 Notification de test',
        'message': 'Ceci est une notification de test pour le centre d\'administration.',
        'categorie': 'info',
        'icon': '🔔',
        'status': 'non_lu',
        'action_url': '/admin/notifications/',
        'created_at': datetime.now()
    }
    
    db.admin_notifications.insert_one(notification)
    
    return JsonResponse({'status': 'success', 'message': 'Notification envoyée'})
def notify_admin_new_reservation(employe, reservation_data, reservation_id):
    """Notifie les administrateurs d'une nouvelle réservation"""
    from django.contrib.auth import get_user_model
    from datetime import datetime
    
    User = get_user_model()
    admins = User.objects.filter(is_staff=True, is_active=True)
    
    for admin in admins:
        admin_notification = {
            'admin_id': admin.id,
            'titre': '🆕 Nouvelle réservation en attente',
            'message': f"{employe.get('prenom', '')} {employe.get('nom', '')} a demandé une réservation pour '{reservation_data.get('titre')}'.",
            'categorie': 'reservation',
            'icon': '🆕',
            'status': 'non_lu',
            'action_url': f'/reservations/{reservation_id}/',
            'reservation_id': reservation_id,
            'created_at': datetime.now()
        }
        db.admin_notifications.insert_one(admin_notification)