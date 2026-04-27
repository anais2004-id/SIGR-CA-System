"""
Moteur IA SIGR-CA — Modèles ML réels entraînés sur les données MongoDB.
"""
import os
import logging
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
from bson import ObjectId
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler
import joblib

from django.conf import settings

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(settings.BASE_DIR, 'ai_models')
os.makedirs(MODELS_DIR, exist_ok=True)

def _get_db():
    """Import paresseux de db pour éviter l'import circulaire avec views.py"""
    from dashboard.views import db
    return db
# ============================================================
# 1. EXTRACTION DES DONNÉES MONGODB → DATAFRAME PANDAS
# ============================================================

def load_reservations_dataframe(days_back=180):
    """Charge les réservations des N derniers jours en DataFrame."""
    db = _get_db()
    cutoff = datetime.now() - timedelta(days=days_back)
    cutoff = datetime.now() - timedelta(days=days_back)
    cursor = db.reservations.find({
        'date_debut': {'$gte': cutoff},
        'statut': {'$in': ['confirmee', 'terminee']},
    })

    rows = []
    for r in cursor:
        if not r.get('date_debut') or not r.get('date_fin'):
            continue
        rows.append({
            'reservation_id': str(r['_id']),
            'employe_id':     str(r.get('employe_id', '')),
            'resource_id':    str(r.get('bureau_id') or r.get('materiel_id') or r.get('resource_id') or ''),
            'resource_type':  r.get('resource_type', 'salle'),
            'date_debut':     r['date_debut'],
            'date_fin':       r['date_fin'],
            'duree_min':      (r['date_fin'] - r['date_debut']).total_seconds() / 60,
            'nb_participants': r.get('nb_participants', 1),
            'jour_semaine':   r['date_debut'].weekday(),  # 0=lundi
            'heure':          r['date_debut'].hour,
            'mois':           r['date_debut'].month,
        })
    return pd.DataFrame(rows)


# ============================================================
# 2. PRÉDICTEUR D'OCCUPATION (Random Forest)
# ============================================================

class OccupationPredictor:
    """
    Prédit le taux d'occupation d'une salle (%) pour un créneau futur.
    Features : jour_semaine, heure, mois, capacite, type_ressource_encoded
    """
    MODEL_PATH = os.path.join(MODELS_DIR, 'occupation_model.pkl')

    def __init__(self):
        self.model = None
        self.scaler = None

    def train(self):
        df = load_reservations_dataframe(days_back=180)
        if len(df) < 5:
            logger.warning(f"Pas assez de données pour entraîner ({len(df)} réservations). Minimum: 30.")
            return False

        # Agrégation par (resource_id, jour, heure) → nb réservations
        df['date_jour'] = df['date_debut'].dt.date
        agg = df.groupby(['resource_id', 'date_jour', 'heure', 'jour_semaine', 'mois']) \
                .agg(nb_reservations=('reservation_id', 'count'),
                     duree_totale=('duree_min', 'sum')) \
                .reset_index()

        # Taux d'occupation = duree_totale / 60min (1h = 100%)
        agg['taux_occupation'] = (agg['duree_totale'] / 60 * 100).clip(0, 100)

        X = agg[['jour_semaine', 'heure', 'mois', 'nb_reservations']].values
        y = agg['taux_occupation'].values

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = RandomForestRegressor(
            n_estimators=100, max_depth=10, random_state=42, n_jobs=-1
        )
        self.model.fit(X_scaled, y)

        # Score sur les données d'entraînement
        score = self.model.score(X_scaled, y)
        logger.info(f"Modèle occupation entraîné. R²={score:.3f} sur {len(agg)} échantillons.")

        joblib.dump({'model': self.model, 'scaler': self.scaler}, self.MODEL_PATH)
        return True

    def load(self):
        if not os.path.exists(self.MODEL_PATH):
            return False
        data = joblib.load(self.MODEL_PATH)
        self.model = data['model']
        self.scaler = data['scaler']
        return True

    def predict(self, jour_semaine, heure, mois, nb_reservations_prev=1):
        """Retourne taux d'occupation prédit (0-100%)."""
        if self.model is None and not self.load():
            return None
        X = np.array([[jour_semaine, heure, mois, nb_reservations_prev]])
        X_scaled = self.scaler.transform(X)
        pred = float(self.model.predict(X_scaled)[0])
        return round(max(0, min(100, pred)), 1)

    def predict_week(self, resource_id):
        """Retourne une heatmap 7j × 24h des taux prédits."""
        if self.model is None and not self.load():
            return None
        db = _get_db()
        # Compter réservations historiques de cette ressource
        count = db.reservations.count_documents({
            '$or': [
                {'bureau_id': ObjectId(resource_id)},
                {'materiel_id': ObjectId(resource_id)},
            ]
        }) or 1

        now = datetime.now()
        heatmap = []
        for day_offset in range(7):
            d = now + timedelta(days=day_offset)
            row = {'jour': d.strftime('%A'), 'date': d.strftime('%d/%m'), 'heures': []}
            for h in range(8, 20):
                taux = self.predict(d.weekday(), h, d.month, count)
                row['heures'].append({'h': h, 'taux': taux})
            heatmap.append(row)
        return heatmap


# ============================================================
# 3. RECOMMANDATIONS PERSONNALISÉES (Collaborative Filtering)
# ============================================================

