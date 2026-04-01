# dashboard/middleware.py
from django.utils.timezone import now
from django.contrib.auth import get_user_model
from django.db import OperationalError

User = get_user_model()

class UserSessionMiddleware:
    """Middleware pour capturer les sessions utilisateur"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        response = self.get_response(request)
        
        # Capturer les sessions pour les utilisateurs authentifiés
        if request.user.is_authenticated and not request.user.is_anonymous:
            session_key = request.session.session_key
            
            if session_key:
                try:
                    from .models import UserSession
                    
                    # Vérifier si la table existe
                    try:
                        user_session, created = UserSession.objects.get_or_create(
                            session_key=session_key,
                            defaults={
                                'user': request.user,
                                'ip_address': self.get_client_ip(request),
                                'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
                                'last_activity': now(),
                                'login_time': now(),
                                'is_active': True,
                            }
                        )
                        
                        if not created:
                            user_session.last_activity = now()
                            user_session.user = request.user  # Mettre à jour l'utilisateur
                            user_session.ip_address = self.get_client_ip(request)
                            user_session.user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
                            user_session.is_active = True
                            user_session.save()
                            
                    except OperationalError:
                        # La table n'existe pas encore, ignorer
                        pass
                        
                except Exception as e:
                    print(f"Erreur middleware session: {e}")
        
        return response
    
    def get_client_ip(self, request):
        """Récupère l'IP du client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip