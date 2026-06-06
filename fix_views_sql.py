#!/usr/bin/env python3
"""
fix_views_sql.py — Elimine toutes les references SQL dans dashboard/views.py
=============================================================================
USAGE :
  1. Placez ce fichier dans C:\\Users\\hp\\SIGR-CA-System\\
  2. Ouvrez PowerShell dans ce dossier
  3. Lancez : python fix_views_sql.py

Un backup est cree automatiquement : dashboard/views.py.bak
"""
import re, shutil, sys
from pathlib import Path

SRC = Path("dashboard/views.py")
BAK = Path("dashboard/views.py.bak")

if not SRC.exists():
    sys.exit(f"Fichier introuvable : {SRC}")

shutil.copy(SRC, BAK)
print(f"Backup cree : {BAK}")

text = SRC.read_text(encoding="utf-8")
changes = []

def replace(pattern, repl, description, flags=0):
    global text
    new, n = re.subn(pattern, repl, text, flags=flags)
    if n:
        text = new
        changes.append(f"  [{n:3d}x] {description}")


# ══════════════════════════════════════════════════════════════════════════════
# 1. INJECTER les helpers session juste apres "db = settings.MONGO_DB"
# ══════════════════════════════════════════════════════════════════════════════
SESSION_HELPERS = '''
# ──── Helpers session MongoDB (remplacent Django ORM auth) ────────────────────
from functools import wraps as _wraps

def session_required(view_func):
    """Remplace @login_required — verifie la session MongoDB."""
    @_wraps(view_func)
    def _wrapper(request, *args, **kwargs):
        if not request.session.get("user_id"):
            from django.conf import settings as _s
            login_url = getattr(_s, "LOGIN_URL", "/employe/login/")
            from django.shortcuts import redirect as _r
            return _r(f"{login_url}?next={request.path}")
        return view_func(request, *args, **kwargs)
    return _wrapper

def staff_required(view_func):
    """Acces reserve aux admins (is_staff = True en session)."""
    @_wraps(view_func)
    def _wrapper(request, *args, **kwargs):
        from django.shortcuts import redirect as _r
        if not request.session.get("user_id"):
            return _r("/login/")
        if not request.session.get("is_staff"):
            return _r("employe_espace")
        return view_func(request, *args, **kwargs)
    return _wrapper

def get_session_user(request):
    """Retourne un dict avec les infos utilisateur depuis la session."""
    uid = request.session.get("user_id", "")
    return {
        "id":             uid,
        "username":       request.session.get("username", ""),
        "is_staff":       request.session.get("is_staff", False),
        "is_superuser":   request.session.get("is_superuser", False),
        "is_authenticated": bool(uid),
        "first_name":     request.session.get("prenom", ""),
        "last_name":      request.session.get("nom", ""),
        "email":          request.session.get("email", ""),
    }
# ─────────────────────────────────────────────────────────────────────────────
'''

MARKER = "db = settings.MONGO_DB"
if MARKER in text and "session_required" not in text:
    text = text.replace(MARKER, SESSION_HELPERS + MARKER, 1)
    changes.append("  [  1x] Injection de session_required / staff_required / get_session_user")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Supprimer le bloc "Anciens users dashboard_utilisateur" dans login_view
# ══════════════════════════════════════════════════════════════════════════════
old_login_block = re.compile(
    r"# ── 1\. Anciens users.*?user_id\s*=\s*str\(old_user\['id'\]\)[^\n]*\n",
    re.DOTALL,
)
text, n = old_login_block.subn("", text)
if n:
    changes.append("  [  1x] Suppression bloc 'Anciens users' (dashboard_utilisateur) dans login_view")


# ══════════════════════════════════════════════════════════════════════════════
# 3. @login_required → @session_required
# ══════════════════════════════════════════════════════════════════════════════
replace(r"@login_required\b", "@session_required",
        "@login_required → @session_required")


# ══════════════════════════════════════════════════════════════════════════════
# 4. request.user.XXX → session equivalents
# ══════════════════════════════════════════════════════════════════════════════
replace(r"request\.user\.is_staff\b",
        "request.session.get('is_staff', False)",
        "request.user.is_staff → session")

replace(r"request\.user\.is_superuser\b",
        "request.session.get('is_superuser', False)",
        "request.user.is_superuser → session")

replace(r"request\.user\.is_authenticated\b",
        "bool(request.session.get('user_id'))",
        "request.user.is_authenticated → session")

replace(r"request\.user\.username\b",
        "request.session.get('username', '')",
        "request.user.username → session")

replace(r"request\.user\.id\b",
        "request.session.get('user_id', '')",
        "request.user.id → session")

replace(r"request\.user\.email\b",
        "request.session.get('email', '')",
        "request.user.email → session")

replace(r"request\.user\.first_name\b",
        "request.session.get('prenom', '')",
        "request.user.first_name → session")

