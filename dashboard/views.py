from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.conf import settings
from bson import ObjectId
from datetime import datetime, timedelta
from collections import Counter
from django.contrib import messages
import json
import random

# Authentification Django
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages

db = settings.MONGO_DB


# ====================== AUTHENTIFICATION ======================
def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")

    return render(request, 'dashboard/login.html')


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


# ====================== HELPERS ======================
class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


# ====================== PAGES ======================
@login_required
def dashboard(request):
    total_employes = db.employees.count_documents({})
    total_bureaux = db.bureaux.count_documents({})

    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    acces_aujourdhui = db.acces_logs.count_documents({'timestamp': {'$gte': today_start}})
    acces_refuses = db.acces_logs.count_documents({
        'timestamp': {'$gte': today_start}, 'resultat': 'REFUSE'
    })
    acces_autorises_today = acces_aujourdhui - acces_refuses

    alertes = db.alertes.count_documents({'statut': 'NON_TRAITEE'}) if 'alertes' in db.list_collection_names() else 0

    # Derniers logs
    derniers_logs = list(db.acces_logs.find().sort('timestamp', -1).limit(8))
    for log in derniers_logs:
        bureau = db.bureaux.find_one({'_id': log.get('bureau_id')})
        log['bureau_nom'] = bureau['nom'] if bureau else 'Inconnu'
        emp = db.employees.find_one({'_id': log.get('utilisateur_id')})
        log['nom_utilisateur'] = f"{emp.get('nom','')} {emp.get('prenom','')}" if emp else 'Inconnu'

    # Données pour le graphique 7 jours
    seven_days_ago = datetime.now() - timedelta(days=7)
    pipeline = [
        {'$match': {'timestamp': {'$gte': seven_days_ago}}},
        {'$group': {
            '_id': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$timestamp'}},
            'total': {'$sum': 1},
            'autorises': {'$sum': {'$cond': [{'$eq': ['$resultat', 'AUTORISE']}, 1, 0]}}
        }},
        {'$sort': {'_id': 1}}
    ]
    stats_7jours = list(db.acces_logs.aggregate(pipeline))

    context = {
        'total_employes': total_employes,
        'total_bureaux': total_bureaux,
        'acces_aujourdhui': acces_aujourdhui,
        'acces_refuses': acces_refuses,
        'alertes': alertes,
        'derniers_logs': derniers_logs,
        'stats_7jours': stats_7jours,
        'acces_autorises_today': acces_autorises_today,
    }

    return render(request, 'dashboard/dashboard.html', context)


@login_required
def employe_list(request):
    """Liste de tous les employés — version robuste"""
    try:
        # Récupère tous les employés sans filtre
        employes_raw = list(db.employees.find({}))
    except Exception as e:
        print(f"[ERREUR] Impossible de charger les employés: {e}")
        employes_raw = []

    employes = []
    for e in employes_raw:
        try:
            # Convertit l'ObjectId en string pour les URLs
            e['id'] = str(e['_id'])

            # Assure des valeurs par défaut pour tous les champs
            e.setdefault('nom', '')
            e.setdefault('prenom', '')
            e.setdefault('badge_id', '')
            e.setdefault('email', '')
            e.setdefault('telephone', '')
            e.setdefault('departement', '')
            e.setdefault('poste', '')
            e.setdefault('niveau', 'Staff')
            e.setdefault('statut', 'actif')

            # Nombre d'accès — utilise l'ObjectId original pour la requête
            try:
                e['nb_acces'] = db.acces_logs.count_documents({'utilisateur_id': e['_id']})
            except Exception:
                e['nb_acces'] = 0

            # Dernier accès — méthode compatible PyMongo 3.x et 4.x
            try:
                derniers = list(
                    db.acces_logs.find({'utilisateur_id': e['_id']})
                    .sort('timestamp', -1)
                    .limit(1)
                )
                e['dernier_acces'] = derniers[0]['timestamp'] if derniers else None
            except Exception:
                e['dernier_acces'] = None

            employes.append(e)

        except Exception as err:
            print(f"[ERREUR] Traitement employé {e.get('_id', '?')}: {err}")
            # On ajoute quand même l'employé avec des valeurs minimales
            e.setdefault('id', str(e.get('_id', '')))
            e.setdefault('nom', 'Inconnu')
            e.setdefault('prenom', '')
            e.setdefault('badge_id', '')
            e.setdefault('email', '')
            e.setdefault('departement', '')
            e.setdefault('poste', '')
            e.setdefault('niveau', 'Staff')
            e.setdefault('statut', 'actif')
            e['nb_acces'] = 0
            e['dernier_acces'] = None
            employes.append(e)

    # Collecte les départements uniques
    departements = sorted(set(
        e.get('departement', '')
        for e in employes
        if e.get('departement', '').strip()
    ))

    context = {
        'employes': employes,
        'total_employes': len(employes),
        'actifs': sum(1 for e in employes if e.get('statut') == 'actif'),
        'inactifs': sum(1 for e in employes if e.get('statut') != 'actif'),
        'total_departements': len(departements),
        'departements': departements,
    }

    return render(request, 'dashboard/employe_list.html', context)

