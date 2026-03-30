# models.py
from django.contrib.auth.models import AbstractUser
from django.db import models

class Utilisateur(AbstractUser):
    """Modèle utilisateur personnalisé"""
    badge_rfid = models.CharField(max_length=50, blank=True, null=True, unique=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    poste = models.CharField(max_length=100, blank=True, null=True)
    departement = models.CharField(max_length=100, blank=True, null=True)

    # IMPORTANT : on change les related_name pour éviter les conflits
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='utilisateur_set',      # ← Changé
        blank=True,
        help_text='The groups this user belongs to.'
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='utilisateur_set',      # ← Changé
        blank=True,
        help_text='Specific permissions for this user.'
    )

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.username})"