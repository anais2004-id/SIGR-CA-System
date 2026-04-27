from django.core.management.base import BaseCommand
from dashboard.ai_engine import train_all_models

class Command(BaseCommand):
    help = "Entraîne tous les modèles IA SIGR-CA sur les données MongoDB."

    def handle(self, *args, **options):
        self.stdout.write("🤖 Entraînement des modèles IA en cours...")
        results = train_all_models()
        for name, ok in results.items():
            symbol = "✅" if ok else "❌"
            self.stdout.write(f"  {symbol} {name}")
        self.stdout.write(self.style.SUCCESS("Terminé."))