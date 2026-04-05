# dashboard/models.py
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta


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
    
    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
    
    def __str__(self):
        return f"{self.username} ({self.get_full_name()})"


User = get_user_model()


class UserSession(models.Model):
    """Modèle pour suivre les sessions utilisateur"""
    DEVICE_CHOICES = [
        ('desktop', 'Ordinateur'),
        ('mobile', 'Mobile'),
        ('tablet', 'Tablette'),
        ('unknown', 'Inconnu'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_key = models.CharField(max_length=40, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=20, choices=DEVICE_CHOICES, default='unknown')
    location = models.CharField(max_length=200, blank=True, null=True)
    login_time = models.DateTimeField(default=timezone.now)
    last_activity = models.DateTimeField(auto_now=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name = 'Session utilisateur'
        verbose_name_plural = 'Sessions utilisateurs'
        ordering = ['-last_activity']
        indexes = [
            models.Index(fields=['session_key']),
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['is_active', 'last_activity']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.ip_address} - {self.last_activity.strftime('%d/%m/%Y %H:%M')}"
    
    def get_duration(self):
        """Durée de la session"""
        if self.logout_time:
            end = self.logout_time
        else:
            end = timezone.now()
        delta = end - self.login_time
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        if delta.days > 0:
            return f"{delta.days}j {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    def get_status(self):
        """Statut de la session"""
        if not self.is_active:
            return 'terminated'
        delta = timezone.now() - self.last_activity
        if delta.seconds < 300:  # 5 minutes
            return 'active'
        elif delta.seconds < 1800:  # 30 minutes
            return 'idle'
        else:
            return 'inactive'
    
    def get_status_badge(self):
        """Badge de statut HTML"""
        status = self.get_status()
        if status == 'active':
            return '<span class="badge b-green">🟢 Actif</span>'
        elif status == 'idle':
            return '<span class="badge b-amber">🟡 Inactif</span>'
        elif status == 'inactive':
            return '<span class="badge b-red">🔴 Très inactif</span>'
        else:
            return '<span class="badge b-gray">⚫ Terminé</span>'


class SessionLog(models.Model):
    """Historique des connexions/déconnexions"""
    ACTION_CHOICES = [
        ('login', 'Connexion'),
        ('logout', 'Déconnexion'),
        ('timeout', 'Expiration'),
        ('terminated', 'Terminée par admin'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='session_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    session_key = models.CharField(max_length=40, blank=True)
    
    class Meta:
        verbose_name = 'Historique session'
        verbose_name_plural = 'Historique des sessions'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['action', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.action} - {self.timestamp.strftime('%d/%m/%Y %H:%M')}"


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
        verbose_name = "Règle d'accès"
        verbose_name_plural = "Règles d'accès"
        unique_together = [['employe_id', 'zone_nom', 'jour', 'mois', 'annee']]
    
    def __str__(self):
        return f"{self.employe_id} - {self.zone_nom} - {self.jour}/{self.mois}/{self.annee}"


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
        verbose_name = 'Ressource'
        verbose_name_plural = 'Ressources'
        ordering = ['categorie', 'nom']
    
    def __str__(self):
        return f"{self.nom} ({self.get_categorie_display()})"
    
    def is_available(self, date_debut, date_fin):
        """Vérifie si la ressource est disponible sur un créneau"""
        from dashboard.models import Reservation
        conflicts = Reservation.objects.filter(
            resource_id=str(self.id),
            statut__in=['confirmee', 'en_attente'],
            date_debut__lt=date_fin,
            date_fin__gt=date_debut
        ).exists()
        return not conflicts and self.statut == 'disponible'


class Reservation(models.Model):
    """Réservation de ressource"""
    STATUS_CHOICES = [
        ('confirmee', 'Confirmée'),
        ('en_attente', 'En attente'),
        ('annulee', 'Annulée'),
        ('terminee', 'Terminée'),
    ]
    
    RECURRENCE_CHOICES = [
        ('none', 'Aucune'),
        ('daily', 'Quotidienne'),
        ('weekly', 'Hebdomadaire'),
        ('monthly', 'Mensuelle'),
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
    recurrence = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default='none')
    recurrence_end = models.DateTimeField(blank=True, null=True)
    created_by = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.CharField(max_length=100, blank=True)
    
    class Meta:
        db_table = 'reservations'
        verbose_name = 'Réservation'
        verbose_name_plural = 'Réservations'
        ordering = ['-date_debut']
        indexes = [
            models.Index(fields=['resource_id', 'statut']),
            models.Index(fields=['employe_id', 'date_debut']),
            models.Index(fields=['date_debut', 'date_fin']),
        ]
    
    def __str__(self):
        return f"{self.titre} - {self.date_debut.strftime('%d/%m/%Y %H:%M')}"
    
    def get_duration(self):
        """Durée de la réservation"""
        delta = self.date_fin - self.date_debut
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        if delta.days > 0:
            return f"{delta.days}j {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    def cancel(self, cancelled_by):
        """Annuler la réservation"""
        self.statut = 'annulee'
        self.cancelled_at = timezone.now()
        self.cancelled_by = cancelled_by
        self.save()


class Notification(models.Model):
    """Notification envoyée"""
    TYPE_CHOICES = [
        ('email', 'Email'),
        ('sms', 'SMS'),
        ('webhook', 'Webhook'),
        ('push', 'Push'),
    ]
    CATEGORY_CHOICES = [
        ('confirmation', 'Confirmation'),
        ('rappel', 'Rappel'),
        ('annulation', 'Annulation'),
        ('alerte', 'Alerte'),
        ('maintenance', 'Maintenance'),
        ('info', 'Information'),
    ]
    STATUS_CHOICES = [
        ('envoyee', 'Envoyée'),
        ('echouee', 'Échouée'),
        ('en_attente', 'En attente'),
    ]
    
    destinataire = models.CharField(max_length=200)
    type_notification = models.CharField(max_length=10, choices=TYPE_CHOICES)
    categorie = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    sujet = models.CharField(max_length=200)
    message = models.TextField()
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default='envoyee')
    reservation_id = models.CharField(max_length=50, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        db_table = 'notifications'
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"{self.sujet} - {self.destinataire} - {self.sent_at.strftime('%d/%m/%Y %H:%M')}"


class SystemConfig(models.Model):
    """Configuration système"""
    key = models.CharField(max_length=100, unique=True)
    value = models.JSONField(default=dict)
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=100, blank=True)
    
    class Meta:
        db_table = 'system_config'
        verbose_name = 'Configuration système'
        verbose_name_plural = 'Configurations système'
    
    def __str__(self):
        return self.key


class AdminProfile(models.Model):
    """Profil administrateur"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.TextField(blank=True)
    notifications_enabled = models.BooleanField(default=True)
    theme = models.CharField(max_length=20, default='dark')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'admin_profiles'
        verbose_name = 'Profil administrateur'
        verbose_name_plural = 'Profils administrateurs'
    
    def __str__(self):
        return f"Profil de {self.user.username}"