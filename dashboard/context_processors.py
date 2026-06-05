# dashboard/context_processors.py
from django.conf import settings


def employe_photo(request):
    """Photo de profil de l'employé connecté."""
    photo_url = None
    try:
        db       = settings.MONGO_DB
        user     = getattr(request, 'user', None)
        username = getattr(user, 'username', None) or request.session.get('username')
        if username:
            emp = db.employees.find_one({'django_username': username}, {'photo_url': 1})
            if emp:
                photo_url = emp.get('photo_url')
    except Exception:
        pass
    return {'employe_photo_url': photo_url}


def mongo_user_context(request):
    """
    Expose request.user (MongoUser) dans tous les templates sous la clé 'user'.
    Remplace django.contrib.auth.context_processors.auth qui nécessite Django ORM.
    """
    return {'user': getattr(request, 'user', None)}