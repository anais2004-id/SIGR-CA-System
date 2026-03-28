#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
# init_equipements.py
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['controle_acces_db']

# Créer la collection equipements si elle n'existe pas
if 'equipements' not in db.list_collection_names():
    db.create_collection('equipements')
    print("✅ Collection 'equipements' créée")

# Ajouter des équipements de test
equipements_test = [
    {
        'nom': 'Lecteur RFID Entrée Principale',
        'type': 'RFID',
        'code': 'RDR-001',
        'emplacement': 'Entrée principale',
        'bureau_id': None,  # Sera lié à un bureau
        'ip_address': '192.168.1.101',
        'port': 5000,
        'statut': 'actif',
        'derniere_connexion': None,
        'created_at': datetime.now()
    },
    {
        'nom': 'Lecteur RFID Direction',
        'type': 'RFID',
        'code': 'RDR-002',
        'emplacement': 'Direction Générale',
        'bureau_id': None,
        'ip_address': '192.168.1.102',
        'port': 5000,
        'statut': 'actif',
        'derniere_connexion': None,
        'created_at': datetime.now()
    },
    {
        'nom': 'Scanner QR Code Accueil',
        'type': 'QR',
        'code': 'QR-001',
        'emplacement': 'Hall d\'accueil',
        'bureau_id': None,
        'ip_address': '192.168.1.103',
        'port': 5001,
        'statut': 'actif',
        'derniere_connexion': None,
        'created_at': datetime.now()
    },
    {
        'nom': 'Scanner QR Code Salle Serveur',
        'type': 'QR',
        'code': 'QR-002',
        'emplacement': 'Salle Serveur',
        'bureau_id': None,
        'ip_address': '192.168.1.104',
        'port': 5001,
        'statut': 'actif',
        'derniere_connexion': None,
        'created_at': datetime.now()
    }
]

for equip in equipements_test:
    db.equipements.update_one(
        {'code': equip['code']},
        {'$setOnInsert': equip},
        upsert=True
    )
    print(f"✅ Équipement ajouté: {equip['nom']}")

print("\n📊 Liste des équipements:")
for e in db.equipements.find():
    print(f"  - {e['nom']} ({e['type']}) - Code: {e['code']} - Statut: {e['statut']}")