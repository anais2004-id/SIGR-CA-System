from django.core.management.base import BaseCommand
from django.conf import settings
from datetime import datetime, timedelta

db = settings.MONGO_DB

class Command(BaseCommand):
    help = 'Envoie les emails de rappel de retour de ressource J-1'

    def handle(self, *args, **options):
        maintenant = datetime.now()
        # Chercher les rappels à envoyer (heure actuelle ± 30 min)
        rappels = db.rappels_email.find({
            'envoye': False,
            'type': 'retour_ressource',
            'a_envoyer_le': {
                '$gte': maintenant - timedelta(minutes=30),
                '$lte': maintenant + timedelta(minutes=30),
            }
        })

        for rappel in rappels:
            try:
                reservation = db.reservations.find_one({'_id': rappel['reservation_id']})
                employe_id = rappel.get('employe_id')
                employe = db.employees.find_one({'_id': employe_id}) or \
                          db.employees.find_one({'django_user_id': employe_id})

                if employe and employe.get('email') and reservation:
                    from dashboard.utils_email import envoyer_email
                    ressource_nom = reservation.get('bureau_nom') or reservation.get('materiel_nom', 'ressource')
                    date_fin = reservation['date_fin'].strftime('%d/%m/%Y à %H:%M')
                    
                    envoyer_email(
                        employe['email'],
                        f"⏰ Rappel : retour de ressource demain — {ressource_nom}",
                        f"Bonjour {employe.get('prenom', '')},\n\n"
                        f"Rappel : vous avez emprunté « {ressource_nom} ».\n"
                        f"Sa date de retour est prévue le {date_fin}.\n\n"
                        f"Merci de la restituer à temps.\n\n"
                        f"Cordialement,\nL'équipe SIGR-CA"
                    )
                    
                    db.rappels_email.update_one(
                        {'_id': rappel['_id']},
                        {'$set': {'envoye': True, 'envoye_le': maintenant}}
                    )
                    self.stdout.write(f"✅ Rappel envoyé à {employe.get('email')}")

            except Exception as e:
                self.stdout.write(f"❌ Erreur rappel {rappel['_id']}: {e}")