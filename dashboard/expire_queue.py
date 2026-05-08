from django.core.management.base import BaseCommand
from dashboard.queue_service import QueueService

class Command(BaseCommand):
    help = "Expire les notifications de file d'attente non confirmées"
    def handle(self, *args, **kwargs):
        QueueService.expirer_notifications()
        self.stdout.write(self.style.SUCCESS("File d'attente nettoyée."))
