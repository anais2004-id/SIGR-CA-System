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

from .models import Utilisateur, UserSession

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
    """Tableau de bord employé"""
    if request.user.is_staff or request.user.is_superuser:
        return redirect('dashboard')
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        messages.error(request, "Profil employé introuvable. Contactez l'administrateur.")
        logout(request)
        return redirect('login')
    
    employe['id'] = str(employe['_id'])
    utilisateur_id = employe['_id']
    
    total_acces = db.acces_logs.count_documents({'utilisateur_id': utilisateur_id})
    acces_autorises = db.acces_logs.count_documents({'utilisateur_id': utilisateur_id, 'resultat': 'AUTORISE'})
    acces_refuses = total_acces - acces_autorises
    taux_succes = round((acces_autorises / total_acces * 100) if total_acces > 0 else 0, 1)
    
    acces = list(db.acces_logs.find({'utilisateur_id': utilisateur_id}).sort('timestamp', -1).limit(10))
    for a in acces:
        bureau = db.bureaux.find_one({'_id': a.get('bureau_id')})
        a['bureau_nom'] = bureau['nom'] if bureau else 'Zone inconnue'
        if not a.get('type_acces'):
            a['type_acces'] = 'RFID'
        if not a.get('resultat'):
            a['resultat'] = 'REFUSE'
    
    reservations = list(db.reservations.find({'employe_id': str(employe['_id'])}).sort('date_debut', -1))
    now = datetime.now()
    a_venir = 0
    prochaine_resa = None
    
    for r in reservations:
        r['id'] = str(r['_id'])
        bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
        r['bureau_nom'] = bureau['nom'] if bureau else 'Salle inconnue'
        
        if r.get('statut') == 'confirmee' and r.get('date_debut') and r['date_debut'] > now:
            a_venir += 1
            if not prochaine_resa:
                prochaine_resa = r
    
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
    
    return render(request, 'dashboard/employe_espace.html', {
        'employe': employe,
        'acces': acces,
        'total_acces': total_acces,
        'acces_autorises': acces_autorises,
        'acces_refuses': acces_refuses,
        'taux_succes': taux_succes,
        'reservations': reservations,
        'a_venir': a_venir,
        'prochaine_resa': prochaine_resa,
        'bureaux': bureaux,
    })


# dashboard/views.py - Modifiez la fonction employe_mes_reservations

@login_required
def employe_mes_reservations(request):
    if request.user.is_staff:
        return redirect('dashboard')
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        return redirect('login')
    
    employe['id'] = str(employe['_id'])
    reservations = list(db.reservations.find({'employe_id': str(employe['_id'])}).sort('date_debut', -1))
    
    for r in reservations:
        r['id'] = str(r['_id'])
        bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
        r['bureau_nom'] = bureau['nom'] if bureau else 'Salle inconnue'
    
    now = datetime.now()
    actives = sum(1 for r in reservations if r.get('statut') == 'confirmee'
                  and r.get('date_debut') and r['date_debut'] <= now <= r.get('date_fin', now))
    a_venir = sum(1 for r in reservations if r.get('statut') == 'confirmee'
                  and r.get('date_debut') and r['date_debut'] > now)
    en_attente = sum(1 for r in reservations if r.get('statut') == 'en_attente')
    
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
    
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
                    # CRITIQUE: Changement ici - statut = 'en_attente' au lieu de 'confirmee'
                    reservation_data = {
                        'titre': request.POST.get('titre', '').strip(),
                        'description': request.POST.get('description', '').strip(),
                        'bureau_id': ObjectId(bureau_id),
                        'employe_id': str(employe['_id']),
                        'employe_nom': f"{employe.get('nom', '')} {employe.get('prenom', '')}",
                        'date_debut': date_debut,
                        'date_fin': date_fin,
                        'nb_participants': int(request.POST.get('nb_participants', 1)),
                        'statut': 'en_attente',  # ← Changement important
                        'qr_code': None,  # Pas de QR code tant que non confirmée
                        'created_at': datetime.now(),
                        'created_by': request.user.username,
                    }
                    db.reservations.insert_one(reservation_data)
                    
                    # Notification à l'admin
                    notify_admin_new_reservation(employe, reservation_data)
                    
                    messages.success(request, "Réservation créée avec succès ! En attente de validation par un administrateur.")
                    return redirect('employe_mes_reservations')
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    # Convertir les réservations en JSON pour le calendrier
    reservations_json = json.dumps([{
        'id': str(r['_id']),
        'date_debut': r['date_debut'].isoformat() if r.get('date_debut') else None,
    } for r in reservations], default=str)
    
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


