"""
Script de migration des utilisateurs SQLite → MongoDB
À exécuter avec : python manage.py shell < migrate_users_to_mongo.py
"""
import sqlite3
from pymongo import MongoClient
from django.conf import settings
from datetime import datetime

print("=" * 60)
print("Migration utilisateurs SQLite → MongoDB")
print("=" * 60)

# ── Connexion SQLite (source) ──────────────────────────────────
try:
    conn = sqlite3.connect('db.sqlite3')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM dashboard_utilisateur')
    users_sql = [dict(r) for r in cursor.fetchall()]
    conn.close()
    print(f"✅ {len(users_sql)} utilisateurs trouvés dans SQLite")
except Exception as e:
    print(f"❌ Erreur lecture SQLite : {e}")
    exit(1)

# ── Connexion MongoDB (destination) ───────────────────────────
try:
    client = MongoClient('localhost', 27017)
    db = client['general_emballage']
    print("✅ Connexion MongoDB OK")
except Exception as e:
    print(f"❌ Erreur connexion MongoDB : {e}")
    exit(1)

# ── Migration ──────────────────────────────────────────────────
migrated = 0
skipped  = 0
errors   = 0

for user in users_sql:
    username = user['username']

    # Vérifie si l'utilisateur existe déjà dans MongoDB
    existing = db.dashboard_utilisateur.find_one({'username': username})
    if existing:
        print(f"  ⏭  '{username}' déjà présent dans MongoDB — ignoré")
        skipped += 1
        continue

    def parse_dt(val):
        if not val:
            return None
        for fmt in ('%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
        return None

    doc = {
        'id':           user['id'],
        'password':     user['password'],
        'last_login':   parse_dt(user.get('last_login')),
        'is_superuser': bool(user['is_superuser']),
        'username':     user['username'],
        'first_name':   user.get('first_name', ''),
        'last_name':    user.get('last_name', ''),
        'email':        user.get('email', ''),
        'is_staff':     bool(user['is_staff']),
        'is_active':    bool(user['is_active']),
        'date_joined':  parse_dt(user.get('date_joined')),
        'badge_rfid':   user.get('badge_rfid'),
        'telephone':    user.get('telephone'),
        'poste':        user.get('poste'),
        'departement':  user.get('departement'),
    }

    try:
        db.dashboard_utilisateur.insert_one(doc)
        print(f"  ✅ '{username}' migré (staff={doc['is_staff']}, superuser={doc['is_superuser']})")
        migrated += 1
    except Exception as e:
        print(f"  ❌ Erreur pour '{username}' : {e}")
        errors += 1

# ── Index utiles ───────────────────────────────────────────────
try:
    db.dashboard_utilisateur.create_index('username', unique=True)
    db.dashboard_utilisateur.create_index('email')
    db.dashboard_utilisateur.create_index('id', unique=True)
    print("\n✅ Index créés sur dashboard_utilisateur")
except Exception as e:
    print(f"\n⚠️  Index : {e}")

# ── Résumé ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"  Migrés  : {migrated}")
print(f"  Ignorés : {skipped} (déjà existants)")
print(f"  Erreurs : {errors}")
print("=" * 60)

if errors == 0:
    print("\n✅ Migration terminée avec succès.")
    print("   Prochaine étape : python manage.py migrate --run-syncdb")
else:
    print("\n⚠️  Migration terminée avec des erreurs. Vérifiez ci-dessus.")