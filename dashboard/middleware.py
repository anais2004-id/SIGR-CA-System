# dashboard/middleware.py
from django.utils.timezone import now as tz_now
from django.conf import settings
import requests


# ─────────────────────────────────────────────────────────────────────────────
# Objet proxy qui imite request.user de Django Auth
# mais lit depuis la session MongoDB  →  views.py N'A PAS BESOIN D'ÊTRE MODIFIÉ
# ─────────────────────────────────────────────────────────────────────────────
class MongoUser:
    """Remplace request.user partout dans les vues, sans toucher à Django Auth."""

    def __init__(self, session):
        self._id        = session.get('user_id')        # str(ObjectId)
        self.username   = session.get('username', '')
        self.is_staff   = session.get('is_staff', False)
        self.is_superuser = session.get('is_superuser', False)
        self.is_active  = True
        self.first_name = session.get('prenom', '')
        self.last_name  = session.get('nom', '')
        self.email      = session.get('email', '')
        # Django Auth attend request.user.id comme int ou str
        self.id         = self._id
        self.pk         = self._id

    # ── API Django Auth ──────────────────────────────────────────────────────
    @property
    def is_authenticated(self):
        return bool(self._id)

    @property
    def is_anonymous(self):
        return not bool(self._id)

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    def __str__(self):
        return self.username or 'AnonymousUser'

    def __bool__(self):
        return bool(self._id)


class AnonymousMongoUser:
    """Utilisateur non connecté."""
    id            = None
    pk            = None
    username      = ''
    is_staff      = False
    is_superuser  = False
    is_active     = False
    is_authenticated = False
    is_anonymous  = True
    first_name    = ''
    last_name     = ''
    email         = ''

    def get_full_name(self):    return ''
    def get_short_name(self):   return ''
    def has_perm(self, *a):     return False
    def has_module_perms(self, *a): return False
    def __str__(self):          return 'AnonymousUser'
    def __bool__(self):         return False


# ─────────────────────────────────────────────────────────────────────────────
# Middleware principal : injecte request.user depuis la session MongoDB
# ─────────────────────────────────────────────────────────────────────────────
class MongoAuthMiddleware:
    """
    À placer APRÈS SessionMiddleware et AVANT AuthenticationMiddleware
    (ou à la place de AuthenticationMiddleware si vous retirez djongo).
    
    Injecte request.user = MongoUser(...) basé sur la session,
    ce qui rend @login_required, request.user.is_staff, etc. fonctionnels
    sans aucune modification des vues.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user_id = request.session.get('user_id')
        if user_id:
            request.user       = MongoUser(request.session)
            request.mongo_user = request.user   # compatibilité avec ancien code
        else:
            request.user       = AnonymousMongoUser()
            request.mongo_user = {'is_authenticated': False, 'is_staff': False}

        return self.get_response(request)


# ─────────────────────────────────────────────────────────────────────────────
# Middleware session (enregistrement MongoDB — inchangé)
# ─────────────────────────────────────────────────────────────────────────────
class UserSessionMiddleware:
    """Enregistre/met à jour la session dans MongoDB."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # On lit depuis request.user qui est maintenant un MongoUser
        if getattr(request, 'user', None) and request.user.is_authenticated:
            session_key = request.session.session_key
            if session_key:
                try:
                    db         = settings.MONGO_DB
                    ip         = self._get_client_ip(request)
                    user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
                    device     = self._get_device_type(request)
                    location   = self._get_location(ip)
                    right_now  = tz_now()

                    col_session = db['dashboard_usersession']
                    col_log     = db['dashboard_sessionlog']

                    existing = list(
                        col_session.find({'session_key': session_key})
                        .sort('last_activity', -1)
                    )

                    if len(existing) > 1:
                        keep_id = existing[0]['_id']
                        col_session.delete_many({
                            'session_key': session_key,
                            '_id': {'$ne': keep_id}
                        })
                        created = False
                        doc_id  = keep_id
                    elif len(existing) == 1:
                        created = False
                        doc_id  = existing[0]['_id']
                    else:
                        result = col_session.insert_one({
                            'user_id':       request.user.id,
                            'session_key':   session_key,
                            'ip_address':    ip,
                            'user_agent':    user_agent,
                            'device_type':   device,
                            'location':      location,
                            'login_time':    right_now,
                            'last_activity': right_now,
                            'logout_time':   None,
                            'is_active':     True,
                        })
                        doc_id  = result.inserted_id
                        created = True

                        col_log.insert_one({
                            'user_id':     request.user.id,
                            'action':      'login',
                            'ip_address':  ip,
                            'user_agent':  user_agent,
                            'session_key': session_key,
                            'timestamp':   right_now,
                        })

                    if not created:
                        col_session.update_one(
                            {'_id': doc_id},
                            {'$set': {
                                'user_id':       request.user.id,
                                'ip_address':    ip,
                                'user_agent':    user_agent,
                                'device_type':   device,
                                'location':      location,
                                'last_activity': right_now,
                                'is_active':     True,
                                'logout_time':   None,
                            }}
                        )

                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"UserSessionMiddleware error: {e}"
                    )

        return response

    def _get_client_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            return xff.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    def _get_device_type(self, request):
        ua = request.META.get('HTTP_USER_AGENT', '').lower()
        if 'mobile' in ua or 'android' in ua or 'iphone' in ua:
            return 'mobile'
        if 'tablet' in ua or 'ipad' in ua:
            return 'tablet'
        return 'desktop'

    def _get_location(self, ip):
        if not ip or ip.startswith('127.') or ip.startswith('192.168.') or ip.startswith('10.'):
            return 'Local'
        try:
            r = requests.get(f'http://ip-api.com/json/{ip}', timeout=2)
            d = r.json()
            if d.get('status') == 'success':
                return f"{d.get('city', '')}, {d.get('countryCode', '')}"
        except Exception:
            pass
        return 'Inconnu'


# ─────────────────────────────────────────────────────────────────────────────
class NoBrowserCacheMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma']        = 'no-cache'
        response['Expires']       = '0'
        return response


# Alias pour compatibilité avec l'ancien middleware.py
#MongoUserMiddleware = MongoAuthMiddleware