replace(r"request\.user\.last_name\b",
        "request.session.get('nom', '')",
        "request.user.last_name → session")

# request.user restant (sans attribut specifique)
replace(r"request\.user\b(?!\.\w)",
        "get_session_user(request)",
        "request.user (reste) → get_session_user(request)")


# ══════════════════════════════════════════════════════════════════════════════
# 5. Collection dashboard_utilisateur → utilisateurs
# ══════════════════════════════════════════════════════════════════════════════
replace(r"""db\[['"]dashboard_utilisateur['"]\]""",
        "db['utilisateurs']",
        "db['dashboard_utilisateur'] → db['utilisateurs']")

replace(r"db\.dashboard_utilisateur\b",
        "db.utilisateurs",
        "db.dashboard_utilisateur → db.utilisateurs")


# ══════════════════════════════════════════════════════════════════════════════
# 6. Acces ['id'] → ['_id'] sur documents MongoDB
# ══════════════════════════════════════════════════════════════════════════════
# old_user['id']  # entier
replace(r"\['id'\]\s*#\s*entier[^\n]*",
        "['_id']  # ObjectId MongoDB",
        "xxx['id'] # entier → ['_id']")

# .get('id') sur docs MongoDB admin/user
replace(r"""(admin|user_doc|old_user|new_user|utilisateur)\.get\(['"]id['"]\)""",
        r"\1.get('_id')",
        "xxx.get('id') → xxx.get('_id') sur docs MongoDB")

# admin['id']
replace(r"""admin\['id'\]""",
        "str(admin['_id'])",
        "admin['id'] → str(admin['_id'])")

# Projection {'id': 1}
replace(r"""'id'\s*:\s*1(?=\s*[,}])""",
        "'_id': 1",
        "{'id': 1} projection → {'_id': 1}")


# ══════════════════════════════════════════════════════════════════════════════
# 7. Supprimer imports Django ORM devenus inutiles
# ══════════════════════════════════════════════════════════════════════════════
replace(r"^from django\.contrib\.auth\.decorators import login_required[^\n]*\n",
        "",
        "Suppression: import login_required",
        flags=re.MULTILINE)

replace(r"^User = get_user_model\(\)[^\n]*\n",
        "",
        "Suppression: User = get_user_model()",
        flags=re.MULTILINE)

# Supprimer "from django.contrib.auth import get_user_model" UNIQUEMENT
# si get_user_model n'est plus utilise apres suppression de User = get_user_model()
if "get_user_model" not in text:
    replace(r"^from django\.contrib\.auth import .*?get_user_model.*?\n",
            "",
            "Suppression: import get_user_model (plus utilise)",
            flags=re.MULTILINE)


# ══════════════════════════════════════════════════════════════════════════════
# 8. Scan final : signaler les occurrences restantes a verifier
# ══════════════════════════════════════════════════════════════════════════════
remaining = []
for pattern, label in [
    (r"request\.user\b",         "request.user"),
    (r"\['id'\]",                "['id']"),
    (r"dashboard_utilisateur",   "dashboard_utilisateur"),
    (r"@login_required",         "@login_required"),
    (r"User\.objects\.",         "User.objects."),
    (r"authenticate\(",          "authenticate("),
]:
    locs = [(i+1) for i, line in enumerate(text.splitlines())
            if re.search(pattern, line)]
    if locs:
        remaining.append(f"    {label:30s} lignes : {locs[:10]}"
                         + (" ..." if len(locs) > 10 else ""))


# ══════════════════════════════════════════════════════════════════════════════
# ECRITURE + RAPPORT
# ══════════════════════════════════════════════════════════════════════════════
SRC.write_text(text, encoding="utf-8")

print("\n" + "=" * 65)
print("  MODIFICATIONS APPLIQUEES")
print("=" * 65)
if changes:
    for c in changes:
        print(c)
else:
    print("  Aucune modification necessaire.")

if remaining:
    print("\n" + "=" * 65)
    print("  A VERIFIER MANUELLEMENT (occurrences restantes)")
    print("=" * 65)
    for r in remaining:
        print(r)

print("=" * 65)
print(f"\nFichier mis a jour : {SRC}")
print(f"Backup disponible  : {BAK}")
print("""
ETAPES SUIVANTES :
  1. Ouvrez settings.py et verifiez :
     - SESSION_ENGINE = 'django.contrib.sessions.backends.db'
       peut devenir 'django.contrib.sessions.backends.cache'
       ou 'django.contrib.sessions.backends.file'
     - MIDDLEWARE : retirez AuthenticationMiddleware si vous n'en avez plus besoin

  2. Dans les templates HTML, remplacez :
       {{ user.is_staff }}    →  {{ request.session.is_staff }}
       {{ user.username }}    →  {{ request.session.username }}
     Ou passez ces valeurs via le contexte de chaque vue.

  3. Relancez le serveur : python manage.py runserver
""")
