# dashboard/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser

class Utilisateur(AbstractUser):
    """Modèle utilisateur personnalisé"""
    badge_rfid = models.CharField(max_length=50, blank=True, null=True, unique=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    poste = models.CharField(max_length=100, blank=True, null=True)
    departement = models.CharField(max_length=100, blank=True, null=True)

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='utilisateur_set',
        blank=True,
        help_text='The groups this user belongs to.'
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='utilisateur_set',
        blank=True,
        help_text='Specific permissions for this user.'
    )
# dashboard/models.py - Ajoutez cette classe après Utilisateur

class UserSession(models.Model):
    """Suivi des sessions utilisateur"""
    user = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    login_time = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'user_sessions'
        ordering = ['-last_activity']
    
    def __str__(self):
        return f"{self.user.username} - {self.login_time}"
    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.username})"


class AccessRule(models.Model):
    """Règle d'accès pour un employé"""
    employe_id = models.CharField(max_length=50)
    zone_nom = models.CharField(max_length=100)
    jour = models.IntegerField()
    mois = models.IntegerField()
    annee = models.IntegerField()
    heure_debut = models.CharField(max_length=5, default='08:00')
    heure_fin = models.CharField(max_length=5, default='18:00')
    acces_autorise = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'access_rules'


class Resource(models.Model):
    """Ressource (salle, matériel, équipement)"""
    CATEGORY_CHOICES = [
        ('salle', 'Salle'),
        ('materiel', 'Matériel'),
        ('equipement', 'Équipement'),
        ('vehicule', 'Véhicule'),
        ('laboratoire', 'Laboratoire'),
        ('autre', 'Autre'),
    ]
    
    STATUS_CHOICES = [
        ('disponible', 'Disponible'),
        ('occupe', 'Occupé'),
        ('maintenance', 'En maintenance'),
        ('reserve', 'Réservé'),
        ('hors_service', 'Hors service'),
    ]
    
    nom = models.CharField(max_length=200)
    categorie = models.CharField(max_length=50, choices=CATEGORY_CHOICES)
    description = models.TextField(blank=True)
    photo = models.TextField(blank=True)
    caracteristiques = models.JSONField(default=dict)
    localisation = models.CharField(max_length=200, blank=True)
    bureau_associe = models.CharField(max_length=100, blank=True)
    statut = models.CharField(max_length=50, choices=STATUS_CHOICES, default='disponible')
    capacite = models.IntegerField(default=1)
    disponibilite_heures = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=100, blank=True)
    
    class Meta:
        db_table = 'resources'


class Reservation(models.Model):
    """Réservation de ressource"""
    STATUS_CHOICES = [
        ('confirmee', 'Confirmée'),
        ('en_attente', 'En attente'),
        ('annulee', 'Annulée'),
        ('terminee', 'Terminée'),
    ]
    
    titre = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    resource_id = models.CharField(max_length=50)
    resource_type = models.CharField(max_length=50)
    bureau_id = models.CharField(max_length=50, blank=True)
    employe_id = models.CharField(max_length=50)
    employe_nom = models.CharField(max_length=200, blank=True)
    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField()
    nb_participants = models.IntegerField(default=1)
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmee')
    recurrence = models.CharField(max_length=20, blank=True)
    recurrence_end = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'reservations'


class Notification(models.Model):
    """Notification envoyée"""
    TYPE_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('webhook', 'Webhook'),
    ]
    CATEGORY_CHOICES = [
        ('confirmation', 'Confirmation'),
        ('rappel', 'Rappel'),
        ('annulation', 'Annulation'),
        ('alerte', 'Alerte'),
        ('maintenance', 'Maintenance'),
    ]
    
    destinataire = models.CharField(max_length=200)
    type_notification = models.CharField(max_length=10, choices=TYPE_CHOICES)
    categorie = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    sujet = models.CharField(max_length=200)
    message = models.TextField()
    statut = models.CharField(max_length=20, default='envoyee')
    reservation_id = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'notifications'