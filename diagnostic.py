"""
diagnostic.py — À exécuter depuis le répertoire racine du projet Django
Commande : python diagnostic.py

Vérifie tous les problèmes courants de votre application SIGR-CA.
"""

import os, sys, django

# ── Setup Django ──────────────────────────────────────────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from django.conf import settings

OK  = "  ✅"
ERR = "  ❌"
WRN = "  ⚠️ "

print("\n" + "="*60)
print("  DIAGNOSTIC SIGR-CA")
print("="*60)

# ──────────────────────────────────────────────────────────────────────────────
# 1. MEDIA_ROOT
# ──────────────────────────────────────────────────────────────────────────────
print("\n📁 MEDIA & STORAGE")
media_root = str(settings.MEDIA_ROOT)
avatars_dir = os.path.join(media_root, 'avatars')

if os.path.isabs(media_root):
    print(f"{OK} MEDIA_ROOT est absolu : {media_root}")
else:
    print(f"{ERR} MEDIA_ROOT est RELATIF ({media_root}) → les photos ne seront pas sauvegardées !")

if os.path.exists(media_root):
    print(f"{OK} Dossier media/ existe")
else:
    print(f"{WRN} Dossier media/ absent → sera créé automatiquement au premier upload")

if os.path.exists(avatars_dir):
    nb = len([f for f in os.listdir(avatars_dir) if f.startswith('avatar_')])
    print(f"{OK} Dossier avatars/ existe ({nb} avatar(s) stocké(s))")
else:
    print(f"{WRN} Dossier media/avatars/ absent → sera créé automatiquement")

# ──────────────────────────────────────────────────────────────────────────────
# 2. MONGODB
# ──────────────────────────────────────────────────────────────────────────────
print("\n🍃 MONGODB")
try:
    db = settings.MONGO_DB
    # Ping
    db.command('ping')
    print(f"{OK} Connexion MongoDB OK")

    nb_employes = db.employees.count_documents({})
    print(f"{OK} Collection employees : {nb_employes} document(s)")

    # Statuts
    actifs   = db.employees.count_documents({'statut': 'actif'})
    inactifs = db.employees.count_documents({'statut': 'inactif'})
    sans_statut = db.employees.count_documents({'statut': {'$exists': False}})
    autre_statut = nb_employes - actifs - inactifs - sans_statut

    print(f"     → actif={actifs}, inactif={inactifs}, sans statut={sans_statut}, autre={autre_statut}")

    if sans_statut > 0 or autre_statut > 0:
        print(f"{WRN} {sans_statut + autre_statut} employé(s) avec statut manquant/invalide → sera normalisé à 'actif' par la vue")

    # Badge dupliqués
    pipeline = [
        {'$group': {'_id': '$badge_id', 'count': {'$sum': 1}}},
        {'$match': {'count': {'$gt': 1}}}
    ]
    dupes = list(db.employees.aggregate(pipeline))
    if dupes:
        print(f"{ERR} Badges RFID DUPLIQUÉS détectés : {[d['_id'] for d in dupes]}")
    else:
        print(f"{OK} Aucun badge RFID dupliqué")

    # Employés sans badge
    sans_badge = db.employees.count_documents({'badge_id': {'$in': ['', None]}})
    if sans_badge:
        print(f"{WRN} {sans_badge} employé(s) sans badge RFID")

except Exception as e:
    print(f"{ERR} Erreur MongoDB : {e}")

# ──────────────────────────────────────────────────────────────────────────────
# 3. UTILISATEURS DJANGO
# ──────────────────────────────────────────────────────────────────────────────
print("\n👤 UTILISATEURS DJANGO (SQLite)")
try:
    from django.contrib.auth import get_user_model
    User = get_user_model()

    total_users = User.objects.count()
    admins = User.objects.filter(is_staff=True).count()
    superusers = User.objects.filter(is_superuser=True).count()
    print(f"{OK} {total_users} utilisateur(s) total | {admins} staff | {superusers} superuser")

    if admins == 0:
        print(f"{ERR} AUCUN utilisateur staff ! Le bouton 'Modifier' sera bloqué pour tout le monde.")
        print(f"     → Correction : python manage.py shell")
        print(f"       >>> from dashboard.models import Utilisateur")
        print(f"       >>> Utilisateur.objects.filter(username='admin').update(is_staff=True, is_superuser=True)")
    else:
        staff_users = User.objects.filter(is_staff=True).values_list('username', flat=True)
        print(f"     → Staff : {list(staff_users)}")

except Exception as e:
    print(f"{ERR} Erreur SQLite : {e}")

# ──────────────────────────────────────────────────────────────────────────────
# 4. URLs
# ──────────────────────────────────────────────────────────────────────────────
print("\n🔗 URLs")
try:
    from django.urls import reverse
    urls_to_check = [
        ('employe_list',     []),
        ('employe_ajouter',  []),
        ('employe_detail',   ['507f1f77bcf86cd799439011']),
        ('employe_modifier', ['507f1f77bcf86cd799439011']),
        ('employe_supprimer',['507f1f77bcf86cd799439011']),
    ]
    for name, args in urls_to_check:
        try:
            url = reverse(name, args=args) if args else reverse(name)
            print(f"{OK} {name:25s} → {url}")
        except Exception as e:
            print(f"{ERR} {name:25s} → NON TROUVÉE ({e})")
except Exception as e:
    print(f"{ERR} Erreur vérification URLs : {e}")

# ──────────────────────────────────────────────────────────────────────────────
# 5. SETTINGS CRITIQUES
# ──────────────────────────────────────────────────────────────────────────────
print("\n⚙️  SETTINGS")
print(f"     DEBUG = {settings.DEBUG}")
print(f"     TIME_ZONE = {settings.TIME_ZONE}")
print(f"     STATIC_URL = {settings.STATIC_URL}")
print(f"     MEDIA_URL = {settings.MEDIA_URL}")

# MIDDLEWARE doublons
mw_flat = [m.split('.')[-1] for m in settings.MIDDLEWARE]
mw_dupes = [m for m in set(mw_flat) if mw_flat.count(m) > 1]
if mw_dupes:
    print(f"{WRN} MIDDLEWARE dupliqués détectés : {mw_dupes}")
    print(f"     → Nettoyez settings.py : chaque middleware ne doit apparaître qu'une seule fois")
else:
    print(f"{OK} Pas de middleware dupliqué")

# ──────────────────────────────────────────────────────────────────────────────
# 6. NORMALISATION STATUTS (auto-fix optionnel)
# ──────────────────────────────────────────────────────────────────────────────
print("\n🔧 CORRECTION AUTOMATIQUE DES STATUTS MONGODB")
try:
    db = settings.MONGO_DB
    result = db.employees.update_many(
        {'statut': {'$nin': ['actif', 'inactif']}},
        {'$set': {'statut': 'actif'}}
    )
    if result.modified_count > 0:
        print(f"{OK} {result.modified_count} statut(s) corrigé(s) → 'actif'")
    else:
        print(f"{OK} Tous les statuts sont déjà valides")
except Exception as e:
    print(f"{ERR} Erreur normalisation : {e}")

print("\n" + "="*60)
print("  FIN DU DIAGNOSTIC")
print("="*60 + "\n")