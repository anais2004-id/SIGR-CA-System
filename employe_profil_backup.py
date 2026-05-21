def employe_profil(request):
    """Modification du profil employ├®"""
    if request.user.is_staff:
        return redirect('dashboard')
    
    from datetime import datetime, timedelta
    
    # R├®cup├®rer l'employ├®
    employe = db.employees.find_one({'django_user_id': request.user.id})
    if not employe:
        employe = db.employees.find_one({'django_username': request.user.username})
    
    if not employe:
        messages.error(request, "Profil employ├® introuvable.")
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
    
    # Acc├¿s du mois
    start_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    acces_mois = db.acces_logs.count_documents({
        'utilisateur_id': utilisateur_id,
        'timestamp': {'$gte': start_month}
    })
    
    # Dernier acc├¿s
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
    
    # Pr├®f├®rences
    preferences = employe.get('preferences_notifications', {})
    if not preferences:
        preferences = {'email': True, 'rappel': True}
    
    # R├®cup├®rer les sessions actives de l'utilisateur
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
                'ip_address': session.ip_address or 'ÔÇö',
                'login_time': session.login_time.strftime('%d/%m/%Y %H:%M:%S'),
                'last_activity': session.last_activity.strftime('%d/%m/%Y %H:%M:%S'),
                'is_current': session.session_key == request.session.session_key
            })
    except:
        active_sessions = []
    
    # Traitement POST
    if request.method == 'POST':
        # V├®rifier quelle action est demand├®e
        if 'change_password' in request.POST:
            # Changement de mot de passe
            old_password = request.POST.get('old_password', '')
            new_password1 = request.POST.get('new_password1', '')
            new_password2 = request.POST.get('new_password2', '')
            
            if not request.user.check_password(old_password):
                messages.error(request, "L'ancien mot de passe est incorrect.")
            elif len(new_password1) < 6:
                messages.error(request, "Le nouveau mot de passe doit contenir au moins 6 caract├¿res.")
            elif new_password1 != new_password2:
                messages.error(request, "Les mots de passe ne correspondent pas.")
            else:
                request.user.set_password(new_password1)
                request.user.save()
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                messages.success(request, "Mot de passe chang├® avec succ├¿s.")
            
            return redirect('employe_profil')
        
        elif 'update_preferences' in request.POST:
            # Mise ├á jour des pr├®f├®rences
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
            messages.success(request, "Pr├®f├®rences mises ├á jour.")
            return redirect('employe_profil')
        
        else:
            # Mise ├á jour du profil
            try:
                prenom = request.POST.get('prenom', '').strip()
                nom = request.POST.get('nom', '').strip()
                email = request.POST.get('email', '').strip()
                telephone = request.POST.get('telephone', '').strip()
                poste = request.POST.get('poste', '').strip()
                departement = request.POST.get('departement', '').strip()
                
                if not prenom or not nom:
                    messages.error(request, "Le nom et le pr├®nom sont requis.")
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
                
                # Mettre ├á jour l'utilisateur Django
                user = request.user
                user.first_name = prenom
                user.last_name = nom
                user.email = email
                user.save()
                
                messages.success(request, "Profil mis ├á jour avec succ├¿s.")
                
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