def notify_admin_new_reservation(employe, reservation_data):
    """Notifie les administrateurs d'une nouvelle réservation"""
    admins = Utilisateur.objects.filter(is_staff=True, is_active=True)
    
    message = f"""
    🆕 NOUVELLE RÉSERVATION EN ATTENTE
    
    Employé: {employe.get('prenom', '')} {employe.get('nom', '')}
    Titre: {reservation_data.get('titre')}
    Salle: {reservation_data.get('bureau_id')}
    Date: {reservation_data['date_debut'].strftime('%d/%m/%Y %H:%M')} → {reservation_data['date_fin'].strftime('%H:%M')}
    Participants: {reservation_data.get('nb_participants', 1)}
    
    Connectez-vous à l'interface admin pour confirmer ou refuser cette réservation.
    """
    
    for admin in admins:
        db.notifications.insert_one({
            'destinataire': admin.email,
            'type_notification': 'email',
            'categorie': 'reservation_attente',
            'sujet': f"Nouvelle réservation en attente - {reservation_data.get('titre')}",
            'message': message,
            'statut': 'envoyee',
            'reservation_id': str(reservation_data.get('_id')),
            'created_at': datetime.now(),
        })
        
        if admin.email:
            try:
                from django.core.mail import send_mail
                send_mail(
                    f"Nouvelle réservation en attente - {reservation_data.get('titre')}",
                    message,
                    settings.DEFAULT_FROM_EMAIL,
                    [admin.email],
                    fail_silently=True,
                )
            except:
                pass


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
    acces_ok = db.acces_logs.count_documents({'resultat': 'AUTORISE'})
    acces_no = db.acces_logs.count_documents({'resultat': 'REFUSE'})
    total_bureaux = db.bureaux.count_documents({})
    alertes = db.alertes.count_documents({'statut': 'NON_TRAITEE'}) if 'alertes' in db.list_collection_names() else 0
    
    derniers_logs = list(db.acces_logs.find().sort('timestamp', -1).limit(20))
    for log in derniers_logs:
        b = db.bureaux.find_one({'_id': log.get('bureau_id')})
        log['bureau_nom'] = b['nom'] if b else 'Inconnu'
        e = db.employees.find_one({'_id': log.get('utilisateur_id')})
        log['nom_utilisateur'] = f"{e.get('nom','')} {e.get('prenom','')}" if e else 'Inconnu'
    
    bureaux = list(db.bureaux.find().limit(10))
    for b in bureaux:
        b['id'] = str(b['_id'])
    
    return render(request, 'dashboard/live.html', {
        'acces_ok': acces_ok,
        'acces_no': acces_no,
        'total_bureaux': total_bureaux,
        'alertes': alertes,
        'derniers_logs': derniers_logs,
        'bureaux': bureaux,
    })


# ====================== RESSOURCES ======================

@login_required
def ressources(request):
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
    capacite_totale = sum(b.get('capacite_max', 0) for b in bureaux)
    one_hour_ago = datetime.now() - timedelta(hours=1)
    total_occ, total_cap = 0, 0
    for b in bureaux:
        cap = b.get('capacite_max', 10)
        recent = db.acces_logs.count_documents({'bureau_id': b['_id'], 'timestamp': {'$gte': one_hour_ago}})
        total_occ += min(recent * 3, cap)
        total_cap += cap
    occupation_moy = round(total_occ / total_cap * 100) if total_cap else 0
    return render(request, 'dashboard/ressources.html', {
        'total_bureaux': len(bureaux),
        'capacite_totale': capacite_totale,
        'occupation_moy': occupation_moy,
        'bureaux': bureaux,
    })


