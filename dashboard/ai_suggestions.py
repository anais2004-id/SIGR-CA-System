# dashboard/ai_suggestions.py
import json
import random
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import numpy as np

class SmartSuggestionEngine:
    """Moteur de suggestions intelligentes basé sur l'analyse des habitudes"""
    
    def __init__(self, db):
        self.db = db
    
    def get_user_preferences(self, employe_id):
        """Récupère les préférences d'un utilisateur"""
        employe = self.db.employees.find_one({'_id': employe_id})
        if not employe:
            return {}
        return employe.get('preferences_reservation', {
            'preferred_days': ['monday', 'tuesday', 'wednesday', 'thursday'],
            'preferred_hours_start': [9, 10, 11, 14, 15],
            'preferred_duration': 60,
            'avoid_overlap': True,
            'preferred_rooms': []
        })
    
    def get_user_history(self, employe_id, days=90):
        """Analyse l'historique des réservations de l'utilisateur"""
        start_date = datetime.now() - timedelta(days=days)
        
        reservations = list(self.db.reservations.find({
            'employe_id': str(employe_id),
            'date_debut': {'$gte': start_date},
            'statut': 'confirmee'
        }))
        
        if not reservations:
            return None
        
        # Analyse des jours préférés
        days_count = Counter()
        hours_count = Counter()
        durations = []
        room_preferences = Counter()
        
        for r in reservations:
            if r.get('date_debut'):
                day = r['date_debut'].strftime('%A').lower()
                hour = r['date_debut'].hour
                days_count[day] += 1
                hours_count[hour] += 1
                
                if r.get('date_fin') and r.get('date_debut'):
                    duration = (r['date_fin'] - r['date_debut']).seconds // 3600
                    durations.append(duration)
                
                if r.get('bureau_id'):
                    room_preferences[str(r['bureau_id'])] += 1
        
        # Calcul des moyennes
        avg_duration = int(np.mean(durations)) if durations else 60
        
        # Top 3 jours préférés
        top_days = [day for day, _ in days_count.most_common(3)]
        # Top 5 heures préférées
        top_hours = [hour for hour, _ in hours_count.most_common(5)]
        
        return {
            'preferred_days': top_days,
            'preferred_hours': top_hours,
            'avg_duration': avg_duration,
            'total_reservations': len(reservations),
            'room_preferences': {k: v for k, v in room_preferences.most_common(5)}
        }
    
    def get_room_availability_pattern(self, bureau_id, days=30):
        """Analyse les créneaux disponibles d'une salle"""
        start_date = datetime.now() - timedelta(days=days)
        
        # Réservations existantes
        reservations = list(self.db.reservations.find({
            'bureau_id': bureau_id,
            'date_debut': {'$gte': start_date},
            'statut': {'$in': ['confirmee', 'en_attente']}
        }))
        
        # Créer une matrice d'occupation (jours x heures)
        occupation = defaultdict(lambda: defaultdict(int))
        
        for r in reservations:
            if r.get('date_debut') and r.get('date_fin'):
                current = r['date_debut']
                end = r['date_fin']
                while current < end:
                    day = current.strftime('%A').lower()
                    hour = current.hour
                    occupation[day][hour] += 1
                    current += timedelta(hours=1)
        
        # Calculer les créneaux libres typiques
        available_slots = []
        days_order = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        
        for day in days_order:
            for hour in range(8, 19):  # 8h à 18h
                occupation_rate = occupation[day].get(hour, 0)
                # Taux d'occupation typique sur cette tranche
                total_days = days
                rate = (occupation_rate / total_days * 100) if total_days > 0 else 0
                
                if rate < 30:  # Moins de 30% d'occupation
                    available_slots.append({
                        'day': day,
                        'hour': hour,
                        'availability_rate': 100 - rate,
                        'confidence': 'high' if rate < 15 else 'medium'
                    })
        
        return available_slots
    
    def suggest_alternative_slots_advanced(self, resource_id, date_debut, date_fin, employe_id=None):
        """Suggestions avancées avec IA"""
        suggestions = []
        
        # Récupérer les préférences utilisateur
        user_prefs = {}
        user_history = None
        if employe_id:
            user_prefs = self.get_user_preferences(employe_id)
            user_history = self.get_user_history(employe_id)
        
        # Récupérer les disponibilités de la salle
        room_patterns = self.get_room_availability_pattern(resource_id)
        
        # Calculer la durée originale
        duration = (date_fin - date_debut)
        duration_hours = duration.seconds // 3600
        
        # Score pour chaque suggestion
        for days_offset in [1, 2, 3, 4, 5, 7, 14]:
            for hour_offset in [-3, -2, -1, 1, 2, 3]:
                # Calculer la date suggérée
                suggested_start = date_debut + timedelta(days=days_offset, hours=hour_offset)
                suggested_end = suggested_start + duration
                
                # Vérifier que c'est dans le futur et dans les 30 jours
                if suggested_start <= datetime.now():
                    continue
                if suggested_start > datetime.now() + timedelta(days=30):
                    continue
                
                # Vérifier les conflits avec les réservations existantes
                conflict = self.db.reservations.find_one({
                    'bureau_id': resource_id,
                    'statut': {'$in': ['confirmee', 'en_attente']},
                    'date_debut': {'$lt': suggested_end},
                    'date_fin': {'$gt': suggested_start}
                })
                
                if conflict:
                    continue
                
                # Calculer le score de la suggestion
                score = self._calculate_suggestion_score(
                    suggested_start, suggested_end,
                    user_prefs, user_history, room_patterns
                )
                
                # Vérifier les heures d'ouverture
                if not self._is_within_business_hours(suggested_start, suggested_end):
                    score -= 30
                
                if score > 30:  # Seuil minimum
                    suggestions.append({
                        'date_debut': suggested_start,
                        'date_fin': suggested_end,
                        'score': score,
                        'reason': self._get_reason(score, user_history),
                        'availability': self._get_availability_label(score)
                    })
        
        # Trier par score et limiter à 5
        suggestions.sort(key=lambda x: x['score'], reverse=True)
        
        # Enrichir les suggestions avec des informations
        enriched = []
        for s in suggestions[:5]:
            enriched.append({
                'date': s['date_debut'].strftime('%d/%m/%Y'),
                'debut': s['date_debut'].strftime('%H:%M'),
                'fin': s['date_fin'].strftime('%H:%M'),
                'score': s['score'],
                'reason': s['reason'],
                'availability': s['availability'],
                'day_name': s['date_debut'].strftime('%A').lower()
            })
        
        return enriched
    
    def _calculate_suggestion_score(self, start, end, user_prefs, user_history, room_patterns):
        """Calcule un score pour une suggestion"""
        score = 50  # Score de base
        
        day_name = start.strftime('%A').lower()
        hour = start.hour
        
        # Préférences utilisateur (historique)
        if user_history:
            if day_name in user_history.get('preferred_days', []):
                score += 20
            if hour in user_history.get('preferred_hours', []):
                score += 15
        
        # Préférences explicites
        if user_prefs:
            if day_name in user_prefs.get('preferred_days', []):
                score += 15
            if hour in user_prefs.get('preferred_hours_start', []):
                score += 10
        
        # Pattern de disponibilité de la salle
        for pattern in room_patterns:
            if pattern['day'] == day_name and pattern['hour'] == hour:
                score += pattern['availability_rate'] / 10
                if pattern['confidence'] == 'high':
                    score += 10
                break
        
        # Pénalité pour les week-ends (sauf si préféré)
        if day_name in ['saturday', 'sunday']:
            if day_name not in user_history.get('preferred_days', []):
                score -= 15
        
        # Bonus pour les heures de bureau standards (9h-12h, 14h-17h)
        if 9 <= hour <= 12 or 14 <= hour <= 17:
            score += 10
        
        # Pénalité pour les heures tardives
        if hour >= 18 or hour <= 7:
            score -= 20
        
        return min(100, max(0, score))
    
    def _is_within_business_hours(self, start, end):
        """Vérifie si le créneau est dans les heures d'ouverture"""
        hour_start = start.hour
        hour_end = end.hour
        
        # Heures d'ouverture par défaut : 8h-18h
        if hour_start < 8 or hour_start > 17:
            return False
        if hour_end > 18:
            return False
        return True
    
    def _get_reason(self, score, user_history):
        """Génère une raison pour la suggestion"""
        if score >= 80:
            return "🎯 Créneau idéal basé sur vos habitudes"
        elif score >= 60:
            return "📊 Bon créneau, recommandé par l'analyse"
        elif score >= 40:
            return "🕐 Créneau alternatif disponible"
        else:
            return "⚡ Dernière option disponible"
    
    def _get_availability_label(self, score):
        """Label de disponibilité"""
        if score >= 80:
            return "Très disponible"
        elif score >= 60:
            return "Disponible"
        elif score >= 40:
            return "Peu fréquenté"
        else:
            return "Libre"

# Instance globale
suggestion_engine = None

def get_suggestion_engine(db):
    global suggestion_engine
    if suggestion_engine is None:
        suggestion_engine = SmartSuggestionEngine(db)
    return suggestion_engine