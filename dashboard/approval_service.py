# dashboard/approval_service.py
from django.utils import timezone
from datetime import timedelta
from .models import (
    ApprovalRule, ApprovalRequest, ApprovalAuditLog,
    ZoneManager, ApprovalDelegation, Notification
)

class ApprovalService:

    # -----------------------------------------------------------------
    @staticmethod
    def evaluer_regles(reservation: dict, user_role: str) -> dict:
        """
        Détermine si auto-approbation et le niveau requis.
        reservation : dict {categorie, duree_minutes, nb_participants, ...}
        Retourne {'auto': bool, 'niveau_max': int, 'rule': ApprovalRule|None}
        """
        duree = reservation.get('duree_minutes', 0)
        cat   = reservation.get('categorie', '')
        nb    = reservation.get('nb_participants', 1)

        rules = [r for r in ApprovalRule.objects.all().order_by('priorite') if r.actif]
        for r in rules:
            if r.role_concerne and r.role_concerne != user_role:
                continue
            if r.categorie_ressource and r.categorie_ressource != cat:
                continue
            if r.duree_max_minutes and duree > r.duree_max_minutes:
                continue
            if r.nb_participants_max and nb > r.nb_participants_max:
                continue
            return {
                'auto': r.auto_approve,
                'niveau_max': r.niveau_approbation_requis,
                'rule': r,
            }
        # Défaut : approbation niveau 1
        return {'auto': False, 'niveau_max': 1, 'rule': None}

    # -----------------------------------------------------------------
    @staticmethod
    def get_approbateur(zone_id: str, niveau: int = 1):
        """Retourne le manager actif (en tenant compte des délégations)."""
        try:
            zm = ZoneManager.objects.get(zone_id=zone_id,
                                         niveau=niveau, actif=True)
        except ZoneManager.DoesNotExist:
            return None

        # Vérifier délégation active
        deleg = ApprovalDelegation.objects.filter(
            delegant_id=zm.manager_id, actif=True,
            date_debut__lte=timezone.now(),
            date_fin__gte=timezone.now()
        ).first()
        if deleg:
            return {
                'id':   deleg.delegataire_id,
                'nom':  deleg.delegataire_nom,
                'email':deleg.delegataire_email,
                'delegue': True,
            }
        return {'id': zm.manager_id, 'nom': zm.manager_nom,
                'email': zm.manager_email, 'delegue': False}

    # -----------------------------------------------------------------
    @classmethod
    def creer_workflow(cls, reservation_id, reservation_data,
                       user, ip=None):
        """
        Crée la 1ère demande d'approbation OU auto-approuve
        selon les règles. Doit être appelée juste après l'insertion
        de la réservation.
        """
        eval_ = cls.evaluer_regles(reservation_data,
                                   getattr(user, 'role', 'employe'))

        # Auto-approbation
        if eval_['auto']:
            ar = ApprovalRequest.objects.create(
                reservation_id=reservation_id,
                niveau=1, niveau_max=eval_['niveau_max'],
                statut='approuvee',
                auto_approuvee=True,
                decided_at=timezone.now(),
                decided_by_id=str(user.id),
                decided_by_nom=user.get_full_name() or user.username,
                commentaire="Auto-approuvé par règle " +
                            (eval_['rule'].nom if eval_['rule'] else 'défaut'),
            )
            cls._log(reservation_id, ar.id, 'auto_approve', user,
                     'en_attente', 'confirmee', ip,
                     f"Règle: {eval_['rule'].nom if eval_['rule'] else '-'}")
            return {'auto': True, 'request': ar, 'nouveau_statut': 'confirmee'}

        # Sinon : créer demande niveau 1
        approb = cls.get_approbateur(reservation_data.get('bureau_id', ''), 1)
        ar = ApprovalRequest.objects.create(
            reservation_id=reservation_id,
            niveau=1,
            niveau_max=eval_['niveau_max'],
            approbateur_id=(approb['id'] if approb else ''),
            approbateur_nom=(approb['nom'] if approb else ''),
            statut='en_attente',
            date_limite=timezone.now() + timedelta(hours=48),
        )
        cls._log(reservation_id, ar.id, 'creation', user,
                 '', 'en_attente', ip)

        # Notifier l'approbateur
        if approb:
            Notification.objects.create(
                user_id=approb['id'],
                titre="Nouvelle demande d'approbation",
                message=f"Réservation {reservation_data.get('titre','')} "
                        f"à approuver (niveau 1)",
                categorie='reservation',
                icon='✅',
                action_url=f'/reservations/{reservation_id}/approuver/',
                reservation_id=reservation_id,
            )
        return {'auto': False, 'request': ar, 'nouveau_statut': 'en_attente'}

    # -----------------------------------------------------------------
    @classmethod
    def approuver(cls, approval_id, user, commentaire='', ip=None):
        ar = ApprovalRequest.objects.get(id=approval_id)
        if ar.statut != 'en_attente':
            return {'ok': False, 'error': 'Déjà traitée'}

        ar.statut = 'approuvee'
        ar.decided_at = timezone.now()
        ar.decided_by_id = str(user.id)
        ar.decided_by_nom = user.get_full_name() or user.username
        ar.commentaire = commentaire
        ar.save()

        cls._log(ar.reservation_id, ar.id, 'approbation', user,
                 'en_attente', 'approuvee', ip, commentaire)

        # Niveau supérieur requis ?
        if ar.niveau < ar.niveau_max:
            # Créer demande niveau suivant
            from .models import Reservation  # ou requête Mongo
            ar_next = ApprovalRequest.objects.create(
                reservation_id=ar.reservation_id,
                niveau=ar.niveau + 1,
                niveau_max=ar.niveau_max,
                statut='en_attente',
                date_limite=timezone.now() + timedelta(hours=48),
            )
            cls._log(ar.reservation_id, ar_next.id, 'escalade', user,
                     '', 'en_attente', ip,
                     f"Escalade vers niveau {ar_next.niveau}")
            return {'ok': True, 'final': False}

        # Approbation finale → confirmer la réservation (Mongo)
        cls._maj_statut_reservation(ar.reservation_id, 'confirmee')
        return {'ok': True, 'final': True}

    # -----------------------------------------------------------------
    @classmethod
    def rejeter(cls, approval_id, user, commentaire='', ip=None):
        ar = ApprovalRequest.objects.get(id=approval_id)
        ar.statut = 'rejetee'
        ar.decided_at = timezone.now()
        ar.decided_by_id = str(user.id)
        ar.decided_by_nom = user.get_full_name() or user.username
        ar.commentaire = commentaire
        ar.save()
        cls._log(ar.reservation_id, ar.id, 'rejet', user,
                 'en_attente', 'rejetee', ip, commentaire)
        cls._maj_statut_reservation(ar.reservation_id, 'annulee')
        # → libérer la file d'attente (voir fonctionnalité 2)
        from .queue_service import QueueService
        QueueService.notifier_prochain(ar.reservation_id)
        return {'ok': True}

    # -----------------------------------------------------------------
    @staticmethod
    def _maj_statut_reservation(reservation_id, statut):
        """Met à jour la collection Mongo `reservations`."""
        try:
            from bson import ObjectId
            from config.mongo import db   # adapte au chemin réel
            db.reservations.update_one(
                {'_id': ObjectId(reservation_id)},
                {'$set': {'statut': statut,
                          'updated_at': timezone.now()}}
            )
        except Exception as e:
            print(f"[Approval] Maj Mongo échouée : {e}")

    @staticmethod
    def _log(reservation_id, approval_id, action, user,
             ancien, nouveau, ip, commentaire=''):
        ApprovalAuditLog.objects.create(
            reservation_id=reservation_id,
            approval_request_id=approval_id,
            action=action,
            acteur_id=str(user.id),
            acteur_nom=user.get_full_name() or user.username,
            acteur_role=getattr(user, 'role', ''),
            ancien_statut=ancien,
            nouveau_statut=nouveau,
            commentaire=commentaire,
            ip_address=ip,
        )
