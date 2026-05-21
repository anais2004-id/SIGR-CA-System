from django.core.management.base import BaseCommand
from dashboard.views import send_rappel_retour_ressource

class Command(BaseCommand):
    help = 'Envoie les rappels de retour de matériel pour les réservations se terminant demain'

    def handle(self, *args, **kwargs):
        send_rappel_retour_ressource()
        self.stdout.write(self.style.SUCCESS('✅ Rappels envoyés avec succès.'))