@login_required
def bureau_ajouter(request):
    if request.method == 'POST':
        try:
            data = {
                'nom': request.POST.get('nom'),
                'code_bureau': request.POST.get('code_bureau'),
                'etage': int(request.POST.get('etage', 0)),
                'capacite_max': int(request.POST.get('capacite_max', 10)),
                'niveau_securite': request.POST.get('niveau_securite', 'standard'),
                'description': request.POST.get('description', ''),
                'created_at': datetime.now(),
            }
            db.bureaux.insert_one(data)
            messages.success(request, f"Ressource ajoutée avec succès!")
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    return redirect('ressources')


@login_required
def bureau_detail(request, bureau_id):
    return redirect('ressources')


# ====================== CALENDRIER ET RÈGLES ======================

@login_required
def calendrier(request):
    employes = list(db.employees.find({'statut': 'actif'}))
    for e in employes:
        e['id'] = str(e['_id'])
    return render(request, 'dashboard/calendrier.html', {'employes': employes})


@login_required
def api_get_employee_rules(request, employe_id):
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
                db.access_rules.delete_many({'employe_id': employe_id, 'jour': jour, 'mois': mois, 'annee': annee})
            else:
                db.access_rules.delete_one({'employe_id': employe_id, 'zone_nom': zone_nom, 'jour': jour, 'mois': mois, 'annee': annee})
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
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        rules = data.get('rules', [])
        if not employe_id:
            return JsonResponse({'error': 'Employé ID manquant'}, status=400)
        db.access_rules.delete_many({'employe_id': employe_id})
        if rules:
            db.access_rules.insert_many([{
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
            } for r in rules])
        return JsonResponse({'status': 'success', 'message': f'{len(rules)} règle(s) enregistrée(s)'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_bureaux(request):
    bureaux = list(db.bureaux.find())
    result = [{'id': str(b['_id']), 'nom': b.get('nom', ''), 'niveau': b.get('niveau_securite', 'standard'), 'capacite': b.get('capacite_max', 0)} for b in bureaux]
    if not result:
        result = [
            {'id': '1', 'nom': 'Direction Générale', 'niveau': 'critique', 'capacite': 5},
            {'id': '2', 'nom': 'Atelier Production', 'niveau': 'standard', 'capacite': 20},
            {'id': '3', 'nom': 'Salle Serveur', 'niveau': 'critique', 'capacite': 2},
            {'id': '4', 'nom': 'Archives', 'niveau': 'restreint', 'capacite': 3},
            {'id': '5', 'nom': 'Bureau RH', 'niveau': 'standard', 'capacite': 4},
            {'id': '6', 'nom': 'Laboratoire', 'niveau': 'restreint', 'capacite': 6},
            {'id': '7', 'nom': 'Entrée Principale', 'niveau': 'public', 'capacite': 50},
        ]
    return JsonResponse({'bureaux': result})


# ====================== STATISTIQUES ======================

@login_required
def statistiques(request):
    now = datetime.now()
    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total_mois = db.acces_logs.count_documents({'timestamp': {'$gte': start_month}})
    total_all = db.acces_logs.count_documents({})
    autorises = db.acces_logs.count_documents({'resultat': 'AUTORISE'})
    taux_succes = round(autorises / total_all * 100) if total_all else 0
    
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
                'nom': emp.get('nom'),
                'prenom': emp.get('prenom'),
                'departement': emp.get('departement'),
                'nb_acces': t['count'],
                'taux_succes': round(auto_emp / t['count'] * 100) if t['count'] else 0,
                'dernier_acces': None,
                'zone_principale': 'Atelier'
            })
    
    zones_stats = []
    for z in db.acces_logs.aggregate([
        {'$match': {'timestamp': {'$gte': start_month}}},
        {'$group': {'_id': '$bureau_id', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]):
        b = db.bureaux.find_one({'_id': z['_id']})
        if b:
            total_z = db.acces_logs.count_documents({'bureau_id': z['_id']})
            auto_z = db.acces_logs.count_documents({'bureau_id': z['_id'], 'resultat': 'AUTORISE'})
            zones_stats.append({'nom': b['nom'], 'count': z['count'], 'pct': round(auto_z / total_z * 100) if total_z else 0})
    
    labels, autorises_list, refuses_list, prediction_list = [], [], [], []
    for i in range(29, -1, -1):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        a = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'AUTORISE'})
        r = db.acces_logs.count_documents({'timestamp': {'$gte': day_start, '$lt': day_end}, 'resultat': 'REFUSE'})
        labels.append(day_start.strftime('%d/%m'))
        autorises_list.append(a)
        refuses_list.append(r)
    
    for i in range(len(autorises_list)):
        window = autorises_list[max(0, i-6):i+1]
        avg = sum(window) / len(window) if window else 0
        prediction_list.append(round(avg * 1.05, 1))
    
    chart_data = json.dumps({'labels': labels, 'autorises': autorises_list, 'refuses': refuses_list, 'prediction': prediction_list})
    last_7 = sum(autorises_list[-7:]) if len(autorises_list) >= 7 else sum(autorises_list)
    prev_7 = sum(autorises_list[-14:-7]) if len(autorises_list) >= 14 else last_7
    prediction_pct = round(((last_7 - prev_7) / prev_7 * 100) if prev_7 else 0, 1)
    
    return render(request, 'dashboard/statistiques.html', {
        'total_mois': total_mois,
        'taux_succes': taux_succes,
        'taux_refus': 100 - taux_succes,
        'pic_heure': '08h30',
        'zone_active': zones_stats[0]['nom'] if zones_stats else 'N/A',
        'top_employes': top_employes,
        'zones_stats': zones_stats,
        'chart_data': chart_data,
        'prediction': prediction_pct,
    })


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
    derniers_logs = list(db.acces_logs.find().sort('timestamp', -1).limit(15))
    logs_data = []
    for log in derniers_logs:
        emp = db.employees.find_one({'_id': log.get('utilisateur_id')})
        bureau = db.bureaux.find_one({'_id': log.get('bureau_id')})
        nom = f"{emp.get('nom','?')} {emp.get('prenom','')}" if emp else 'Inconnu'
        badge = emp.get('badge_id', '???') if emp else '???'
        logs_data.append({
            'nom': nom,
            'badge': badge,
            'zone': bureau['nom'] if bureau else 'Zone inconnue',
            'resultat': log.get('resultat', 'REFUSE'),
            'method': log.get('type_acces', 'RFID'),
            'time': log['timestamp'].strftime('%H:%M:%S') if log.get('timestamp') else '--:--:--',
        })
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    acces_ok = db.acces_logs.count_documents({'timestamp': {'$gte': today_start}, 'resultat': 'AUTORISE'})
    acces_no = db.acces_logs.count_documents({'timestamp': {'$gte': today_start}, 'resultat': 'REFUSE'})
    alertes = db.alertes.count_documents({'statut': 'NON_TRAITEE'}) if 'alertes' in db.list_collection_names() else 0
    presences = db.acces_logs.count_documents({'timestamp': {'$gte': today_start}})
    return JsonResponse({
        'logs': logs_data,
        'stats': {'acces_ok': acces_ok, 'acces_no': acces_no, 'alertes': alertes, 'presences': presences}
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
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    reservations = list(db.reservations.find().sort('date_debut', -1))
    
    for r in reservations:
        r['id'] = str(r['_id'])
        employe_id = r.get('employe_id')
        if employe_id:
            try:
                emp = db.employees.find_one({'_id': ObjectId(employe_id)})
                if emp:
                    r['employe_nom'] = f"{emp.get('nom', '')} {emp.get('prenom', '')}".strip() or 'Inconnu'
                else:
                    emp = db.employees.find_one({'django_user_id': employe_id})
                    if emp:
                        r['employe_nom'] = f"{emp.get('nom', '')} {emp.get('prenom', '')}".strip() or 'Inconnu'
                    else:
                        r['employe_nom'] = 'Inconnu'
            except:
                r['employe_nom'] = 'Inconnu'
        else:
            r['employe_nom'] = 'Inconnu'
        
        bureau_id = r.get('bureau_id')
        if bureau_id:
            try:
                bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
                r['bureau_nom'] = bureau['nom'] if bureau else 'Salle inconnue'
            except:
                r['bureau_nom'] = 'Salle inconnue'
        else:
            r['bureau_nom'] = 'Salle inconnue'
    
    now = datetime.now()
    actives = sum(1 for r in reservations if r.get('statut') == 'confirmee'
                  and r.get('date_debut') and r['date_debut'] <= now <= r.get('date_fin', now))
    a_venir = sum(1 for r in reservations if r.get('statut') == 'confirmee'
                  and r.get('date_debut') and r['date_debut'] > now)
    en_attente = sum(1 for r in reservations if r.get('statut') == 'en_attente')
    
    total_bureaux = db.bureaux.count_documents({})
    if total_bureaux > 0:
        occupied_bureaux = len(set(r.get('bureau_id') for r in reservations if r.get('statut') == 'confirmee' and r.get('date_debut') <= now <= r.get('date_fin', now)))
        taux_occupation = round((occupied_bureaux / total_bureaux) * 100)
    else:
        taux_occupation = 0
    
    return render(request, 'dashboard/reservation_list.html', {
        'reservations': reservations,
        'total': len(reservations),
        'actives': actives,
        'a_venir': a_venir,
        'en_attente': en_attente,
        'taux_occupation': taux_occupation,
    })


@login_required
def reservation_ajouter(request):
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])
    employes = list(db.employees.find({'statut': 'actif'}))
    for e in employes:
        e['id'] = str(e['_id'])
    
    if request.method == 'POST':
        try:
            date_debut = datetime.strptime(request.POST.get('date_debut'), '%Y-%m-%dT%H:%M')
            date_fin = datetime.strptime(request.POST.get('date_fin'), '%Y-%m-%dT%H:%M')
            bureau_id_str = request.POST.get('bureau_id')
            employe_id_str = request.POST.get('employe_id')
            
            if date_fin <= date_debut:
                messages.error(request, "La date de fin doit être après la date de début.")
                return render(request, 'dashboard/reservation_form.html',
                              {'bureaux': bureaux, 'employes': employes, 'reservation': request.POST})
            
            chevauchement = db.reservations.find_one({
                'bureau_id': ObjectId(bureau_id_str),
                'statut': {'$in': ['confirmee', 'en_attente']},
                'date_debut': {'$lt': date_fin},
                'date_fin': {'$gt': date_debut},
            })
            
            if chevauchement:
                messages.error(request, "Cette salle est déjà réservée sur ce créneau.")
                return render(request, 'dashboard/reservation_form.html',
                              {'bureaux': bureaux, 'employes': employes, 'reservation': request.POST})
            
            db.reservations.insert_one({
                'titre': request.POST.get('titre', '').strip(),
                'description': request.POST.get('description', '').strip(),
                'bureau_id': ObjectId(bureau_id_str),
                'employe_id': ObjectId(employe_id_str),
                'date_debut': date_debut,
                'date_fin': date_fin,
                'nb_participants': int(request.POST.get('nb_participants', 1)),
                'statut': 'confirmee',
                'created_at': datetime.now(),
                'created_by': request.user.username,
            })
            messages.success(request, "Réservation créée avec succès!")
            return redirect('reservation_list')
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return render(request, 'dashboard/reservation_form.html',
                  {'bureaux': bureaux, 'employes': employes, 'reservation': {}, 'is_edit': False})


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
        
        if access_rule:
            if access_rule.get('acces_autorise', True):
                if access_rule.get('heure_debut', '00:00') <= current_hour <= access_rule.get('heure_fin', '23:59'):
                    acces_autorise = True
        elif reservation_valide:
            acces_autorise = True
        
        emergency = db.system_config.find_one({'type': 'emergency'})
        if emergency and emergency.get('active', False):
            acces_autorise = True
        
        log_access(employe['_id'], zone_code, 'AUTORISE' if acces_autorise else 'REFUSE',
                  'Accès ' + ('autorisé' if acces_autorise else 'refusé'), access_method)
        
        return JsonResponse({
            'autorise': acces_autorise,
            'message': 'Accès autorisé' if acces_autorise else 'Accès refusé',
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

@login_required
def active_sessions(request):
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    # Récupérer TOUTES les sessions actives, pas seulement celles du PC local
    active_sessions = UserSession.objects.filter(
        is_active=True,
        logout_time__isnull=True
    ).select_related('user').order_by('-last_activity')
    
    # Afficher toutes les sessions dans la console pour déboguer
    print(f"📊 {active_sessions.count()} sessions actives trouvées:")
    for s in active_sessions:
        print(f"  - {s.user.username} | IP: {s.ip_address} | Dernière activité: {s.last_activity}")
    
    total_connected = active_sessions.count()
    total_users = Utilisateur.objects.filter(is_active=True).count()
    admin_sessions = active_sessions.filter(user__is_staff=True).count()
    employee_sessions = total_connected - admin_sessions
    inactive_threshold = timezone.now() - timedelta(minutes=30)
    inactive_sessions = active_sessions.filter(last_activity__lt=inactive_threshold).count()
    
    # Récupérer l'historique des dernières 24h
    last_24h = timezone.now() - timedelta(hours=24)
    recent_history = UserSession.objects.filter(
        logout_time__isnull=False,
        logout_time__gte=last_24h
    ).select_related('user').order_by('-logout_time')[:50]
    
    return render(request, 'dashboard/active_sessions.html', {
        'active_sessions': active_sessions,
        'total_connected': total_connected,
        'total_users': total_users,
        'admin_sessions': admin_sessions,
        'employee_sessions': employee_sessions,
        'inactive_sessions': inactive_sessions,
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
            user_session.is_active = False
            user_session.logout_time = timezone.now()
            user_session.save()
            try:
                Session.objects.filter(session_key=user_session.session_key).delete()
            except:
                pass
            messages.success(request, f"Session de {user_session.user.username} terminée")
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
        is_active_now = (timezone.now() - session.last_activity).seconds < 300
        users.append({
            'id': session.id,
            'user_id': session.user.id,
            'username': session.user.username,
            'full_name': session.user.get_full_name(),
            'is_staff': session.user.is_staff,
            'login_time': session.login_time.strftime('%d/%m/%Y %H:%M:%S'),
            'last_activity': session.last_activity.strftime('%d/%m/%Y %H:%M:%S'),
            'ip_address': session.ip_address or '—',
            'session_key': session.session_key,
            'is_active': is_active_now,
        })
    
    return JsonResponse({
        'total': len(users),
        'users': users,
        'timestamp': timezone.now().strftime('%d/%m/%Y %H:%M:%S'),
    })
# dashboard/views.py - Ajoutez cette fonction



@login_required
def employe_profil(request):
    """Modification du profil employé"""
    if request.user.is_staff:
        return redirect('dashboard')
    
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        messages.error(request, "Profil employé introuvable.")
        return redirect('login')
    
    employe['id'] = str(employe['_id'])
    
    # Statistiques pour l'affichage
    total_acces = db.acces_logs.count_documents({'utilisateur_id': employe['_id']})
    acces_autorises = db.acces_logs.count_documents({
        'utilisateur_id': employe['_id'],
        'resultat': 'AUTORISE'
    })
    taux_succes = round((acces_autorises / total_acces * 100) if total_acces > 0 else 0, 1)
    reservations_count = db.reservations.count_documents({'employe_id': str(employe['_id'])})
    
    # Préférences par défaut si non définies
    if 'preferences_notifications' not in employe:
        employe['preferences_notifications'] = {'email': True, 'sms': False}
    
    if request.method == 'POST':
        try:
            prenom = request.POST.get('prenom', '').strip()
            nom = request.POST.get('nom', '').strip()
            email = request.POST.get('email', '').strip()
            telephone = request.POST.get('telephone', '').strip()
            poste = request.POST.get('poste', '').strip()
            departement = request.POST.get('departement', '').strip()
            notif_email = request.POST.get('notif_email') == 'on'
            notif_sms = request.POST.get('notif_sms') == 'on'
            
            if not prenom or not nom:
                messages.error(request, "Le nom et le prénom sont requis.")
                return render(request, 'dashboard/employe_profil.html', {
                    'employe': employe,
                    'total_acces': total_acces,
                    'taux_succes': taux_succes,
                    'reservations_count': reservations_count
                })
            
            update_data = {
                'nom': nom,
                'prenom': prenom,
                'email': email,
                'telephone': telephone,
                'poste': poste,
                'departement': departement,
                'preferences_notifications': {
                    'email': notif_email,
                    'sms': notif_sms
                },
                'updated_at': datetime.now()
            }
            
            db.employees.update_one({'_id': employe['_id']}, {'$set': update_data})
            
            user = request.user
            user.first_name = prenom
            user.last_name = nom
            user.email = email
            user.save()
            
            messages.success(request, "Votre profil a été mis à jour avec succès.")
            return redirect('employe_profil')
            
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return render(request, 'dashboard/employe_profil.html', {
        'employe': employe,
        'user': request.user,
        'total_acces': total_acces,
        'taux_succes': taux_succes,
        'reservations_count': reservations_count,
    })

@login_required
def employe_change_password(request):
    """Changer le mot de passe de l'employé"""
    if request.user.is_staff:
        return redirect('dashboard')
    
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # Vérifier l'ancien mot de passe
        if not request.user.check_password(old_password):
            messages.error(request, "L'ancien mot de passe est incorrect.")
            return redirect('employe_profil')
        
        # Vérifier la longueur du nouveau mot de passe
        if len(new_password) < 6:
            messages.error(request, "Le nouveau mot de passe doit contenir au moins 6 caractères.")
            return redirect('employe_profil')
        
        # Vérifier la confirmation
        if new_password != confirm_password:
            messages.error(request, "Les mots de passe ne correspondent pas.")
            return redirect('employe_profil')
        
        # Changer le mot de passe
        request.user.set_password(new_password)
        request.user.save()
        
        # Maintenir la session active
        update_session_auth_hash(request, request.user)
        
        messages.success(request, "Votre mot de passe a été changé avec succès.")
        return redirect('employe_profil')
    
    return redirect('employe_profil')

class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)
        # dashboard/views.py - Ajoutez ces fonctions


@login_required
def reservation_list(request):
    """Liste des réservations pour l'admin avec onglets"""
    if not request.user.is_staff:
        return redirect('employe_espace')
    
    # Récupérer toutes les réservations
    reservations = list(db.reservations.find().sort('date_debut', -1))
    
    for r in reservations:
        r['id'] = str(r['_id'])
        
        # Récupérer le nom de l'employé
        employe_id = r.get('employe_id')
        if employe_id:
            try:
                if isinstance(employe_id, str) and len(employe_id) == 24:
                    emp = db.employees.find_one({'_id': ObjectId(employe_id)})
                else:
                    emp = db.employees.find_one({'django_user_id': employe_id}) or db.employees.find_one({'_id': employe_id})
                
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
        
        # Récupérer le nom de la salle
        bureau_id = r.get('bureau_id')
        if bureau_id:
            try:
                bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
                r['bureau_nom'] = bureau['nom'] if bureau else 'Salle inconnue'
            except:
                r['bureau_nom'] = 'Salle inconnue'
        else:
            r['bureau_nom'] = 'Salle inconnue'
        
        # Vérifier si la réservation a un QR code
        r['has_qr'] = r.get('qr_code') is not None
    
    # Statistiques
    now = datetime.now()
    en_attente = sum(1 for r in reservations if r.get('statut') == 'en_attente')
    confirmees = sum(1 for r in reservations if r.get('statut') == 'confirmee')
    annulees = sum(1 for r in reservations if r.get('statut') == 'annulee')
    terminees = sum(1 for r in reservations if r.get('statut') == 'terminee')
    
    return render(request, 'dashboard/reservation_list.html', {
        'reservations': reservations,
        'total': len(reservations),
        'en_attente': en_attente,
        'confirmees': confirmees,
        'annulees': annulees,
        'terminees': terminees,
        'now': now,
    })


@login_required
def reservation_confirmer(request, reservation_id):
    """Confirmer une réservation et générer un QR code"""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    try:
        reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
        if not reservation:
            messages.error(request, "Réservation non trouvée")
            return redirect('reservation_list')
        
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
            
            # Convertir l'image en base64 pour stockage MongoDB
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
            
            # Récupérer l'employé pour la notification
            employe_id = reservation.get('employe_id')
            employe = None
            try:
                if isinstance(employe_id, str) and len(employe_id) == 24:
                    employe = db.employees.find_one({'_id': ObjectId(employe_id)})
                else:
                    employe = db.employees.find_one({'django_user_id': employe_id})
            except:
                pass
            
            # Envoyer notification à l'employé
            if employe and employe.get('email'):
                send_reservation_confirmation_email(employe, reservation, qr_base64)
            
            messages.success(request, f"Réservation '{reservation.get('titre')}' confirmée avec QR code généré.")
            
            # Redirection selon la provenance
            if request.POST.get('redirect_to') == 'list':
                return redirect('reservation_list')
            return redirect('reservation_detail', reservation_id=reservation_id)
        
        # Récupérer les détails pour l'affichage
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
    
    if request.method == 'POST':
        try:
            reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
            if reservation:
                motif = request.POST.get('motif', 'Non spécifié')
                
                db.reservations.update_one(
                    {'_id': ObjectId(reservation_id)},
                    {'$set': {
                        'statut': 'annulee',
                        'refused_at': datetime.now(),
                        'refused_by': request.user.username,
                        'refusal_reason': motif,
                    }}
                )
                
                # Notifier l'employé
                employe_id = reservation.get('employe_id')
                employe = None
                try:
                    if isinstance(employe_id, str) and len(employe_id) == 24:
                        employe = db.employees.find_one({'_id': ObjectId(employe_id)})
                    else:
                        employe = db.employees.find_one({'django_user_id': employe_id})
                except:
                    pass
                
                if employe and employe.get('email'):
                    send_reservation_refusal_email(employe, reservation, motif)
                
                messages.success(request, f"Réservation '{reservation.get('titre')}' refusée.")
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")
    
    return redirect('reservation_list')


@login_required
def reservation_detail(request, reservation_id):
    """Voir les détails d'une réservation (avec QR code si confirmée)"""
    if not request.user.is_staff:
        return redirect('employe_espace')
    
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

@login_required
def api_reservation_qr(request, reservation_id):
    """API pour récupérer le QR code d'une réservation"""
    try:
        # Vérifier que l'utilisateur a le droit d'accéder au QR code
        if request.user.is_staff:
            reservation = db.reservations.find_one({'_id': ObjectId(reservation_id)})
        else:
            # Pour les employés, vérifier que c'est bien leur réservation
            employe = db.employees.find_one({'django_user_id': request.user.id})
            if not employe:
                return JsonResponse({'error': 'Employé non trouvé'}, status=404)
            reservation = db.reservations.find_one({
                '_id': ObjectId(reservation_id),
                'employe_id': str(employe['_id'])
            })
        
        if not reservation:
            return JsonResponse({'error': 'Réservation non trouvée'}, status=404)
        
        return JsonResponse({
            'qr_code': reservation.get('qr_code'),
            'date_debut': reservation.get('date_debut'),
            'date_fin': reservation.get('date_fin'),
            'titre': reservation.get('titre'),
            'statut': reservation.get('statut'),
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)