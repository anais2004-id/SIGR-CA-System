# dashboard/signals.py

from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver
from django.utils import timezone

@receiver(user_logged_out)
def cleanup_session_on_logout(sender, request, user, **kwargs):
    """Nettoie la session quand l'utilisateur se déconnecte"""
    if not request or not hasattr(request, 'session'):
        return

    session_key = request.session.session_key
    if not session_key:
        return

    try:
        from django.conf import settings
        db = settings.MONGO_DB

        db['dashboard_usersession'].update_many(
            {
                'session_key': session_key,
                'is_active': True,
            },
            {
                '$set': {
                    'is_active': False,
                    'logout_time': timezone.now(),
                }
            }
        )
    except Exception:
        pass