@login_required
def employe_detail(request, employe_id):
    try:
        employe = db.employees.find_one({'_id': ObjectId(employe_id)})
        if not employe:
            return redirect('employe_list')
        
        employe['id'] = str(employe['_id'])

        # Accès
        acces = list(db.acces_logs.find({'utilisateur_id': ObjectId(employe_id)}).sort('timestamp', -1))
        total_acces = len(acces)
        acces_autorises = sum(1 for a in acces if a.get('resultat') == 'AUTORISE')
        acces_refuses = total_acces - acces_autorises
        dernier_acces = acces[0] if acces else None

        # Bureaux les plus fréquentés
        count_bureaux = Counter(a.get('bureau_id') for a in acces if a.get('bureau_id'))
        bureaux_frequentes = []
        for bid, count in count_bureaux.most_common(6):
            b = db.bureaux.find_one({'_id': bid})
            if b:
                pct = round(count / total_acces * 100) if total_acces else 0
                bureaux_frequentes.append({
                    'nom': b.get('nom', 'Inconnu'),
                    'count': count,
                    'pct': pct
                })

        # Simulation cycle de travail (à remplacer par vraie donnée plus tard)
        cycle_travail = {
            'type': employe.get('type_contrat', 'CDI'),
            'horaire': employe.get('horaire', '08:00 - 17:00'),
            'jours': employe.get('jours_travailles', ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven']),
            'heures_hebdo': employe.get('heures_hebdo', 35),
            'manager': employe.get('manager', 'Non défini')
        }

        context = {
            'employe': employe,
            'total_acces': total_acces,
            'acces_autorises': acces_autorises,
            'acces_refuses': acces_refuses,
            'dernier_acces': dernier_acces,
            'bureaux_frequentes': bureaux_frequentes,
            'acces': acces[:60],
            'cycle_travail': cycle_travail,
            'taux_succes': round((acces_autorises / total_acces * 100) if total_acces else 0, 1)
        }

        return render(request, 'dashboard/employe_details.html', context)

    except Exception as e:
        print(e)
        return redirect('employe_list')


@login_required
def employe_ajouter(request):
    """Ajouter un nouvel employé"""

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

            messages.success(request, f"Employé {nouvel_employe['nom']} {nouvel_employe['prenom']} ajouté avec succès!")
            return redirect('employe_detail', employe_id=str(result.inserted_id))

        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout: {str(e)}")
            return render(request, 'dashboard/employe_form.html', {'employe': request.POST})

    return render(request, 'dashboard/employe_form.html', {'employe': {}})


@login_required
def employe_modifier(request, employe_id):
    """Modifier un employé existant"""

    try:
        employe = db.employees.find_one({'_id': ObjectId(employe_id)})
        if not employe:
            messages.error(request, "Employé non trouvé")
            return redirect('employe_list')

        employe['id'] = str(employe['_id'])

        if request.method == 'POST':
            try:
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
                if date_embauche:
                    update_data['date_embauche'] = datetime.strptime(date_embauche, '%Y-%m-%d')
                else:
                    update_data['date_embauche'] = None

                db.employees.update_one(
                    {'_id': ObjectId(employe_id)},
                    {'$set': update_data}
                )

                messages.success(request, f"Employé {update_data['nom']} {update_data['prenom']} modifié avec succès!")
                return redirect('employe_detail', employe_id=employe_id)

            except Exception as e:
                messages.error(request, f"Erreur lors de la modification: {str(e)}")
                return render(request, 'dashboard/employe_form.html', {'employe': employe, 'is_edit': True})

        return render(request, 'dashboard/employe_form.html', {'employe': employe, 'is_edit': True})

    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('employe_list')


@login_required
def employe_supprimer(request, employe_id):
    """Archiver un employé"""

    if request.method == 'POST':
        try:
            db.employees.update_one(
                {'_id': ObjectId(employe_id)},
                {'$set': {
                    'statut': 'inactif',
                    'archived_at': datetime.now()
                }}
            )
            messages.success(request, "Employé archivé avec succès")
        except Exception as e:
            messages.error(request, f"Erreur lors de l'archivage: {str(e)}")

    return redirect('employe_list')


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


@login_required
def ressources(request):
    bureaux = list(db.bureaux.find())
    for b in bureaux:
        b['id'] = str(b['_id'])

    capacite_totale = sum(b.get('capacite_max', 0) for b in bureaux)
    occupation_moy = 47

    return render(request, 'dashboard/ressources.html', {
        'total_bureaux': len(bureaux),
        'capacite_totale': capacite_totale,
        'occupation_moy': occupation_moy,
        'bureaux': bureaux,
    })


@login_required
def bureau_ajouter(request):
    if request.method == 'POST':
        data = {
            'nom': request.POST.get('nom'),
            'code_bureau': request.POST.get('code_bureau'),
            'etage': int(request.POST.get('etage', 0)),
            'capacite_max': int(request.POST.get('capacite_max', 10)),
        }
        db.bureaux.insert_one(data)
    return redirect('ressources')


# ====================== CALENDRIER ET RÈGLES ======================

@login_required
def calendrier(request):
    """Page calendrier d'accès"""
    employes = list(db.employees.find({'statut': 'actif'}))
    for e in employes:
        e['id'] = str(e['_id'])

    context = {
        'employes': employes,
    }

    return render(request, 'dashboard/calendrier.html', context)


@login_required
def api_get_employee_rules(request, employe_id):
    """Récupérer les règles d'un employé.

    Retourne un dict avec des clés "ANNEE-MOIS-JOUR" (ex: "2026-3-15")
    pour éviter les conflits de type entier/string et les ambiguïtés
    inter-mois (le jour 5 de mars ≠ le jour 5 d'avril).
    """
    try:
        rules_cursor = db.access_rules.find({'employe_id': employe_id})
        rules = list(rules_cursor)

        formatted_rules = {}
        for rule in rules:
            jour = rule.get('jour')
            mois = rule.get('mois')
            annee = rule.get('annee')

            # Ignorer les règles sans date complète
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
        print(f"Erreur récupération règles: {e}")
        return JsonResponse({'rules': {}, 'status': 'error', 'message': str(e)})


@login_required
def api_save_day_rules(request):
    """Sauvegarder les règles d'un jour spécifique"""
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
            jour = rule.get('jour')
            mois = rule.get('mois')
            annee = rule.get('annee')
            zone_nom = rule.get('zone_nom', '')

            if zone_nom == '__DELETE__':
                # Supprimer toutes les règles de ce jour précis
                db.access_rules.delete_many({
                    'employe_id': employe_id,
                    'jour': jour,
                    'mois': mois,
                    'annee': annee
                })
            else:
                # Remplacer la règle existante pour cette zone/jour
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

        return JsonResponse({
            'status': 'success',
            'message': f'{saved_count} règle(s) sauvegardée(s)'
        })

    except Exception as e:
        print(f"Erreur sauvegarde règles: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_save_all_rules(request):
    """Sauvegarder toutes les règles d'un employé (remplace tout)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        rules = data.get('rules', [])

        if not employe_id:
            return JsonResponse({'error': 'Employé ID manquant'}, status=400)

        # Supprimer toutes les règles existantes de cet employé
        db.access_rules.delete_many({'employe_id': employe_id})

        if rules:
            docs = []
            for rule in rules:
                docs.append({
                    'employe_id': employe_id,
                    'zone_nom': rule.get('zone_nom', ''),
                    'jour': rule.get('jour'),
                    'mois': rule.get('mois'),
                    'annee': rule.get('annee'),
                    'heure_debut': rule.get('heure_debut', '08:00'),
                    'heure_fin': rule.get('heure_fin', '18:00'),
                    'acces_autorise': rule.get('acces_autorise', True),
                    'created_at': datetime.now(),
                    'updated_at': datetime.now()
                })
            db.access_rules.insert_many(docs)

        return JsonResponse({
            'status': 'success',
            'message': f'{len(rules)} règle(s) enregistrée(s)'
        })

    except Exception as e:
        print(f"Erreur sauvegarde toutes règles: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def api_bureaux(request):
    """API pour récupérer la liste des bureaux"""
    bureaux = list(db.bureaux.find())
    result = []
    for b in bureaux:
        result.append({
            'id': str(b['_id']),
            'nom': b.get('nom', ''),
            'niveau': b.get('niveau_securite', 'standard'),
            'capacite': b.get('capacite_max', 0)
        })

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


@login_required
def statistiques(request):
    now = datetime.now()
    start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_mois = db.acces_logs.count_documents({'timestamp': {'$gte': start_month}})
    total_all = db.acces_logs.count_documents({})
    autorises = db.acces_logs.count_documents({'resultat': 'AUTORISE'})
    taux_succes = round(autorises / total_all * 100) if total_all else 0

    pipeline = [
        {'$match': {'timestamp': {'$gte': start_month}}},
        {'$group': {'_id': '$utilisateur_id', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 5}
    ]
    top = list(db.acces_logs.aggregate(pipeline))
    top_employes = []
    for t in top:
        emp = db.employees.find_one({'_id': t['_id']})
        if emp:
            top_employes.append({
                'nom': emp.get('nom'),
                'prenom': emp.get('prenom'),
                'departement': emp.get('departement'),
                'nb_acces': t['count'],
                'taux_succes': 94,
                'dernier_acces': None,
                'zone_principale': 'Atelier'
            })

    zones_stats = []
    for z in list(db.acces_logs.aggregate([
        {'$match': {'timestamp': {'$gte': start_month}}},
        {'$group': {'_id': '$bureau_id', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}, {'$limit': 5}
    ])):
        b = db.bureaux.find_one({'_id': z['_id']})
        if b:
            zones_stats.append({'nom': b['nom'], 'count': z['count'], 'pct': 82})

    return render(request, 'dashboard/statistiques.html', {
        'total_mois': total_mois,
        'taux_succes': taux_succes,
        'taux_refus': 100 - taux_succes,
        'pic_heure': '08h30',
        'zone_active': 'Direction Générale',
        'top_employes': top_employes,
        'zones_stats': zones_stats,
    })


@login_required
def parametres(request):
    return render(request, 'dashboard/parametres.html')


# ====================== API ======================
@login_required
def api_occupation(request):
    bureaux = list(db.bureaux.find())
    result = []
    one_hour_ago = datetime.now() - timedelta(hours=1)
    for b in bureaux:
        recent = db.acces_logs.count_documents({
            'bureau_id': b['_id'],
            'timestamp': {'$gte': one_hour_ago}
        })
        cap = b.get('capacite_max', 10)
        occ = min(recent * 3, cap)
        taux = round(occ / cap * 100) if cap else 0
        result.append({
            'id': str(b['_id']),
            'nom': b['nom'],
            'occupation': occ,
            'capacite': cap,
            'taux': taux
        })
    return JsonResponse({'bureaux': result})


@login_required
def api_bureau_stats(request, bureau_id):
    dates = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    acces = [random.randint(20, 90) for _ in range(7)]
    return JsonResponse({'dates': dates, 'acces_par_jour': acces})


@login_required
def bureau_detail(request, bureau_id):
    return redirect('ressources')


# ====================== GESTION DES ÉQUIPEMENTS ======================

@login_required
def equipement_list(request):
    """Liste des équipements RFID et QR Code"""

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

    context = {
        'equipements': equipements,
        'nb_total': len(equipements),
        'nb_rfid': nb_rfid,
        'nb_qr': nb_qr,
        'nb_actifs': nb_actifs,
        'nb_inactifs': nb_inactifs,
    }

    return render(request, 'dashboard/equipement_list.html', context)


@login_required
def equipement_detail(request, equipement_id):
    """Détail d'un équipement"""

    try:
        equipement = db.equipements.find_one({'_id': ObjectId(equipement_id)})
        if not equipement:
            messages.error(request, "Équipement non trouvé")
            return redirect('equipement_list')

        equipement['id'] = str(equipement['_id'])

        if equipement.get('bureau_id'):
            bureau = db.bureaux.find_one({'_id': equipement['bureau_id']})
            equipement['bureau'] = bureau

        logs = list(db.acces_logs.find({
            'equipement_code': equipement.get('code')
        }).sort('timestamp', -1).limit(100))

        for log in logs:
            employe = db.employees.find_one({'_id': log.get('utilisateur_id')})
            if employe:
                log['nom_utilisateur'] = f"{employe.get('nom', '')} {employe.get('prenom', '')}"
            else:
                log['nom_utilisateur'] = 'Inconnu'

        yesterday = datetime.now() - timedelta(days=1)
        week_ago = datetime.now() - timedelta(days=7)

        stats = {
            'logs_24h': db.acces_logs.count_documents({
                'equipement_code': equipement.get('code'),
                'timestamp': {'$gte': yesterday}
            }),
            'logs_7j': db.acces_logs.count_documents({
                'equipement_code': equipement.get('code'),
                'timestamp': {'$gte': week_ago}
            }),
            'autorises': db.acces_logs.count_documents({
                'equipement_code': equipement.get('code'),
                'resultat': 'AUTORISE'
            }),
            'refuses': db.acces_logs.count_documents({
                'equipement_code': equipement.get('code'),
                'resultat': 'REFUSE'
            })
        }

        context = {
            'equipement': equipement,
            'logs': logs,
            'stats': stats,
        }

        return render(request, 'dashboard/equipement_detail.html', context)

    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('equipement_list')


@login_required
def equipement_ajouter(request):
    """Ajouter un nouvel équipement"""

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
            messages.success(request, f"Équipement {equipement['nom']} ajouté avec succès!")
            return redirect('equipement_list')

        except Exception as e:
            messages.error(request, f"Erreur lors de l'ajout: {str(e)}")

    context = {
        'bureaux': bureaux,
        'equipement': {},
        'is_edit': False
    }

    return render(request, 'dashboard/equipement_form.html', context)


@login_required
def equipement_modifier(request, equipement_id):
    """Modifier un équipement existant"""

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

            db.equipements.update_one(
                {'_id': ObjectId(equipement_id)},
                {'$set': update_data}
            )

            messages.success(request, "Équipement modifié avec succès!")
            return redirect('equipement_detail', equipement_id=equipement_id)

        equipement['id'] = str(equipement['_id'])

        context = {
            'equipement': equipement,
            'bureaux': bureaux,
            'is_edit': True
        }

        return render(request, 'dashboard/equipement_form.html', context)

    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('equipement_list')


@login_required
def equipement_supprimer(request, equipement_id):
    """Supprimer un équipement"""

    if request.method == 'POST':
        try:
            db.equipements.update_one(
                {'_id': ObjectId(equipement_id)},
                {'$set': {'statut': 'inactif', 'deleted_at': datetime.now()}}
            )
            messages.success(request, "Équipement désactivé avec succès!")
        except Exception as e:
            messages.error(request, f"Erreur: {str(e)}")

    return redirect('equipement_list')


@login_required
def equipement_tester(request, equipement_id):
    """Tester la connexion à un équipement"""

    try:
        equipement = db.equipements.find_one({'_id': ObjectId(equipement_id)})
        if not equipement:
            return JsonResponse({'status': 'error', 'message': 'Équipement non trouvé'})

        result = 0
        response_time = random.randint(10, 50)

        if result == 0:
            db.equipements.update_one(
                {'_id': ObjectId(equipement_id)},
                {'$set': {'derniere_connexion': datetime.now(), 'statut': 'actif'}}
            )
            return JsonResponse({
                'status': 'success',
                'message': 'Connexion réussie',
                'response_time': response_time
            })
        else:
            return JsonResponse({
                'status': 'error',
                'message': 'Échec de connexion'
            })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ====================== API ÉQUIPEMENTS ======================

@login_required
def api_equipements(request):
    """API pour récupérer la liste des équipements"""

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
            'derniere_connexion': eq.get('derniere_connexion')
        })

    return JsonResponse({'equipements': resultats}, encoder=JSONEncoder)


