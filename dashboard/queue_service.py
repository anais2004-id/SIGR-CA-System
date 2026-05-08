# dashboard/queue_service.py
from datetime import timedelta
from django.utils import timezone
from .models import WaitingQueue, Notification

class QueueService:

    # -----------------------------------------------------------------
    @staticmethod
    def ajouter(resource_id, resource_nom, user, date_debut, date_fin,
                titre='', nb_participants=1, flexible_minutes=30):
        """Ajoute en queue, retourne la position."""
        derniere = WaitingQueue.objects.filter(
            resource_id=resource_id, statut='en_attente'
        ).order_by('-position').first()
        position = (derniere.position + 1) if derniere else 1

        wq = WaitingQueue.objects.create(
            resource_id=resource_id,
            resource_nom=resource_nom,
            user_id=str(user.id),
            user_nom=user.get_full_name() or user.username,
            user_email=user.email,
            date_debut_souhaitee=date_debut,
            date_fin_souhaitee=date_fin,
            nb_participants=nb_participants,
            titre=titre,
            flexible_minutes=flexible_minutes,
            position=position,
        )
        return wq

    # -----------------------------------------------------------------
    @staticmethod
    def proposer_alternatives(resource_id, date_debut, date_fin,
                              flexible_minutes=120, max_propositions=3):
        """
        Cherche des créneaux libres autour du créneau demandé.
        Utilise la collection Mongo `reservations`.
        """
        from bson import ObjectId
        from config.mongo import db   # adapte
        duree = date_fin - date_debut
        propositions = []

        # Pas de 30 min, on essaye -2h à +4h
        for delta_min in range(-flexible_minutes, flexible_minutes*2+1, 30):
            if delta_min == 0:
                continue
            d1 = date_debut + timedelta(minutes=delta_min)
            d2 = d1 + duree
            conflit = db.reservations.find_one({
                'resource_id': str(resource_id),
                'statut': {'$in': ['confirmee', 'en_attente']},
                'date_debut': {'$lt': d2},
                'date_fin':   {'$gt': d1},
            })
            if not conflit:
                propositions.append({'date_debut': d1, 'date_fin': d2,
                                     'decalage_min': delta_min})
                if len(propositions) >= max_propositions:
                    break
        return propositions

    # -----------------------------------------------------------------
    @classmethod
    def notifier_prochain(cls, reservation_id_libere=None,
                          resource_id=None):
        """
        Appelé quand une réservation est annulée / rejetée / terminée.
        Notifie le 1er en file d'attente.
        """
        # Retrouver la ressource libérée si pas fournie
        if resource_id is None and reservation_id_libere:
            try:
                from bson import ObjectId
                from config.mongo import db
                r = db.reservations.find_one(
                    {'_id': ObjectId(reservation_id_libere)})
                if r:
                    resource_id = r.get('resource_id')
            except Exception:
                pass
        if not resource_id:
            return

        suivant = WaitingQueue.objects.filter(
            resource_id=resource_id, statut='en_attente'
        ).order_by('position').first()
        if not suivant:
            return

        suivant.statut = 'notifie'
        suivant.notifie_at = timezone.now()
        suivant.expire_at = timezone.now() + timedelta(hours=2)
        suivant.save()

        Notification.objects.create(
            user_id=suivant.user_id,
            titre="🎉 Ressource disponible !",
            message=f"La ressource {suivant.resource_nom} est libre. "
                    f"Vous avez 2h pour confirmer votre réservation.",
            categorie='reservation',
            icon='🎉',
            action_url=f'/queue/{suivant.id}/confirmer/',
        )
        return suivant

    # -----------------------------------------------------------------
    @classmethod
    def expirer_notifications(cls):
        """À appeler par cron / management command."""
        expired = WaitingQueue.objects.filter(
            statut='notifie', expire_at__lt=timezone.now()
        )
        for wq in expired:
            wq.statut = 'expire'
            wq.save()
            cls.notifier_prochain(resource_id=wq.resource_id)
