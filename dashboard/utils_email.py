# dashboard/utils_email.py
# Utilitaire d'envoi d'email compatible Python 3.12 (contourne le bug keyfile/certfile)
import ssl
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from django.conf import settings

logger = logging.getLogger(__name__)


def _build_html_email(titre, contenu_html, couleur_header='#1f6feb'):
    """Enveloppe HTML commune pour tous les emails SIGR-CA."""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0a0c10;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0c10;padding:32px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#111318;border-radius:14px;border:1px solid rgba(255,255,255,0.07);overflow:hidden;max-width:560px;width:100%;">
        <tr>
          <td style="background:linear-gradient(135deg,{couleur_header},#06b6d4);padding:28px 36px;text-align:center;">
            <div style="font-size:28px;margin-bottom:10px;">🛡️</div>
            <h1 style="margin:0;color:#fff;font-size:20px;font-weight:600;">{titre}</h1>
            <p style="margin:6px 0 0;color:rgba(255,255,255,0.7);font-size:13px;">SIGR-CA — Système de Gestion des Ressources</p>
          </td>
        </tr>
        <tr>
          <td style="padding:28px 36px;">
            {contenu_html}
          </td>
        </tr>
        <tr>
          <td style="padding:16px 36px;border-top:1px solid rgba(255,255,255,0.05);text-align:center;">
            <p style="color:#4b5563;font-size:12px;margin:0;">© SIGR-CA — Email automatique, ne pas répondre.</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def envoyer_email(destinataire, sujet, texte_plain, html=None):
    """
    Envoie un email via SMTP port 587 + STARTTLS manuel.
    Compatible Python 3.12 (évite le bug keyfile/certfile de Django 4.x).
    Retourne True si succès, False sinon.
    """
    if not destinataire:
        logger.warning("envoyer_email: destinataire vide, email ignoré.")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = sujet
        msg['From'] = settings.DEFAULT_FROM_EMAIL
        msg['To'] = destinataire
        msg.attach(MIMEText(texte_plain, 'plain', 'utf-8'))
        if html:
            msg.attach(MIMEText(html, 'html', 'utf-8'))

        ctx = ssl.create_default_context()
        with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT) as server:
            server.ehlo()
            server.starttls(context=ctx)
            server.ehlo()
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            server.sendmail(settings.EMAIL_HOST_USER, destinataire, msg.as_string())

        logger.info(f"Email envoyé à {destinataire} — sujet: {sujet}")
        return True

    except Exception as e:
        logger.error(f"Erreur envoi email à {destinataire}: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Emails métier SIGR-CA
# ─────────────────────────────────────────────────────────────────────────────

def email_reservation_confirmee(employe, reservation, bureau_nom):
    """Email envoyé à l'employé quand sa réservation est confirmée."""
    prenom_nom = f"{employe.get('prenom', '')} {employe.get('nom', '')}".strip() or employe.get('email', '')
    date_debut = reservation['date_debut'].strftime('%d/%m/%Y à %H:%M')
    date_fin   = reservation['date_fin'].strftime('%H:%M')

    texte = f"""Bonjour {prenom_nom},

Votre réservation a été CONFIRMÉE.

  Titre      : {reservation.get('titre', 'Sans titre')}
  Date       : {date_debut} → {date_fin}
  Salle      : {bureau_nom}
  Participants: {reservation.get('nb_participants', 1)}

Présentez votre QR code au lecteur pour accéder à la salle.

Cordialement,
L'équipe SIGR-CA"""

    contenu_html = f"""
        <p style="color:#9ca3af;font-size:15px;margin:0 0 10px;">
          Bonjour <strong style="color:#f3f4f6;">{prenom_nom}</strong>,
        </p>
        <div style="background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.3);
                    border-radius:8px;padding:16px 20px;margin:0 0 20px;">
          <p style="margin:0;color:#6ee7b7;font-size:15px;font-weight:600;">✅ Réservation confirmée</p>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px;color:#9ca3af;">
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Titre</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;font-weight:500;">{reservation.get('titre','Sans titre')}</td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Date</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;">{date_debut} → {date_fin}</td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Salle</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;">{bureau_nom}</td></tr>
          <tr><td style="padding:8px 0;">
            <span style="color:#6b7280;">Participants</span></td>
            <td style="padding:8px 0;color:#f3f4f6;">{reservation.get('nb_participants',1)}</td></tr>
        </table>
        <p style="color:#9ca3af;font-size:14px;margin:20px 0 0;">
          🔐 Présentez votre <strong style="color:#f3f4f6;">QR code</strong> au lecteur pour accéder à la salle.
        </p>"""

    html = _build_html_email("Réservation confirmée", contenu_html, couleur_header='#10b981')
    return envoyer_email(
        employe.get('email'),
        f"✅ Réservation confirmée — {reservation.get('titre', 'Sans titre')}",
        texte, html
    )


def email_reservation_refusee(employe, reservation, motif):
    """Email envoyé à l'employé quand sa réservation est refusée."""
    prenom_nom = f"{employe.get('prenom', '')} {employe.get('nom', '')}".strip() or employe.get('email', '')
    date_debut = reservation['date_debut'].strftime('%d/%m/%Y à %H:%M')
    date_fin   = reservation['date_fin'].strftime('%H:%M')

    texte = f"""Bonjour {prenom_nom},

Votre réservation a été REFUSÉE.

  Titre  : {reservation.get('titre', 'Sans titre')}
  Date   : {date_debut} → {date_fin}
  Motif  : {motif}

Vous pouvez effectuer une nouvelle demande depuis votre espace employé.

Cordialement,
L'équipe SIGR-CA"""

    contenu_html = f"""
        <p style="color:#9ca3af;font-size:15px;margin:0 0 10px;">
          Bonjour <strong style="color:#f3f4f6;">{prenom_nom}</strong>,
        </p>
        <div style="background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);
                    border-radius:8px;padding:16px 20px;margin:0 0 20px;">
          <p style="margin:0;color:#fca5a5;font-size:15px;font-weight:600;">❌ Réservation refusée</p>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px;color:#9ca3af;">
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Titre</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;font-weight:500;">{reservation.get('titre','Sans titre')}</td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Date</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;">{date_debut} → {date_fin}</td></tr>
          <tr><td style="padding:8px 0;">
            <span style="color:#6b7280;">Motif du refus</span></td>
            <td style="padding:8px 0;color:#fca5a5;">{motif}</td></tr>
        </table>
        <p style="color:#9ca3af;font-size:14px;margin:20px 0 0;">
          Vous pouvez effectuer une nouvelle demande depuis votre 
          <a href="http://127.0.0.1:8000/employe/reservations/" style="color:#3b82f6;">espace employé</a>.
        </p>"""

    html = _build_html_email("Réservation refusée", contenu_html, couleur_header='#ef4444')
    return envoyer_email(
        employe.get('email'),
        f"❌ Réservation refusée — {reservation.get('titre', 'Sans titre')}",
        texte, html
    )


def email_rappel_reservation(employe, reservation, bureau_nom, minutes_avant=60):
    """Rappel envoyé X minutes avant une réservation."""
    prenom_nom = f"{employe.get('prenom', '')} {employe.get('nom', '')}".strip() or employe.get('email', '')
    date_debut = reservation['date_debut'].strftime('%d/%m/%Y à %H:%M')
    date_fin   = reservation['date_fin'].strftime('%H:%M')
    dans_combien = f"{minutes_avant} minute{'s' if minutes_avant > 1 else ''}"

    texte = f"""Bonjour {prenom_nom},

Rappel : votre réservation commence dans {dans_combien}.

  Titre  : {reservation.get('titre', 'Sans titre')}
  Date   : {date_debut} → {date_fin}
  Salle  : {bureau_nom}

N'oubliez pas votre QR code !

Cordialement,
L'équipe SIGR-CA"""

    contenu_html = f"""
        <p style="color:#9ca3af;font-size:15px;margin:0 0 10px;">
          Bonjour <strong style="color:#f3f4f6;">{prenom_nom}</strong>,
        </p>
        <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);
                    border-radius:8px;padding:16px 20px;margin:0 0 20px;">
          <p style="margin:0;color:#fcd34d;font-size:15px;font-weight:600;">
            ⏰ Rappel — dans {dans_combien}
          </p>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px;color:#9ca3af;">
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Titre</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;font-weight:500;">{reservation.get('titre','Sans titre')}</td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Date</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;">{date_debut} → {date_fin}</td></tr>
          <tr><td style="padding:8px 0;">
            <span style="color:#6b7280;">Salle</span></td>
            <td style="padding:8px 0;color:#f3f4f6;">{bureau_nom}</td></tr>
        </table>
        <p style="color:#9ca3af;font-size:14px;margin:20px 0 0;">
          🔐 N'oubliez pas votre <strong style="color:#f3f4f6;">QR code</strong> d'accès !
        </p>"""

    html = _build_html_email("Rappel de réservation", contenu_html, couleur_header='#f59e0b')
    return envoyer_email(
        employe.get('email'),
        f"⏰ Rappel — {reservation.get('titre', 'Sans titre')} dans {dans_combien}",
        texte, html
    )


def email_maintenance_ressource(employe_email, ressource_nom, date_debut, date_fin, motif=''):
    """Alerte envoyée quand une ressource réservée est mise en maintenance."""
    date_d = date_debut.strftime('%d/%m/%Y à %H:%M')
    date_f = date_fin.strftime('%d/%m/%Y à %H:%M')

    texte = f"""Bonjour,

La ressource "{ressource_nom}" que vous avez réservée sera indisponible :

  Du    : {date_d}
  Au    : {date_f}
  Motif : {motif or 'Maintenance planifiée'}

Veuillez contacter votre administrateur pour reprogrammer.

Cordialement,
L'équipe SIGR-CA"""

    contenu_html = f"""
        <div style="background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);
                    border-radius:8px;padding:16px 20px;margin:0 0 20px;">
          <p style="margin:0;color:#fcd34d;font-size:15px;font-weight:600;">
            🔧 Ressource indisponible — {ressource_nom}
          </p>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px;color:#9ca3af;">
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Ressource</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;font-weight:500;">{ressource_nom}</td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Du</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;">{date_d}</td></tr>
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Au</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;">{date_f}</td></tr>
          <tr><td style="padding:8px 0;">
            <span style="color:#6b7280;">Motif</span></td>
            <td style="padding:8px 0;color:#f3f4f6;">{motif or 'Maintenance planifiée'}</td></tr>
        </table>
        <p style="color:#9ca3af;font-size:14px;margin:20px 0 0;">
          Contactez votre administrateur pour reprogrammer votre réservation.
        </p>"""

    html = _build_html_email("Ressource indisponible", contenu_html, couleur_header='#f59e0b')
    return envoyer_email(
        employe_email,
        f"🔧 Indisponibilité planifiée — {ressource_nom}",
        texte, html
    )


def email_badge_rfid_affecte(employe, badge_id, type_badge='RFID'):
    """Email envoyé à l'employé quand un badge lui est affecté."""
    prenom_nom = f"{employe.get('prenom', '')} {employe.get('nom', '')}".strip() or employe.get('email', '')
    type_label = 'QR Code' if type_badge == 'QR' else 'Badge RFID'
    icone = '📱' if type_badge == 'QR' else '💳'

    texte = f"""Bonjour {prenom_nom},

Votre {type_label} d'accès a été configuré.

  Identifiant : {badge_id}
  Type        : {type_label}

Vous pouvez maintenant accéder aux zones autorisées.
Consultez votre badge virtuel dans votre espace employé.

Cordialement,
L'équipe SIGR-CA"""

    contenu_html = f"""
        <p style="color:#9ca3af;font-size:15px;margin:0 0 10px;">
          Bonjour <strong style="color:#f3f4f6;">{prenom_nom}</strong>,
        </p>
        <div style="background:rgba(31,111,235,0.1);border:1px solid rgba(31,111,235,0.3);
                    border-radius:8px;padding:16px 20px;margin:0 0 20px;">
          <p style="margin:0;color:#93c5fd;font-size:15px;font-weight:600;">
            {icone} {type_label} configuré avec succès
          </p>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px;color:#9ca3af;">
          <tr><td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="color:#6b7280;">Identifiant</span></td>
            <td style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);
                       color:#f3f4f6;font-family:monospace;font-size:13px;">{badge_id}</td></tr>
          <tr><td style="padding:8px 0;">
            <span style="color:#6b7280;">Type</span></td>
            <td style="padding:8px 0;color:#f3f4f6;">{type_label}</td></tr>
        </table>
        <p style="color:#9ca3af;font-size:14px;margin:20px 0 0;">
          Accédez à votre 
          <a href="http://127.0.0.1:8000/employe/badge-virtuel/" style="color:#3b82f6;">badge virtuel</a>
          pour voir votre QR code d'accès.
        </p>"""

    html = _build_html_email(f"{type_label} configuré", contenu_html)
    return envoyer_email(
        employe.get('email'),
        f"{icone} Votre {type_label} SIGR-CA est prêt",
        texte, html
    )