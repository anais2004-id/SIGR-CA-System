# Créez un script Python : sync_sessions.py
# Exécutez-le avec : python manage.py runscript sync_sessions

from django.contrib.sessions.models import Session
from django.contrib.auth import get_user_model
from dashboard.models import UserSession
from django.utils.timezone import now
import json

User = get_user_model()

def run():
    """Synchronise toutes les sessions Django existantes avec UserSession"""
    
    print("🔄 Synchronisation des sessions...")
    
    # Récupérer toutes les sessions actives de Django
    all_sessions = Session.objects.filter(expire_date__gt=now())
    
    count_created = 0
    count_updated = 0
    
    for session in all_sessions:
        try:
            # Décoder les données de session
            session_data = session.get_decoded()
            user_id = session_data.get('_auth_user_id')
            
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    
                    # Créer ou mettre à jour UserSession
                    user_session, created = UserSession.objects.update_or_create(
                        session_key=session.session_key,
                        defaults={
                            'user': user,
                            'last_activity': session.expire_date,
                            'is_active': True,
                            'ip_address': 'unknown',  # IP non disponible rétroactivement
                            'user_agent': 'legacy_session',
                        }
                    )
                    
                    if created:
                        count_created += 1
                        print(f"  ✅ Session créée pour {user.username}")
                    else:
                        count_updated += 1
                        
                except User.DoesNotExist:
                    pass
                    
        except Exception as e:
            print(f"  ❌ Erreur: {e}")
    
    print(f"\n📊 Résultat: {count_created} sessions créées, {count_updated} mises à jour")