# dashboard/views.py
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from bson import ObjectId
import json
from datetime import datetime, timedelta
import random

# Helper pour convertir ObjectId en string
class JSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)

# Connexion MongoDB
db = settings.MONGO_DB

def dashboard(request):
    """Page principale du dashboard"""
    
    # Récupérer les statistiques pour les KPIs
    total_employes = db.employees.count_documents({})
    total_bureaux = db.bureaux.count_documents({})
    
    # Compter les accès aujourd'hui
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    acces_aujourdhui = db.acces_logs.count_documents({
        'timestamp': {'$gte': today_start}
    })
    
    # Compter les alertes actives
    alertes = db.alertes.count_documents({'statut': 'NON_TRAITEE'}) if 'alertes' in db.list_collection_names() else 0
    
    # Récupérer les derniers logs
    derniers_logs = list(db.acces_logs.find().sort('timestamp', -1).limit(10))
    
    # Récupérer tous les bureaux et AJOUTER L'ID COMME CHAMP SÉPARÉ
    bureaux = list(db.bureaux.find())
    for bureau in bureaux:
        bureau['id'] = str(bureau['_id'])  # Ajouter l'ID comme champ séparé
    
    context = {
        'total_employes': total_employes,
        'total_bureaux': total_bureaux,
        'acces_aujourdhui': acces_aujourdhui,
        'alertes': alertes,
        'derniers_logs': derniers_logs,
        'bureaux': bureaux,
    }
    
    return render(request, 'dashboard/dashboard.html', context)

def api_occupation(request):
    """API pour récupérer l'occupation en temps réel"""
    
    bureaux = list(db.bureaux.find())
    resultats = []
    
    for bureau in bureaux:
        occupation = random.randint(0, bureau.get('capacite_max', 10))
        
        resultats.append({
            'id': str(bureau['_id']),  # Important : 'id' pas '_id'
            'nom': bureau.get('nom', ''),
            'code': bureau.get('code_bureau', ''),
            'etage': bureau.get('etage', 0),
            'capacite': bureau.get('capacite_max', 0),
            'occupation': occupation,
            'taux': round((occupation / bureau.get('capacite_max', 1)) * 100, 1)
        })
    
    return JsonResponse({'bureaux': resultats}, encoder=JSONEncoder)

def api_stats(request):
    """API pour les statistiques des graphiques"""
    
    # Statistiques des 7 derniers jours
    dates = []
    acces_par_jour = []
    
    for i in range(6, -1, -1):
        date = datetime.now() - timedelta(days=i)
        date_str = date.strftime('%d/%m')
        dates.append(date_str)
        
        jour_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        jour_end = jour_start + timedelta(days=1)
        
        count = db.acces_logs.count_documents({
            'timestamp': {'$gte': jour_start, '$lt': jour_end}
        })
        acces_par_jour.append(count)
    
    # Répartition par type d'accès
    types_acces = {
        'RFID': db.acces_logs.count_documents({'type_acces': 'RFID'}),
        'QR Code': db.acces_logs.count_documents({'type_acces': 'QR'})
    }
    
    return JsonResponse({
        'dates': dates,
        'acces_par_jour': acces_par_jour,
        'types_acces': types_acces
    }, encoder=JSONEncoder)

def bureau_detail(request, bureau_id):
    """Page de détail d'un bureau"""
    
    bureau = db.bureaux.find_one({'_id': ObjectId(bureau_id)})
    if not bureau:
        return render(request, '404.html', status=404)
    
    # Récupérer les logs pour ce bureau
    logs = list(db.acces_logs.find(
        {'bureau_id': ObjectId(bureau_id)}
    ).sort('timestamp', -1).limit(50))
    
    context = {
        'bureau': bureau,
        'logs': logs
    }
    
    return render(request, 'dashboard/bureau_detail.html', context)
    # ============================================
# VUES POUR LA GESTION DES EMPLOYÉS
# ============================================

