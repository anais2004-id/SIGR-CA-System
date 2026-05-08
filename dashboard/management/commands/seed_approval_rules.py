from django.core.management.base import BaseCommand
from dashboard.models import ApprovalRule

class Command(BaseCommand):
    help = "Initialise les règles d'approbation par défaut"

    def handle(self, *args, **kwargs):
        rules = [
            {
                'nom': 'Auto-approbation Admin',
                'role_demandeur': 'admin',
                'auto_approuve': True,
                'niveaux_requis': 0,
                'priorite': 100,
                'actif': True,
            },
            {
                'nom': 'Auto-approbation Directeur',
                'role_demandeur': 'directeur',
                'auto_approuve': True,
                'niveaux_requis': 0,
                'priorite': 90,
                'actif': True,
            },
            {
                'nom': 'Réservation courte (<2h) — 1 niveau',
                'role_demandeur': 'employe',
                'duree_max_minutes': 120,
                'auto_approuve': False,
                'niveaux_requis': 1,
                'priorite': 50,
                'actif': True,
            },
            {
                'nom': 'Réservation longue (>2h) — 2 niveaux',
                'role_demandeur': 'employe',
                'duree_min_minutes': 120,
                'auto_approuve': False,
                'niveaux_requis': 2,
                'priorite': 40,
                'actif': True,
            },
            {
                'nom': 'Règle par défaut',
                'role_demandeur': '*',
                'auto_approuve': False,
                'niveaux_requis': 1,
                'priorite': 1,
                'actif': True,
            },
        ]

        created, updated = 0, 0
        for r in rules:
            obj, was_created = ApprovalRule.objects.update_or_create(
                nom=r['nom'], defaults=r
            )
            if was_created: created += 1
            else: updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"✅ {created} règle(s) créée(s), {updated} mise(s) à jour."
        ))
