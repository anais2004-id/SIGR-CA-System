#!/usr/bin/env python3
"""
fix_views.py — Corrige automatiquement tous les User.objects.filter(is_staff=True)
et autres appels ORM problématiques dans dashboard/views.py (djongo + MongoDB).

Usage:
    python fix_views.py C:\\Users\\hp\\SIGR-CA-System\\dashboard\\views.py
"""

import sys
import re
import shutil
from pathlib import Path


def fix_views(path_str: str):
    path = Path(path_str)
    if not path.exists():
        print(f"[ERREUR] Fichier introuvable: {path}")
        sys.exit(1)

    backup = path.with_suffix('.py.bak')
    shutil.copy2(path, backup)
    print(f"[OK] Backup créé: {backup}")

    content = path.read_text(encoding='utf-8-sig')
    original = content
    fixes_applied = 0

    def replace_block(old: str, new: str, label: str):
        nonlocal content, fixes_applied
        if old in content:
            content = content.replace(old, new, 1)
            fixes_applied += 1
            print(f"[FIX {fixes_applied}] {label}")
        else:
            print(f"[SKIP] {label} — bloc introuvable (déjà corrigé ?)")

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 1 — send_notification_to_all_admins (1ère occurrence ~l.10179)
    # ══════════════════════════════════════════════════════════════════════════
    NEW_NOTIF_ALL = (
        "def send_notification_to_all_admins(titre, message, categorie='info', icon='🔔', action_url=None, reservation_id=None):\n"
        "    \"\"\"Envoie une notification à tous les administrateurs (PyMongo direct)\"\"\"\n"
        "    from datetime import datetime\n"
        "    try:\n"
        "        admins = list(db['dashboard_utilisateur'].find(\n"
        "            {'is_staff': True, 'is_active': True}, {'id': 1}\n"
        "        ))\n"
        "        if not admins:\n"
        "            return\n"
        "        notifications = [{\n"
        "            'admin_id':       admin.get('id'),\n"
        "            'titre':          titre,\n"
        "            'message':        message,\n"
        "            'categorie':      categorie,\n"
        "            'icon':           icon,\n"
        "            'status':         'non_lu',\n"
        "            'action_url':     action_url,\n"
        "            'reservation_id': reservation_id,\n"
        "            'created_at':     datetime.now(),\n"
        "        } for admin in admins]\n"
        "        if notifications:\n"
        "            db.admin_notifications.insert_many(notifications)\n"
        "    except Exception as _e:\n"
        "        import logging; logging.getLogger(__name__).warning(f\"send_notification_to_all_admins échoué: {_e}\")"
    )

    replace_block(
        (
            "def send_notification_to_all_admins(titre, message, categorie='info', icon='🔔', action_url=None, reservation_id=None):\n"
            "    \"\"\"Envoie une notification à tous les administrateurs\"\"\"\n"
            "    from datetime import datetime\n"
            "    from django.contrib.auth import get_user_model\n"
            "    \n"
            "    User = get_user_model()\n"
            "    admins = User.objects.filter(is_staff=True, is_active=True)\n"
            "    \n"
            "    notifications = []\n"
            "    for admin in admins:\n"
            "        notifications.append({\n"
            "            'admin_id': admin.id,\n"
            "            'titre': titre,\n"
            "            'message': message,\n"
            "            'categorie': categorie,\n"
            "            'icon': icon,\n"
            "            'status': 'non_lu',\n"
            "            'action_url': action_url,\n"
            "            'reservation_id': reservation_id,\n"
            "            'created_at': datetime.now()\n"
            "        })\n"
            "    \n"
            "    if notifications:\n"
            "        db.admin_notifications.insert_many(notifications)"
        ),
        NEW_NOTIF_ALL,
        "send_notification_to_all_admins (1ère)"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 2 — send_notification_to_all_admins (2ème occurrence ~l.10298)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "def send_notification_to_all_admins(titre, message, categorie='info', icon='🔔', action_url=None, reservation_id=None):\n"
            "    \"\"\"Envoie une notification à tous les administrateurs\"\"\"\n"
            "    from datetime import datetime\n"
            "    from django.contrib.auth import get_user_model\n"
            "    \n"
            "    User = get_user_model()\n"
            "    admins = User.objects.filter(is_staff=True, is_active=True)\n"
            "    \n"
            "    if not admins:\n"
            "        return\n"
            "    \n"
            "    notifications = []\n"
            "    for admin in admins:\n"
            "        notifications.append({\n"
            "            'admin_id': admin.id,\n"
            "            'titre': titre,\n"
            "            'message': message,\n"
            "            'categorie': categorie,\n"
            "            'icon': icon,\n"
            "            'status': 'non_lu',\n"
            "            'action_url': action_url,\n"
            "            'reservation_id': reservation_id,\n"
            "            'created_at': datetime.now()\n"
            "        })\n"
            "    \n"
            "    if notifications:\n"
            "        db.admin_notifications.insert_many(notifications)"
        ),
        NEW_NOTIF_ALL,
        "send_notification_to_all_admins (2ème)"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 3 — notify_admin_new_reservation (~l.10502)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "def notify_admin_new_reservation(employe, reservation_data, reservation_id):\n"
            "    \"\"\"Notifie les administrateurs d'une nouvelle réservation\"\"\"\n"
            "    from django.contrib.auth import get_user_model\n"
            "    from datetime import datetime\n"
            "    \n"
            "    User = get_user_model()\n"
            "    admins = User.objects.filter(is_staff=True, is_active=True)\n"
            "    \n"
            "    for admin in admins:\n"
            "        admin_notification = {\n"
            "            'admin_id': admin.id,\n"
            "            'titre': '🆕 Nouvelle réservation en attente',\n"
            "            'message': f\"{employe.get('prenom', '')} {employe.get('nom', '')} a demandé une réservation pour '{reservation_data.get('titre')}' .\",\n"
            "            'categorie': 'reservation',\n"
            "            'icon': '🆕',\n"
            "            'status': 'non_lu',\n"
            "            'action_url': f'/reservations/{reservation_id}/',\n"
            "            'reservation_id': reservation_id,\n"
            "            'created_at': datetime.now()\n"
            "        }\n"
            "        db.admin_notifications.insert_one(admin_notification)"
        ),
        (
            "def notify_admin_new_reservation(employe, reservation_data, reservation_id):\n"
            "    \"\"\"Notifie les administrateurs d'une nouvelle réservation (PyMongo direct)\"\"\"\n"
            "    from datetime import datetime\n"
            "    try:\n"
            "        admins = list(db['dashboard_utilisateur'].find(\n"
            "            {'is_staff': True, 'is_active': True}, {'id': 1}\n"
            "        ))\n"
            "        for admin in admins:\n"
            "            db.admin_notifications.insert_one({\n"
            "                'admin_id':       admin.get('id'),\n"
            "                'titre':          '🆕 Nouvelle réservation en attente',\n"
            "                'message':        f\"{employe.get('prenom', '')} {employe.get('nom', '')} a demandé une réservation pour '{reservation_data.get('titre')}'.\",\n"
            "                'categorie':      'reservation',\n"
            "                'icon':           '🆕',\n"
            "                'status':         'non_lu',\n"
            "                'action_url':     f'/reservations/{reservation_id}/',\n"
            "                'reservation_id': reservation_id,\n"
            "                'created_at':     datetime.now(),\n"
            "            })\n"
            "    except Exception as _e:\n"
            "        import logging; logging.getLogger(__name__).warning(f\"notify_admin_new_reservation échoué: {_e}\")"
        ),
        "notify_admin_new_reservation"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 4 — employe_mes_reservations : notifs admins (~l.617)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "            # --- Notifications admins ---\n"
            "            from django.contrib.auth import get_user_model\n"
            "            User = get_user_model()\n"
            "            admins = User.objects.filter(is_staff=True, is_active=True)\n"
        ),
        (
            "            # --- Notifications admins (PyMongo direct) ---\n"
            "            admins = list(db['dashboard_utilisateur'].find(\n"
            "                {'is_staff': True, 'is_active': True}, {'id': 1, 'email': 1}\n"
            "            ))\n"
        ),
        "employe_mes_reservations: remplacement User.objects.filter admins"
    )

    # Fix admin.id → admin.get('id') et admin.email → admin.get('email') dans le bloc suivant
    replace_block(
        "                    'admin_id':       admin.id,\n",
        "                    'admin_id':       admin.get('id'),\n",
        "employe_mes_reservations: admin.id → admin.get('id')"
    )
    replace_block(
        "                if admin.email:\n"
        "                    try:\n"
        "                        from dashboard.utils_email import envoyer_email\n"
        "                        envoyer_email(\n"
        "                            admin.email,\n",
        "                if admin.get('email'):\n"
        "                    try:\n"
        "                        from dashboard.utils_email import envoyer_email\n"
        "                        envoyer_email(\n"
        "                            admin['email'],\n",
        "employe_mes_reservations: admin.email → admin.get('email')"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 5 — employe_annuler_reservation : import + ORM (~l.765 / ~l.811)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "    from django.contrib.auth import get_user_model\n"
            "    \n"
            "    User = get_user_model()\n"
            "    employe = db.employees.find_one({'django_user_id': request.user.id})\n"
            "    if not employe:\n"
            "        employe = db.employees.find_one({'django_username': request.user.username})"
        ),
        (
            "    employe = db.employees.find_one({'django_user_id': request.user.id})\n"
            "    if not employe:\n"
            "        employe = db.employees.find_one({'django_username': request.user.username})"
        ),
        "employe_annuler_reservation: suppression import get_user_model inutile"
    )

    replace_block(
        (
            "                # === NOTIFICATION AUX ADMINISTRATEURS ===\n"
            "                admins = User.objects.filter(is_staff=True, is_active=True)\n"
            "                for admin in admins:\n"
            "                    admin_notification = {\n"
            "                        'admin_id': admin.id,\n"
            "                        'titre': '🗑️ Réservation annulée',\n"
            "                        'message': f\"{employe.get('prenom', '')} {employe.get('nom', '')} a annulé sa réservation '{resa.get('titre', 'Sans titre')}' pour la salle {bureau_nom}.\",\n"
            "                        'categorie': 'reservation',\n"
            "                        'icon': '🗑️',\n"
            "                        'status': 'non_lu',\n"
            "                        'action_url': f'/reservations/{reservation_id}/',\n"
            "                        'reservation_id': reservation_id,\n"
            "                        'created_at': datetime.now()\n"
            "                    }\n"
            "                    db.admin_notifications.insert_one(admin_notification)"
        ),
        (
            "                # === NOTIFICATION AUX ADMINISTRATEURS (PyMongo direct) ===\n"
            "                try:\n"
            "                    admins = list(db['dashboard_utilisateur'].find(\n"
            "                        {'is_staff': True, 'is_active': True}, {'id': 1}\n"
            "                    ))\n"
            "                    for admin in admins:\n"
            "                        db.admin_notifications.insert_one({\n"
            "                            'admin_id':       admin.get('id'),\n"
            "                            'titre':          '🗑️ Réservation annulée',\n"
            "                            'message':        f\"{employe.get('prenom', '')} {employe.get('nom', '')} a annulé sa réservation '{resa.get('titre', 'Sans titre')}' pour la salle {bureau_nom}.\",\n"
            "                            'categorie':      'reservation',\n"
            "                            'icon':           '🗑️',\n"
            "                            'status':         'non_lu',\n"
            "                            'action_url':     f'/reservations/{reservation_id}/',\n"
            "                            'reservation_id': reservation_id,\n"
            "                            'created_at':     datetime.now(),\n"
            "                        })\n"
            "                except Exception as _e:\n"
            "                    logger.warning(f\"Notifications annulation échouées: {_e}\")"
        ),
        "employe_annuler_reservation: notifs admins PyMongo"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 6 — Sessions actives employé (~l.7561)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "    try:\n"
            "        from dashboard.models import UserSession\n"
            "        sessions = UserSession.objects.filter(\n"
            "            user=request.user,\n"
            "            is_active=True,\n"
            "            logout_time__isnull=True\n"
            "        ).order_by('-last_activity')\n"
            "\n"
            "        for session in sessions:\n"
            "            active_sessions.append({\n"
            "                'id':            session.id,\n"
            "                'device_type':   session.device_type or 'desktop',\n"
            "                'ip_address':    session.ip_address or '—',\n"
            "                'login_time':    session.login_time.strftime('%d/%m/%Y %H:%M:%S'),\n"
            "                'last_activity': session.last_activity.strftime('%d/%m/%Y %H:%M:%S'),\n"
            "                'is_current':    session.session_key == request.session.session_key\n"
            "            })\n"
            "    except Exception:\n"
            "        active_sessions = []"
        ),
        (
            "    try:\n"
            "        raw_sessions = list(db['dashboard_usersession'].find({\n"
            "            'user_id': request.user.id,\n"
            "            'is_active': True,\n"
            "            '$or': [{'logout_time': None}, {'logout_time': {'$exists': False}}],\n"
            "        }).sort('last_activity', -1))\n"
            "        for s in raw_sessions:\n"
            "            def _fmt(dt):\n"
            "                if dt is None: return '—'\n"
            "                try: return dt.strftime('%d/%m/%Y %H:%M:%S')\n"
            "                except Exception: return str(dt)\n"
            "            active_sessions.append({\n"
            "                'id':            str(s.get('_id', '')),\n"
            "                'device_type':   s.get('device_type') or 'desktop',\n"
            "                'ip_address':    s.get('ip_address') or '—',\n"
            "                'login_time':    _fmt(s.get('login_time')),\n"
            "                'last_activity': _fmt(s.get('last_activity')),\n"
            "                'is_current':    s.get('session_key') == request.session.session_key,\n"
            "            })\n"
            "    except Exception:\n"
            "        active_sessions = []"
        ),
        "Sessions actives employé (UserSession.objects → PyMongo)"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 7 — Chatbot notifs admins (~l.9882)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "        try:\n"
            "            from django.contrib.auth import get_user_model\n"
            "            User   = get_user_model()\n"
            "            admins = User.objects.filter(is_staff=True, is_active=True)\n"
            "\n"
            "            for admin in admins:\n"
            "                db.admin_notifications.insert_one({\n"
            "                    'admin_id':       admin.id,\n"
            "                    'titre':          '🆕 Nouvelle réservation en attente (chatbot)',\n"
        ),
        (
            "        try:\n"
            "            admins = list(db['dashboard_utilisateur'].find(\n"
            "                {'is_staff': True, 'is_active': True}, {'id': 1, 'email': 1}\n"
            "            ))\n"
            "            for admin in admins:\n"
            "                db.admin_notifications.insert_one({\n"
            "                    'admin_id':       admin.get('id'),\n"
            "                    'titre':          '🆕 Nouvelle réservation en attente (chatbot)',\n"
        ),
        "Chatbot notifs admins: User.objects → PyMongo"
    )
    replace_block(
        (
            "                if admin.email:\n"
            "                    try:\n"
            "                        from dashboard.utils_email import envoyer_email\n"
            "                        envoyer_email(\n"
            "                            admin.email,\n"
            "                            f\"🆕 Nouvelle réservation (chatbot) — {titre}\",\n"
            "                            admin_message_email,\n"
            "                        )\n"
            "                    except Exception as _ee:\n"
            "                        print(f\"Email admin échoué : {_ee}\")\n"
            "        except Exception as _e:\n"
            "            print(f\"Notifications admins échouées : {_e}\")"
        ),
        (
            "                if admin.get('email'):\n"
            "                    try:\n"
            "                        from dashboard.utils_email import envoyer_email\n"
            "                        envoyer_email(admin['email'], f\"🆕 Nouvelle réservation (chatbot) — {titre}\", admin_message_email)\n"
            "                    except Exception as _ee:\n"
            "                        logger.warning(f\"Email admin chatbot échoué: {_ee}\")\n"
            "        except Exception as _e:\n"
            "            logger.warning(f\"Notifications admins chatbot échouées: {_e}\")"
        ),
        "Chatbot notifs admins: admin.email → admin.get('email')"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 8 — password_forgot: User.objects.filter email (~l.10534)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "        try:\n"
            "            user = User.objects.filter(email__iexact=email).first()\n"
            "            if user is None:\n"
            "                raise User.DoesNotExist\n"
            "        except User.DoesNotExist:\n"
            "            # On affiche le même message pour ne pas révéler si l'email existe\n"
            "            messages.success(request, \"Si cet email existe dans notre système, un lien vous a été envoyé.\")\n"
            "            return render(request, 'dashboard/password_forgot.html')"
        ),
        (
            "        user_doc = db['dashboard_utilisateur'].find_one(\n"
            "            {'email': {'$regex': f'^{re.escape(email)}$', '$options': 'i'}}\n"
            "        )\n"
            "        if not user_doc:\n"
            "            messages.success(request, \"Si cet email existe dans notre système, un lien vous a été envoyé.\")\n"
            "            return render(request, 'dashboard/password_forgot.html')\n"
            "        try:\n"
            "            user = User.objects.get(pk=user_doc['id'])\n"
            "        except Exception:\n"
            "            messages.success(request, \"Si cet email existe dans notre système, un lien vous a été envoyé.\")\n"
            "            return render(request, 'dashboard/password_forgot.html')"
        ),
        "password_forgot: email lookup via PyMongo"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 9 — Invalidation sessions post-reset (~l.10714)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "        # Invalider toutes les sessions actives de l'utilisateur\n"
            "        from django.contrib.sessions.models import Session\n"
            "        for session in Session.objects.all():\n"
            "            data = session.get_decoded()\n"
            "            if str(data.get('_auth_user_id')) == str(user.pk):\n"
            "                session.delete()"
        ),
        (
            "        # Invalider toutes les sessions actives de l'utilisateur\n"
            "        try:\n"
            "            from django.contrib.sessions.models import Session\n"
            "            for session in Session.objects.all():\n"
            "                try:\n"
            "                    data = session.get_decoded()\n"
            "                    if str(data.get('_auth_user_id')) == str(user.pk):\n"
            "                        session.delete()\n"
            "                except Exception:\n"
            "                    pass\n"
            "        except Exception as _se:\n"
            "            logger.warning(f\"Invalidation sessions Django échouée: {_se}\")\n"
            "        try:\n"
            "            db['dashboard_usersession'].update_many(\n"
            "                {'user_id': user.pk},\n"
            "                {'$set': {'is_active': False, 'logout_time': datetime.now()}}\n"
            "            )\n"
            "        except Exception:\n"
            "            pass"
        ),
        "Invalidation sessions post-reset: try/except + PyMongo"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 10 — Badge RFID affecter (~l.11838)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "        # Mettre à jour le modèle Django si lié\n"
            "        if employe.get('django_user_id'):\n"
            "            try:\n"
            "                django_user = User.objects.get(pk=employe['django_user_id'])\n"
            "                django_user.badge_rfid = badge_id\n"
            "                django_user.save()\n"
            "            except Exception:\n"
            "                pass"
        ),
        (
            "        # Mettre à jour badge_rfid dans MongoDB directement\n"
            "        if employe.get('django_user_id'):\n"
            "            try:\n"
            "                db['dashboard_utilisateur'].update_one(\n"
            "                    {'id': int(employe['django_user_id'])},\n"
            "                    {'$set': {'badge_rfid': badge_id}}\n"
            "                )\n"
            "            except Exception as _e:\n"
            "                logger.warning(f\"Mise à jour badge_rfid échouée: {_e}\")"
        ),
        "Badge RFID affecter: User.objects.get → PyMongo"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 11 — Badge RFID révoquer (~l.11900)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "        if employe.get('django_user_id'):\n"
            "            try:\n"
            "                django_user = User.objects.get(pk=employe['django_user_id'])\n"
            "                django_user.badge_rfid = None\n"
            "                django_user.save()\n"
            "            except Exception:\n"
            "                pass"
        ),
        (
            "        if employe.get('django_user_id'):\n"
            "            try:\n"
            "                db['dashboard_utilisateur'].update_one(\n"
            "                    {'id': int(employe['django_user_id'])},\n"
            "                    {'$unset': {'badge_rfid': ''}}\n"
            "                )\n"
            "            except Exception as _e:\n"
            "                logger.warning(f\"Révocation badge_rfid échouée: {_e}\")"
        ),
        "Badge RFID révoquer: User.objects.get → PyMongo"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 12 — Notification indisponibilité in-app (~l.12232)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "                    try:\n"
            "                        django_user_id = employe.get('django_user_id')\n"
            "                        if django_user_id:\n"
            "                            django_user = User.objects.get(pk=django_user_id)\n"
            "                            Notification.create_notification(\n"
            "                                user=django_user,\n"
            "                                titre=f'🔧 Maintenance planifiée — {ressource_nom}',\n"
            "                                message=f\"La ressource '{ressource_nom}' sera indisponible du \"\n"
            "                                        f\"{date_debut.strftime('%d/%m/%Y %H:%M')} au \"\n"
            "                                        f\"{date_fin.strftime('%d/%m/%Y %H:%M')}. Motif : {description or titre}\",\n"
            "                                categorie='alerte',\n"
            "                                icon='🔧',\n"
            "                            )\n"
            "                    except Exception:\n"
            "                        pass"
        ),
        (
            "                    try:\n"
            "                        if employe.get('_id'):\n"
            "                            db.notifications.insert_one({\n"
            "                                'employe_id': str(employe['_id']),\n"
            "                                'titre':      f'🔧 Maintenance planifiée — {ressource_nom}',\n"
            "                                'message':    f\"La ressource '{ressource_nom}' sera indisponible du \"\n"
            "                                              f\"{date_debut.strftime('%d/%m/%Y %H:%M')} au \"\n"
            "                                              f\"{date_fin.strftime('%d/%m/%Y %H:%M')}. Motif : {description or titre}\",\n"
            "                                'categorie':  'alerte',\n"
            "                                'icon':       '🔧',\n"
            "                                'status':     'non_lu',\n"
            "                                'created_at': datetime.now(),\n"
            "                            })\n"
            "                    except Exception:\n"
            "                        pass"
        ),
        "Notification indisponibilité: Notification.create_notification → PyMongo"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 13 — approbation_inbox wrap try/except (~l.12615)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "def approbation_inbox(request):\n"
            "    user_id = str(request.user.id)\n"
            "    demandes = ApprovalRequest.objects.filter(\n"
            "        approbateur_id=user_id, statut='en_attente'\n"
            "    ).order_by('-created_at')\n"
            "    return render(request, 'dashboard/approbation_inbox.html',\n"
            "                  {'demandes': demandes})"
        ),
        (
            "def approbation_inbox(request):\n"
            "    user_id = str(request.user.id)\n"
            "    try:\n"
            "        demandes = ApprovalRequest.objects.filter(\n"
            "            approbateur_id=user_id, statut='en_attente'\n"
            "        ).order_by('-created_at')\n"
            "    except Exception as _e:\n"
            "        logger.warning(f\"approbation_inbox ORM échoué: {_e}\")\n"
            "        demandes = []\n"
            "    return render(request, 'dashboard/approbation_inbox.html',\n"
            "                  {'demandes': demandes})"
        ),
        "approbation_inbox: try/except"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 14 — queue_confirmer wrap try/except (~l.12707)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "def queue_confirmer(request, queue_id):\n"
            "    \"\"\"L'utilisateur transforme sa place en file en réservation.\"\"\"\n"
            "    wq = WaitingQueue.objects.get(id=queue_id, user_id=str(request.user.id))\n"
            "    if wq.statut != 'notifie':"
        ),
        (
            "def queue_confirmer(request, queue_id):\n"
            "    \"\"\"L'utilisateur transforme sa place en file en réservation.\"\"\"\n"
            "    try:\n"
            "        wq = WaitingQueue.objects.get(id=queue_id, user_id=str(request.user.id))\n"
            "    except Exception:\n"
            "        messages.error(request, \"File d'attente introuvable.\")\n"
            "        return redirect('employe_mes_reservations')\n"
            "    if wq.statut != 'notifie':"
        ),
        "queue_confirmer: try/except WaitingQueue.objects.get"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # FIX 15 — queue_quitter wrap try/except (~l.12740)
    # ══════════════════════════════════════════════════════════════════════════
    replace_block(
        (
            "def queue_quitter(request, queue_id):\n"
            "    wq = WaitingQueue.objects.get(id=queue_id, user_id=str(request.user.id))\n"
            "    wq.statut = 'annule'\n"
            "    wq.save()\n"
            "    messages.info(request, \"Vous avez quitté la file d'attente.\")\n"
            "    return redirect('employe_mes_reservations')"
        ),
        (
            "def queue_quitter(request, queue_id):\n"
            "    try:\n"
            "        wq = WaitingQueue.objects.get(id=queue_id, user_id=str(request.user.id))\n"
            "        wq.statut = 'annule'\n"
            "        wq.save()\n"
            "    except Exception as _e:\n"
            "        logger.warning(f\"queue_quitter échoué: {_e}\")\n"
            "    messages.info(request, \"Vous avez quitté la file d'attente.\")\n"
            "    return redirect('employe_mes_reservations')"
        ),
        "queue_quitter: try/except WaitingQueue.objects.get"
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Assurer que 'import re' est présent (FIX 8 en a besoin)
    # ══════════════════════════════════════════════════════════════════════════
    if 'import re' not in content:
        content = content.replace('import json\n', 'import json\nimport re\n', 1)
        print("[INFO] 'import re' ajouté aux imports")

    # ══════════════════════════════════════════════════════════════════════════
    # Écriture finale
    # ══════════════════════════════════════════════════════════════════════════
    if content != original:
        path.write_text(content, encoding='utf-8')
        print(f"\n✅ {fixes_applied} correction(s) appliquée(s) — fichier sauvegardé.")
        print(f"   Backup disponible: {backup}")
    else:
        print("\n⚠️  Aucun changement — toutes les corrections sont peut-être déjà appliquées.")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python fix_views.py <chemin/vers/views.py>")
        print("Exemple: python fix_views.py C:\\Users\\hp\\SIGR-CA-System\\dashboard\\views.py")
        sys.exit(1)
    fix_views(sys.argv[1])