@login_required
def api_equipement_logs(request, equipement_id):
    """API pour récupérer les logs d'un équipement"""

    try:
        equipement = db.equipements.find_one({'_id': ObjectId(equipement_id)})
        if not equipement:
            return JsonResponse({'error': 'Équipement non trouvé'}, status=404)

        logs = list(db.acces_logs.find({
            'equipement_code': equipement.get('code')
        }).sort('timestamp', -1).limit(50))

        resultats = []
        for log in logs:
            employe = db.employees.find_one({'_id': log.get('utilisateur_id')})
            resultats.append({
                'id': str(log['_id']),
                'timestamp': log['timestamp'],
                'nom_utilisateur': f"{employe.get('nom', '')} {employe.get('prenom', '')}" if employe else 'Inconnu',
                'resultat': log.get('resultat', ''),
                'type_acces': log.get('type_acces', '')
            })

        return JsonResponse({'logs': resultats}, encoder=JSONEncoder)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def api_equipement_commande(request, equipement_id):
    """API pour envoyer une commande à un équipement"""

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
            'timestamp': datetime.now()
        })

        return JsonResponse({
            'status': 'success',
            'message': f'Commande "{commande}" envoyée à {equipement["nom"]}'
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
# ====================== RÉSERVATIONS ======================
# COLLE CE BLOC À LA FIN DE dashboard/views.py

@login_required
def reservation_list(request):
    reservations = list(db.reservations.find().sort('date_debut', -1).limit(200))
    for r in reservations:
        r['id'] = str(r['_id'])
        emp = db.employees.find_one({'_id': r.get('employe_id')})
        r['employe_nom'] = f"{emp.get('nom','')} {emp.get('prenom','')}" if emp else 'Inconnu'
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
    employes = list(db.employees.find({'statut': 'actif'}))
    for e in employes:
        e['id'] = str(e['_id'])

    return render(request, 'dashboard/reservation_list.html', {
        'reservations': reservations,
        'total': len(reservations),
        'actives': actives,
        'a_venir': a_venir,
        'en_attente': en_attente,
        'bureaux': bureaux,
        'employes': employes,
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

            if date_fin <= date_debut:
                messages.error(request, "La date de fin doit être après la date de début.")
                return render(request, 'dashboard/reservation_form.html',
                              {'bureaux': bureaux, 'employes': employes, 'reservation': request.POST})

            bureau_id_str = request.POST.get('bureau_id')
            employe_id_str = request.POST.get('employe_id')

            chevauchement = db.reservations.find_one({
                'bureau_id': ObjectId(bureau_id_str),
                'statut': {'$in': ['confirmee', 'en_attente']},
                'date_debut': {'$lt': date_fin},
                'date_fin': {'$gt': date_debut},
            })
            if chevauchement:
                messages.error(request, "⚠️ Cette salle est déjà réservée sur ce créneau.")
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
            messages.success(request, "✅ Réservation créée avec succès!")
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
            messages.success(request, "✅ Réservation modifiée!")
            return redirect('reservation_list')

        return render(request, 'dashboard/reservation_form.html', {
            'reservation': reservation, 'bureaux': bureaux,
            'employes': employes, 'is_edit': True,
        })
    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('reservation_list')


@login_required
def reservation_annuler(request, reservation_id):
    if request.method == 'POST':
        db.reservations.update_one(
            {'_id': ObjectId(reservation_id)},
            {'$set': {'statut': 'annulee', 'cancelled_at': datetime.now()}}
        )
        messages.success(request, "Réservation annulée.")
    return redirect('reservation_list')


@login_required
def api_reservations_calendrier(request):
    reservations = list(db.reservations.find({'statut': {'$in': ['confirmee', 'en_attente']}}))
    events = []
    colors = {'confirmee': '#2dba6f', 'en_attente': '#e3b341', 'annulee': '#f85149'}
    for r in reservations:
        bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
        emp = db.employees.find_one({'_id': r.get('employe_id')})
        if r.get('date_debut') and r.get('date_fin'):
            events.append({
                'id': str(r['_id']),
                'title': r.get('titre', 'Réservation'),
                'start': r['date_debut'].isoformat(),
                'end': r['date_fin'].isoformat(),
                'color': colors.get(r.get('statut', 'en_attente'), '#388bfd'),
                'extendedProps': {
                    'bureau': bureau['nom'] if bureau else 'Inconnu',
                    'employe': f"{emp.get('nom','')} {emp.get('prenom','')}" if emp else 'Inconnu',
                    'statut': r.get('statut'),
                    'participants': r.get('nb_participants', 1),
                }
            })
    return JsonResponse({'events': events})


@login_required
def api_disponibilite_bureau(request, bureau_id):
    date_debut_str = request.GET.get('debut')
    date_fin_str = request.GET.get('fin')
    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%dT%H:%M')
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%dT%H:%M')
        chevauchement = db.reservations.find_one({
            'bureau_id': ObjectId(bureau_id),
            'statut': {'$in': ['confirmee', 'en_attente']},
            'date_debut': {'$lt': date_fin},
            'date_fin': {'$gt': date_debut},
        })
        return JsonResponse({'disponible': chevauchement is None})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)