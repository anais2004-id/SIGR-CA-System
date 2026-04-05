from django.utils.timezone import now
from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.contrib.sessions.models import Session
import json
import requests

User = get_user_model()

class UserSessionMiddleware:
    """Middleware pour capturer TOUTES les sessions utilisateur sur TOUS les PC"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Traitement avant la vue
        response = self.get_response(request)
        
        # Capturer les sessions pour les utilisateurs authentifiés
        if request.user.is_authenticated and not request.user.is_anonymous:
            session_key = request.session.session_key
            
            if session_key:
                try:
                    from .models import UserSession, SessionLog
                    
                    # Mettre à jour ou créer la session
                    user_session, created = UserSession.objects.update_or_create(
                        session_key=session_key,
                        defaults={
                            'user': request.user,
                            'ip_address': self.get_client_ip(request),
                            'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
                            'last_activity': now(),
                            'is_active': True,
                            'device_type': self.get_device_type(request),
                            'location': self.get_location_from_ip(self.get_client_ip(request)),
                        }
                    )
                    
                    if created:
                        user_session.login_time = now()
                        user_session.save()
                        
                        # Log de connexion
                        SessionLog.objects.create(
                            user=request.user,
                            action='login',
                            ip_address=user_session.ip_address,
                            user_agent=user_session.user_agent,
                            session_key=session_key
                        )
                        
                except OperationalError:
                    pass
                except Exception as e:
                    print(f"Erreur middleware session: {e}")
        
        return response
    
    def get_client_ip(self, request):
        """Récupère l'IP réelle du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_device_type(self, request):
        """Détecte le type d'appareil"""
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        
        if 'mobile' in user_agent or 'android' in user_agent or 'iphone' in user_agent:
            return 'mobile'
        elif 'tablet' in user_agent or 'ipad' in user_agent:
            return 'tablet'
        else:
            return 'desktop'
    
    def get_location_from_ip(self, ip):
        """Obtenir la localisation approximative à partir de l'IP"""
        if not ip or ip.startswith('127.') or ip.startswith('192.168.'):
            return 'Local'
        try:
            # API gratuite pour la géolocalisation
            response = requests.get(f'http://ip-api.com/json/{ip}', timeout=2)
            data = response.json()
            if data.get('status') == 'success':
                return f"{data.get('city', '')}, {data.get('countryCode', '')}"
        except:
            pass
        return None