def employe_list(request):
    """Liste de tous les employés"""
    employes = list(db.employees.find())
    
    # Statistiques
    total_employes = len(employes)
    actifs = 0
    inactifs = 0
    departements = set()
    
    # Ajouter l'ID comme champ séparé
    for emp in employes:
        emp['id'] = str(emp['_id'])
        
        # Compter le statut
        if emp.get('statut') == 'actif':
            actifs += 1
        else:
            inactifs += 1
            
        # Ajouter le département
        if emp.get('departement'):
            departements.add(emp['departement'])
        
        # Compter le nombre d'accès de l'employé
        emp['nb_acces'] = db.acces_logs.count_documents({'utilisateur_id': emp['_id']})
        
        # Dernier accès
        dernier_acces = db.acces_logs.find_one(
            {'utilisateur_id': emp['_id']},
            sort=[('timestamp', -1)]
        )
        emp['dernier_acces'] = dernier_acces['timestamp'] if dernier_acces else None
    
    context = {
        'employes': employes,
        'total_employes': total_employes,
        'actifs': actifs,
        'inactifs': inactifs,
        'total_departements': len(departements),
        'departements': list(departements),
    }
    
    return render(request, 'dashboard/employe_list.html', context)

def employe_detail(request, employe_id):
    """Détail d'un employé"""
    try:
        employe = db.employees.find_one({'_id': ObjectId(employe_id)})
        if not employe:
            return render(request, '404.html', {'message': 'Employé non trouvé'}, status=404)
        
        employe['id'] = str(employe['_id'])
        
        # Récupérer les accès de l'employé
        acces = list(db.acces_logs.find(
            {'utilisateur_id': employe['_id']}
        ).sort('timestamp', -1).limit(100))
        
        # Statistiques
        total_acces = len(acces)
        acces_autorises = sum(1 for a in acces if a.get('resultat') == 'AUTORISE')
        acces_refuses = total_acces - acces_autorises
        
        # Dernier accès
        dernier_acces = acces[0] if acces else None
        
        # Bureaux les plus fréquentés
        bureaux_frequentes = list(db.acces_logs.aggregate([
            {'$match': {'utilisateur_id': employe['_id']}},
            {'$group': {'_id': '$bureau_id', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 5}
        ]))
        
        # Récupérer les noms des bureaux
        for b in bureaux_frequentes:
            bureau = db.bureaux.find_one({'_id': b['_id']})
            b['nom'] = bureau['nom'] if bureau else 'Inconnu'
        
        context = {
            'employe': employe,
            'acces': acces,
            'total_acces': total_acces,
            'acces_autorises': acces_autorises,
            'acces_refuses': acces_refuses,
            'dernier_acces': dernier_acces,
            'bureaux_frequentes': bureaux_frequentes
        }
        
        return render(request, 'dashboard/employe_detail.html', context)
    
    except Exception as e:
        return render(request, '404.html', {'message': str(e)}, status=404)

def employe_ajouter(request):
    """Ajouter un nouvel employé"""
    if request.method == 'POST':
        # Récupérer les données du formulaire
        nouvel_employe = {
            'badge_id': request.POST.get('badge_id'),
            'nom': request.POST.get('nom'),
            'prenom': request.POST.get('prenom'),
            'email': request.POST.get('email'),
            'telephone': request.POST.get('telephone'),
            'departement': request.POST.get('departement'),
            'poste': request.POST.get('poste'),
            'date_embauche': request.POST.get('date_embauche'),
            'statut': 'actif',
            'created_at': datetime.now()
        }
        
        # Vérifier si le badge_id existe déjà
        existant = db.employees.find_one({'badge_id': nouvel_employe['badge_id']})
        if existant:
            return render(request, 'dashboard/employe_form.html', {
                'error': 'Ce badge ID existe déjà',
                'employe': nouvel_employe
            })
        
        # Insérer dans MongoDB
        result = db.employees.insert_one(nouvel_employe)
        
        return redirect('employe_detail', employe_id=str(result.inserted_id))
    
    # GET - Afficher le formulaire vide
    return render(request, 'dashboard/employe_form.html', {'employe': {}})

def employe_modifier(request, employe_id):
    """Modifier un employé existant"""
    try:
        employe = db.employees.find_one({'_id': ObjectId(employe_id)})
        if not employe:
            return render(request, '404.html', {'message': 'Employé non trouvé'}, status=404)
        
        employe['id'] = str(employe['_id'])
        
        if request.method == 'POST':
            # Mettre à jour les données
            update_data = {
                'badge_id': request.POST.get('badge_id'),
                'nom': request.POST.get('nom'),
                'prenom': request.POST.get('prenom'),
                'email': request.POST.get('email'),
                'telephone': request.POST.get('telephone'),
                'departement': request.POST.get('departement'),
                'poste': request.POST.get('poste'),
                'date_embauche': request.POST.get('date_embauche'),
                'statut': request.POST.get('statut'),
                'updated_at': datetime.now()
            }
            
            db.employees.update_one(
                {'_id': ObjectId(employe_id)},
                {'$set': update_data}
            )
            
            return redirect('employe_detail', employe_id=employe_id)
        
        # GET - Afficher le formulaire avec les données existantes
        return render(request, 'dashboard/employe_form.html', {'employe': employe})
    
    except Exception as e:
        return render(request, '404.html', {'message': str(e)}, status=404)

def employe_supprimer(request, employe_id):
    """Supprimer un employé"""
    if request.method == 'POST':
        try:
            # Supprimer l'employé
            db.employees.delete_one({'_id': ObjectId(employe_id)})
            
            # Optionnel : Supprimer aussi ses logs d'accès
            # db.acces_logs.delete_many({'utilisateur_id': ObjectId(employe_id)})
            
            return redirect('employe_list')
        except Exception as e:
            return render(request, '404.html', {'message': str(e)}, status=404)
    
    # GET - Afficher la page de confirmation
    employe = db.employees.find_one({'_id': ObjectId(employe_id)})
    if not employe:
        return render(request, '404.html', {'message': 'Employé non trouvé'}, status=404)
    
    employe['id'] = str(employe['_id'])
    return render(request, 'dashboard/employe_confirm_delete.html', {'employe': employe})

def api_employes(request):
    """API pour récupérer la liste des employés (format JSON)"""
    employes = list(db.employees.find())
    resultats = []
    
    for emp in employes:
        resultats.append({
            'id': str(emp['_id']),
            'badge_id': emp.get('badge_id', ''),
            'nom': emp.get('nom', ''),
            'prenom': emp.get('prenom', ''),
            'email': emp.get('email', ''),
            'departement': emp.get('departement', ''),
            'poste': emp.get('poste', ''),
            'statut': emp.get('statut', 'actif')
        })
    
    return JsonResponse({'employes': resultats}, encoder=JSONEncoder)

def api_employe_acces(request, employe_id):
    """API pour récupérer les accès d'un employé"""
    try:
        acces = list(db.acces_logs.find(
            {'utilisateur_id': ObjectId(employe_id)}
        ).sort('timestamp', -1).limit(50))
        
        resultats = []
        for a in acces:
            bureau = db.bureaux.find_one({'_id': a['bureau_id']})
            resultats.append({
                'id': str(a['_id']),
                'timestamp': a['timestamp'],
                'bureau_nom': bureau['nom'] if bureau else 'Inconnu',
                'type_acces': a.get('type_acces', ''),
                'action': a.get('action', ''),
                'resultat': a.get('resultat', '')
            })
        
        return JsonResponse({'acces': resultats}, encoder=JSONEncoder)
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_bureau_stats(request, bureau_id):
    """API pour les statistiques détaillées d'un bureau"""
    try:
        # Statistiques des 7 derniers jours
        dates = []
        acces_par_jour = []
        
        for i in range(6, -1, -1):
            date = datetime.now() - timedelta(days=i)
            date_str = date.strftime('%d/%m')
            dates.append(date_str)
            
            jour_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            jour_end = jour_start + timedelta(days=1)
            
            count = db.acces_logs.count_documents({
                'bureau_id': ObjectId(bureau_id),
                'timestamp': {'$gte': jour_start, '$lt': jour_end}
            })
            acces_par_jour.append(count)
        
        # Personnes actuellement dans le bureau (simulé)
        personnes_presentes = list(db.acces_logs.aggregate([
            {'$match': {
                'bureau_id': ObjectId(bureau_id),
                'timestamp': {'$gte': datetime.now() - timedelta(hours=2)}
            }},
            {'$group': {'_id': '$utilisateur_id', 'nom': {'$first': '$nom_utilisateur'}}},
            {'$limit': 10}
        ]))
        
        return JsonResponse({
            'dates': dates,
            'acces_par_jour': acces_par_jour,
            'personnes_presentes': personnes_presentes
        }, encoder=JSONEncoder)
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)