class PersonalRecommender:
    """
    Construit une matrice user × resource pour recommander des ressources
    similaires à celles que l'utilisateur a déjà réservées.
    """
    MODEL_PATH = os.path.join(MODELS_DIR, 'reco_model.pkl')

    def __init__(self):
        self.user_resource_matrix = None
        self.resource_ids = []
        self.user_ids = []
        self.similarity_matrix = None

    def train(self):
        df = load_reservations_dataframe(days_back=365)
        if len(df) < 10:
            logger.warning("Pas assez de réservations pour les recommandations.")
            return False

        # Matrice user × resource (nombre de réservations)
        matrix = df.pivot_table(
            index='employe_id', columns='resource_id',
            values='reservation_id', aggfunc='count', fill_value=0
        )

        self.user_ids = matrix.index.tolist()
        self.resource_ids = matrix.columns.tolist()
        self.user_resource_matrix = matrix.values

        # Similarité entre ressources (cosine)
        self.similarity_matrix = cosine_similarity(self.user_resource_matrix.T)

        joblib.dump({
            'matrix': self.user_resource_matrix,
            'user_ids': self.user_ids,
            'resource_ids': self.resource_ids,
            'similarity': self.similarity_matrix,
        }, self.MODEL_PATH)

        logger.info(f"Modèle reco entraîné. {len(self.user_ids)} users × {len(self.resource_ids)} ressources.")
        return True

    def load(self):
        if not os.path.exists(self.MODEL_PATH):
            return False
        data = joblib.load(self.MODEL_PATH)
        self.user_resource_matrix = data['matrix']
        self.user_ids = data['user_ids']
        self.resource_ids = data['resource_ids']
        self.similarity_matrix = data['similarity']
        return True

    def recommend(self, employe_id, top_n=3):
        """Retourne les top N resource_ids recommandés pour cet employé."""
        if self.user_resource_matrix is None and not self.load():
            return []

        if employe_id not in self.user_ids:
            # Nouvel utilisateur → top ressources globales
            scores = self.user_resource_matrix.sum(axis=0)
            top_idx = np.argsort(scores)[::-1][:top_n]
            return [{'resource_id': self.resource_ids[i],
                     'score': float(scores[i]),
                     'raison': 'Populaire dans l\'entreprise'} for i in top_idx]

        user_idx = self.user_ids.index(employe_id)
        user_vec = self.user_resource_matrix[user_idx]

        # Score = somme pondérée des similarités avec les ressources déjà utilisées
        scores = self.similarity_matrix.dot(user_vec)
        # On exclut ce que l'utilisateur a déjà réservé
        scores[user_vec > 0] = -1

        top_idx = np.argsort(scores)[::-1][:top_n]
        return [{'resource_id': self.resource_ids[i],
                 'score': round(float(scores[i]), 2),
                 'raison': 'Basé sur vos réservations passées'}
                for i in top_idx if scores[i] > 0]


# ============================================================
# 4. DÉTECTEUR D'ANOMALIES (Isolation Forest)
# ============================================================

class AnomalyDetector:
    """Détecte les réservations atypiques (durée, horaire, fréquence)."""
    MODEL_PATH = os.path.join(MODELS_DIR, 'anomaly_model.pkl')

    def __init__(self):
        self.model = None
        self.scaler = None

    def train(self):
        df = load_reservations_dataframe(days_back=180)
        if len(df) < 10:
            logger.warning("Pas assez de données pour détection d'anomalies.")
            return False

        X = df[['duree_min', 'nb_participants', 'heure', 'jour_semaine']].values

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = IsolationForest(contamination=0.05, random_state=42, n_jobs=-1)
        self.model.fit(X_scaled)

        joblib.dump({'model': self.model, 'scaler': self.scaler}, self.MODEL_PATH)
        logger.info(f"Modèle anomalies entraîné sur {len(df)} réservations.")
        return True

    def load(self):
        if not os.path.exists(self.MODEL_PATH):
            return False
        data = joblib.load(self.MODEL_PATH)
        self.model = data['model']
        self.scaler = data['scaler']
        return True

    def detect_recent(self, days=7):
        """Retourne les réservations anormales des N derniers jours."""
        if self.model is None and not self.load():
            return []

        df = load_reservations_dataframe(days_back=days)
        if df.empty:
            return []

        X = df[['duree_min', 'nb_participants', 'heure', 'jour_semaine']].values
        X_scaled = self.scaler.transform(X)

        predictions = self.model.predict(X_scaled)  # -1 = anomalie
        scores = self.model.score_samples(X_scaled)

        df['is_anomaly'] = predictions == -1
        df['anomaly_score'] = scores

        anomalies = df[df['is_anomaly']].sort_values('anomaly_score').head(10)
        return anomalies.to_dict('records')


# ============================================================
# 5. FONCTION MAÎTRE : ENTRAÎNER TOUS LES MODÈLES
# ============================================================

def train_all_models():
    """Entraîne les 3 modèles. À appeler manuellement ou via cron."""
    results = {}
    try:
        results['occupation'] = OccupationPredictor().train()
    except Exception as e:
        logger.exception("Erreur entraînement occupation")
        results['occupation'] = False

    try:
        results['recommender'] = PersonalRecommender().train()
    except Exception as e:
        logger.exception("Erreur entraînement reco")
        results['recommender'] = False

    try:
        results['anomaly'] = AnomalyDetector().train()
    except Exception as e:
        logger.exception("Erreur entraînement anomalies")
        results['anomaly'] = False

    return results