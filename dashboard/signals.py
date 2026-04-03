# dashboard/signals.py (créez ce fichier)

from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver
from django.utils.timezone import now
from .models import UserSession

@receiver(user_logged_out)
def cleanup_session_on_logout(sender, request, user, **kwargs):
    """Nettoie la session quand l'utilisateur se déconnecte"""
    if request.session.session_key:
        try:
            user_session = UserSession.objects.get(session_key=request.session.session_key)
            user_session.is_active = False
            user_session.logout_time = now()
            user_session.save()
        except UserSession.DoesNotExist:
            pass