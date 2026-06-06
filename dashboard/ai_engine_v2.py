"""
SIGR-CA — Moteur IA v2  (remplace ai_engine.py)
================================================
4 modèles réellement utiles dans un système de gestion
de ressources + contrôle d'accès :

 1. AccessBehaviorProfiler  — Profil comportemental par employé (KMeans)
    Source : acces_logs  ← données RÉELLES du contrôle d'accès
    → Détecte accès hors-profil : mauvaise heure, zone inconnue, refus en série

 2. NoShowPredictor          — Prédiction d'abandon de réservation (RandomForest)
    Source : reservations + acces_logs (jointure)
    → Libération proactive des ressources non utilisées

 3. SecurityRiskScorer       — Score de risque par événement d'accès (hybride)
    Source : acces_logs en temps réel
    → Clonage de badge, accès hors-horaires, zones inhabituelles → alertes

 4. ResourceUtilizationAnalyzer — Réel vs planifié (stats + KMeans)
    Source : reservations + acces_logs
    → Ressources fantômes, taux d'utilisation effectif, sous-utilisation
"""

import os
import logging
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
from bson import ObjectId
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import joblib

from django.conf import settings

logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(settings.BASE_DIR, 'ai_models')
os.makedirs(MODELS_DIR, exist_ok=True)


def _db():
    from django.conf import settings as s
    return s.MONGO_DB


# ══════════════════════════════════════════════════════════════════════════════
# 1. ACCESS BEHAVIOR PROFILER
#    KMeans sur l'historique d'accès de chaque employé.
#    → Construit un "profil normal" et détecte les déviations.
# ══════════════════════════════════════════════════════════════════════════════
class AccessBehaviorProfiler:
    """
    Utilise KMeans pour créer des profils comportementaux par employé.
    Detecte les accès hors-profil (mauvaise heure, zone inhabituielle,
    trop de refus) et génère un score de déviation 0-100.
    """
    MODEL_PATH = os.path.join(MODELS_DIR, 'behavior_model.pkl')

    def __init__(self):
        self.model = None
        self.scaler = None
        self.employee_profiles = {}

    def _load_access_dataframe(self, days=90):
        db = _db()
        cutoff = datetime.now() - timedelta(days=days)
        cursor = db.acces_logs.find({'timestamp': {'$gte': cutoff}})
        rows = []
        for doc in cursor:
            ts = doc.get('timestamp')
            if not ts:
                continue
            emp_id = str(doc.get('utilisateur_id') or doc.get('employe_id') or '')
            rows.append({
                'employe_id':   emp_id,
                'heure':        ts.hour,
                'jour_semaine': ts.weekday(),
                'resultat_ok':  1 if doc.get('resultat', '') == 'AUTORISE' else 0,
                'bureau_id':    str(doc.get('bureau_id', '')),
                'timestamp':    ts,
            })
        return pd.DataFrame(rows)

    def train(self):
        df = self._load_access_dataframe()
        if len(df) < 10:
            logger.warning("AccessBehaviorProfiler: pas assez de données (%d logs)", len(df))
            return False

        # Profil global : (heure, jour, taux_ok) par employé
        grp = df.groupby('employe_id').agg(
            heure_moy   = ('heure',       'mean'),
            heure_std   = ('heure',       'std'),
            jour_moy    = ('jour_semaine','mean'),
            taux_ok     = ('resultat_ok', 'mean'),
            nb_acces    = ('resultat_ok', 'count'),
        ).fillna(0).reset_index()

        X = grp[['heure_moy', 'heure_std', 'jour_moy', 'taux_ok', 'nb_acces']].values
        self.scaler = StandardScaler()
        Xs = self.scaler.fit_transform(X)

        n_clusters = min(5, len(grp))
        self.model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        self.model.fit(Xs)

        grp['cluster'] = self.model.labels_
        self.employee_profiles = grp.set_index('employe_id').to_dict('index')

        # Calcul des zones habituelles par employé
        self.usual_zones = {}
        for eid, g in df.groupby('employe_id'):
            top_zones = g['bureau_id'].value_counts().head(5).index.tolist()
            self.usual_zones[eid] = set(top_zones)

        joblib.dump({
            'model':    self.model,
            'scaler':   self.scaler,
            'profiles': self.employee_profiles,
            'zones':    self.usual_zones,
        }, self.MODEL_PATH)
        logger.info("AccessBehaviorProfiler entraîné sur %d employés.", len(grp))
        return True

    def load(self):
        if not os.path.exists(self.MODEL_PATH):
            return False
        data = joblib.load(self.MODEL_PATH)
        self.model = data['model']
        self.scaler = data['scaler']
        self.employee_profiles = data['profiles']
        self.usual_zones = data.get('zones', {})
        return True

    def score_access(self, employe_id: str, heure: int, jour: int,
                     bureau_id: str, resultat: str) -> dict:
        """
        Retourne un score de risque 0-100 pour un événement d'accès.
        """
        if self.model is None and not self.load():
            return {'score': 0, 'niveau': 'inconnu', 'raisons': []}

        score = 0
        raisons = []
        profile = self.employee_profiles.get(employe_id)

        if profile:
            # Écart à l'heure habituelle
            ecart_heure = abs(heure - profile['heure_moy'])
            if ecart_heure > 4:
                score += 30
                raisons.append(f"Accès à {heure}h (habituel : {profile['heure_moy']:.0f}h)")

            # Taux de refus inhabituellement élevé
            if profile['taux_ok'] < 0.7 and resultat == 'REFUSE':
                score += 25
                raisons.append("Taux de refus élevé pour cet employé")

        else:
            # Employé inconnu du profil → risque moyen par défaut
            score += 20
            raisons.append("Employé sans historique d'accès")

        # Zone inhabituelle
        usual = self.usual_zones.get(employe_id, set())
        if bureau_id and usual and bureau_id not in usual:
            score += 25
            raisons.append("Zone d'accès inhabituelle")

        # Accès hors heures bureau (avant 7h ou après 20h)
        if heure < 7 or heure > 20:
            score += 20
            raisons.append(f"Heure hors-bureau ({heure}h)")

        # Refus direct
        if resultat == 'REFUSE':
            score += 10
            raisons.append("Accès refusé")

        score = min(100, score)
        if score >= 70:
            niveau = 'critique'
        elif score >= 45:
            niveau = 'élevé'
        elif score >= 20:
            niveau = 'moyen'
        else:
            niveau = 'faible'

        return {'score': score, 'niveau': niveau, 'raisons': raisons}

    def get_suspicious_recent(self, hours=24):
        """Retourne les N accès les plus suspects des dernières N heures."""
        db = _db()
        cutoff = datetime.now() - timedelta(hours=hours)
        logs = list(db.acces_logs.find({'timestamp': {'$gte': cutoff}}).sort('timestamp', -1).limit(200))
        results = []
        for log in logs:
            ts = log.get('timestamp')
            if not ts:
                continue
            eid = str(log.get('utilisateur_id') or log.get('employe_id') or '')
            bid = str(log.get('bureau_id', ''))
            r = log.get('resultat', 'INCONNU')
            scored = self.score_access(eid, ts.hour, ts.weekday(), bid, r)
            if scored['score'] >= 30:
                emp = db.employees.find_one({'_id': ObjectId(eid)}) if eid else None
                results.append({
                    'score':        scored['score'],
                    'niveau':       scored['niveau'],
                    'raisons':      scored['raisons'],
                    'employe':      f"{emp.get('prenom','')} {emp.get('nom','')}".strip() if emp else eid[:8],
                    'employe_id':   eid,
                    'heure':        ts.strftime('%H:%M'),
                    'date':         ts.strftime('%d/%m/%Y'),
                    'bureau_id':    bid,
                    'resultat':     r,
                })
        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:15]

    def get_employee_risk_stats(self):
        """Statistiques de risque agrégées par employé (pour le tableau de bord)."""
        if self.model is None and not self.load():
            return []
        db = _db()
        stats = []
        for eid, profile in list(self.employee_profiles.items())[:20]:
            taux_ok = profile.get('taux_ok', 1.0)
            nb = profile.get('nb_acces', 0)
            risk_base = round((1 - taux_ok) * 100)
            emp = db.employees.find_one({'django_user_id': eid}) \
                  or db.employees.find_one({'_id': ObjectId(eid)}) if eid else None
            stats.append({
                'employe_id':    eid,
                'nom':           f"{emp.get('prenom','')} {emp.get('nom','')}".strip() if emp else eid[:8],
                'nb_acces':      int(nb),
                'taux_ok':       round(taux_ok * 100, 1),
                'risque':        risk_base,
                'heure_habituelle': f"{profile.get('heure_moy', 0):.0f}h",
            })
        stats.sort(key=lambda x: x['risque'], reverse=True)
        return stats


# ══════════════════════════════════════════════════════════════════════════════
# 2. NO-SHOW PREDICTOR
#    RandomForestClassifier sur réservations + présence réelle.
#    → Libération proactive des salles non utilisées.
# ══════════════════════════════════════════════════════════════════════════════
class NoShowPredictor:
    """
    Prédit si une réservation confirmée sera honorée ou abandonnée.
    Entraîné sur : historique des réservations + logs d'accès réels.
    """
    MODEL_PATH = os.path.join(MODELS_DIR, 'noshow_model.pkl')
    WINDOW_MINUTES = 20  # accès dans les 20 min après début = réservation honorée

    def __init__(self):
        self.pipeline = None

    def _build_dataset(self, days=180):
        db = _db()
        cutoff = datetime.now() - timedelta(days=days)
        resas = list(db.reservations.find({
            'date_debut': {'$gte': cutoff},
            'statut': {'$in': ['confirmee', 'terminee', 'annulee']},
        }))
        rows = []
        for r in resas:
            dd = r.get('date_debut')
            if not dd:
                continue
            eid = str(r.get('employe_id', ''))
            bid = r.get('bureau_id')

            # Recherche d'un accès réel dans les WINDOW_MINUTES suivant le début
            window_end = dd + timedelta(minutes=self.WINDOW_MINUTES)
            query = {
                'timestamp':   {'$gte': dd - timedelta(minutes=5), '$lte': window_end},
                'resultat':    'AUTORISE',
            }
            if bid:
                query['bureau_id'] = bid
            # Recherche par employé_id dans acces_logs
            if eid:
                query['$or'] = [
                    {'utilisateur_id': eid},
                    {'employe_id':     eid},
                ]
            honore = 1 if db.acces_logs.find_one(query) else 0

            # Taux no-show historique de cet employé
            emp_resas = db.reservations.count_documents({'employe_id': eid, 'date_debut': {'$lt': dd}})
            emp_noshow = max(0, emp_resas - db.acces_logs.count_documents({'utilisateur_id': eid}))
            taux_noshow_emp = emp_noshow / emp_resas if emp_resas > 0 else 0.3

            # Délai entre création et début
            created = r.get('created_at') or r.get('date_debut')
            delai_h = (dd - created).total_seconds() / 3600 if created else 0

            rows.append({
                'jour_semaine':   dd.weekday(),
                'heure':          dd.hour,
                'duree_min':      ((r.get('date_fin') or dd) - dd).total_seconds() / 60,
                'nb_participants': r.get('nb_participants', 1),
                'delai_h':        max(0, delai_h),
                'taux_noshow_emp':taux_noshow_emp,
                'statut_annule':  1 if r.get('statut') == 'annulee' else 0,
                'honore':         honore,
            })
        return pd.DataFrame(rows)

    def train(self):
        df = self._build_dataset()
        if len(df) < 10:
            logger.warning("NoShowPredictor: pas assez de données (%d resas).", len(df))
            return False

        features = ['jour_semaine','heure','duree_min','nb_participants',
                    'delai_h','taux_noshow_emp']
        X = df[features].values
        y = df['honore'].values

        self.pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('clf', RandomForestClassifier(
                n_estimators=100, max_depth=8,
                class_weight='balanced', random_state=42
            )),
        ])
        self.pipeline.fit(X, y)
        score = self.pipeline.score(X, y)
        logger.info("NoShowPredictor entraîné. Accuracy=%.2f sur %d resas.", score, len(df))

        joblib.dump(self.pipeline, self.MODEL_PATH)
        return True

    def load(self):
        if not os.path.exists(self.MODEL_PATH):
            return False
        self.pipeline = joblib.load(self.MODEL_PATH)
        return True

    def predict_proba(self, jour: int, heure: int, duree_min: float,
                      nb_participants: int, delai_h: float,
                      taux_noshow_emp: float = 0.3) -> dict:
        """Retourne la probabilité que la réservation soit honorée."""
        if self.pipeline is None and not self.load():
            return {'prob_honore': None, 'prob_noshow': None, 'alerte': False}
        X = np.array([[jour, heure, duree_min, nb_participants, delai_h, taux_noshow_emp]])
        proba = self.pipeline.predict_proba(X)[0]
        classes = self.pipeline.classes_
        idx_honore = list(classes).index(1) if 1 in classes else -1
        prob_honore = float(proba[idx_honore]) if idx_honore >= 0 else 0.5
        return {
            'prob_honore': round(prob_honore * 100, 1),
            'prob_noshow': round((1 - prob_honore) * 100, 1),
            'alerte':      prob_honore < 0.4,
        }

    def get_at_risk_reservations(self, hours_ahead=4):
        """
        Retourne les réservations des N prochaines heures à risque d'abandon.
        """
        if self.pipeline is None and not self.load():
            return []
        db = _db()
        now = datetime.now()
        horizon = now + timedelta(hours=hours_ahead)
        resas = list(db.reservations.find({
            'date_debut': {'$gte': now, '$lte': horizon},
            'statut':     'en_attente',
        }).sort('date_debut', 1))
        results = []
        for r in resas:
            dd = r.get('date_debut')
            if not dd:
                continue
            eid = str(r.get('employe_id', ''))
            emp_resas = db.reservations.count_documents({'employe_id': eid, 'date_debut': {'$lt': dd}})
            emp_log   = db.acces_logs.count_documents({'utilisateur_id': eid})
            taux_ns   = max(0, (emp_resas - emp_log)) / emp_resas if emp_resas > 0 else 0.3
            created   = r.get('created_at') or dd
            delai_h   = (dd - created).total_seconds() / 3600

            pred = self.predict_proba(
                jour=dd.weekday(), heure=dd.hour,
                duree_min=((r.get('date_fin') or dd) - dd).total_seconds() / 60,
                nb_participants=r.get('nb_participants', 1),
                delai_h=max(0, delai_h),
                taux_noshow_emp=taux_ns,
            )
            if pred['alerte']:
                bureau = db.bureaux.find_one({'_id': r.get('bureau_id')})
                results.append({
                    'reservation_id': str(r['_id']),
                    'titre':          r.get('titre', 'Sans titre'),
                    'employe_nom':    r.get('employe_nom', eid[:8]),
                    'bureau_nom':     bureau['nom'] if bureau else 'Salle inconnue',
                    'date_debut':     dd.strftime('%d/%m %H:%M'),
                    'prob_noshow':    pred['prob_noshow'],
                    'prob_honore':    pred['prob_honore'],
                })
        return results


# ══════════════════════════════════════════════════════════════════════════════
# 3. SECURITY RISK SCORER (détection en temps réel)
#    Pas besoin d'entraînement — règles expertes + stats.
#    → Clonage badge, multiples refus, accès simultanés anormaux.
# ══════════════════════════════════════════════════════════════════════════════
class SecurityRiskScorer:
    """
    Score de risque hybride (règles + statistiques) pour chaque événement.
    Ne nécessite pas d'entraînement ML — directement opérationnel.
    """

    BUSINESS_START = 7
    BUSINESS_END   = 20
    CLONE_WINDOW_SEC = 300  # 5 minutes : même badge, 2 zones → clonage probable

    def analyse_recent_security(self, hours=24):
        """
        Analyse les accès des dernières N heures et retourne :
        - Les événements critiques (clonage, série de refus, hors-horaires)
        - Un bilan de sécurité global
        """
        db = _db()
        cutoff = datetime.now() - timedelta(hours=hours)
        logs = list(db.acces_logs.find({'timestamp': {'$gte': cutoff}}).sort('timestamp', 1))

        events = []
        alerts = []

        # Index par employé pour détecter les patterns
        by_emp = defaultdict(list)
        for log in logs:
            eid = str(log.get('utilisateur_id') or log.get('employe_id') or '')
            if eid:
                by_emp[eid].append(log)

        for eid, emp_logs in by_emp.items():
            emp = db.employees.find_one({'_id': ObjectId(eid)}) if eid else None
            nom = f"{emp.get('prenom','')} {emp.get('nom','')}".strip() if emp else eid[:8]

            # --- 1. Détection clonage badge ---
            # Même employé dans 2 zones différentes en < CLONE_WINDOW_SEC
            for i in range(len(emp_logs) - 1):
                a, b = emp_logs[i], emp_logs[i+1]
                ta, tb = a.get('timestamp'), b.get('timestamp')
                ba, bb = str(a.get('bureau_id','')), str(b.get('bureau_id',''))
                if ta and tb and ba and bb and ba != bb:
                    delta = (tb - ta).total_seconds()
                    if 0 < delta < self.CLONE_WINDOW_SEC:
                        alerts.append({
                            'type':       'CLONAGE_BADGE',
                            'severite':   'CRITIQUE',
                            'employe':    nom,
                            'employe_id': eid,
                            'detail':     f"Badge utilisé dans 2 zones différentes en {int(delta)}s",
                            'timestamp':  tb.strftime('%d/%m %H:%M:%S'),
                        })

            # --- 2. Série de refus (3+ consécutifs) ---
            consec_refus = 0
            for log in emp_logs:
                if log.get('resultat') == 'REFUSE':
                    consec_refus += 1
                    if consec_refus >= 3:
                        alerts.append({
                            'type':       'MULTIPLES_REFUS',
                            'severite':   'ELEVE',
                            'employe':    nom,
                            'employe_id': eid,
                            'detail':     f"{consec_refus} refus consécutifs",
                            'timestamp':  log.get('timestamp', datetime.now()).strftime('%d/%m %H:%M'),
                        })
                        consec_refus = 0
                else:
                    consec_refus = 0

            # --- 3. Accès hors heures bureau ---
            for log in emp_logs:
                ts = log.get('timestamp')
                if ts and (ts.hour < self.BUSINESS_START or ts.hour >= self.BUSINESS_END):
                    if log.get('resultat') == 'AUTORISE':
                        alerts.append({
                            'type':       'ACCES_HORS_HORAIRES',
                            'severite':   'MOYEN',
                            'employe':    nom,
                            'employe_id': eid,
                            'detail':     f"Accès autorisé à {ts.strftime('%H:%M')} (hors heures)",
                            'timestamp':  ts.strftime('%d/%m %H:%M'),
                        })

        # Dédupliquer les alertes (garder au max 2 par type/employé)
        seen = defaultdict(int)
        deduped = []
        for a in alerts:
            k = (a['type'], a['employe_id'])
            if seen[k] < 2:
                deduped.append(a)
                seen[k] += 1

        # Tri par sévérité
        ordre = {'CRITIQUE': 0, 'ELEVE': 1, 'MOYEN': 2}
        deduped.sort(key=lambda x: ordre.get(x['severite'], 3))

        # Résumé global
        total = len(logs)
        refuses = sum(1 for l in logs if l.get('resultat') == 'REFUSE')
        bilan = {
            'total_acces':      total,
            'refuses':          refuses,
            'taux_refus':       round(refuses / total * 100, 1) if total else 0,
            'nb_alertes':       len(deduped),
            'alertes_critiques': sum(1 for a in deduped if a['severite'] == 'CRITIQUE'),
            'employes_actifs':  len(by_emp),
        }

        return {'alertes': deduped[:20], 'bilan': bilan}


# ══════════════════════════════════════════════════════════════════════════════
# 4. RESOURCE UTILIZATION ANALYZER
#    Compare réservations planifiées vs accès réels.
#    → Ressources fantômes, sous-utilisation, gaspillage.
# ══════════════════════════════════════════════════════════════════════════════
class ResourceUtilizationAnalyzer:
    """
    Analyse le taux d'utilisation RÉEL des ressources (salles/matériels).
    Croise les réservations confirmées avec les logs d'accès effectifs.
    Identifie les ressources sur-réservées et jamais utilisées.
    """

    def analyse(self, days=30):
        db = _db()
        cutoff = datetime.now() - timedelta(days=days)

        resas = list(db.reservations.find({
            'date_debut': {'$gte': cutoff},
            'statut': {'$in': ['confirmee', 'terminee']},
        }))

        stats = defaultdict(lambda: {
            'nb_reservations':   0,
            'nb_avec_acces':     0,
            'duree_reservee_h':  0.0,
            'bureau_nom':        'Inconnu',
        })

        for r in resas:
            bid = r.get('bureau_id')
            if not bid:
                continue
            bid_s = str(bid)
            dd = r.get('date_debut')
            df_r = r.get('date_fin')
            if not dd:
                continue

            stats[bid_s]['nb_reservations'] += 1
            if dd and df_r:
                stats[bid_s]['duree_reservee_h'] += (df_r - dd).total_seconds() / 3600

            # Accès réel dans les 30 min suivant le début
            window_end = dd + timedelta(minutes=30)
            acces_reel = db.acces_logs.find_one({
                'bureau_id': bid,
                'timestamp': {'$gte': dd, '$lte': window_end},
                'resultat':  'AUTORISE',
            })
            if acces_reel:
                stats[bid_s]['nb_avec_acces'] += 1

            # Nom du bureau
            if stats[bid_s]['bureau_nom'] == 'Inconnu':
                bureau = db.bureaux.find_one({'_id': bid})
                if bureau:
                    stats[bid_s]['bureau_nom'] = bureau.get('nom', 'Salle ?')

        results = []
        for bid_s, s in stats.items():
            nb_r = s['nb_reservations']
            nb_a = s['nb_avec_acces']
            taux = round(nb_a / nb_r * 100, 1) if nb_r > 0 else 0.0
            results.append({
                'bureau_id':          bid_s,
                'bureau_nom':         s['bureau_nom'],
                'nb_reservations':    nb_r,
                'nb_avec_acces':      nb_a,
                'nb_fantomes':        nb_r - nb_a,
                'taux_utilisation':   taux,
                'duree_reservee_h':   round(s['duree_reservee_h'], 1),
                'statut':             'critique' if taux < 30 else ('attention' if taux < 60 else 'ok'),
            })

        results.sort(key=lambda x: x['taux_utilisation'])

        # Résumé global
        total_resas  = sum(r['nb_reservations'] for r in results)
        total_honore = sum(r['nb_avec_acces']   for r in results)
        taux_global  = round(total_honore / total_resas * 100, 1) if total_resas else 0

        return {
            'ressources': results,
            'resume': {
                'nb_ressources':    len(results),
                'total_reservations': total_resas,
                'total_honorees':   total_honore,
                'total_fantomes':   total_resas - total_honore,
                'taux_global':      taux_global,
                'periode_jours':    days,
            }
        }


# ══════════════════════════════════════════════════════════════════════════════
# API PUBLIQUE
# ══════════════════════════════════════════════════════════════════════════════

def train_all_models():
    """Entraîne les modèles ML (AccessBehaviorProfiler + NoShowPredictor)."""
    results = {}
    try:
        results['behavior']  = AccessBehaviorProfiler().train()
    except Exception:
        logger.exception("Erreur entraînement behavior")
        results['behavior'] = False
    try:
        results['noshow'] = NoShowPredictor().train()
    except Exception:
        logger.exception("Erreur entraînement noshow")
        results['noshow'] = False
    # SecurityRiskScorer et ResourceUtilizationAnalyzer n'ont pas besoin d'entraînement
    results['security']     = True
    results['utilization']  = True
    return results


def get_models_status():
    return {
        'behavior':    os.path.exists(os.path.join(MODELS_DIR, 'behavior_model.pkl')),
        'noshow':      os.path.exists(os.path.join(MODELS_DIR, 'noshow_model.pkl')),
        'security':    True,
        'utilization': True,
    }


# Singletons (évite de re-charger le modèle à chaque requête)
_behavior_profiler  = None
_noshow_predictor   = None
_security_scorer    = SecurityRiskScorer()
_utilization_analyzer = ResourceUtilizationAnalyzer()


def get_behavior_profiler():
    global _behavior_profiler
    if _behavior_profiler is None:
        _behavior_profiler = AccessBehaviorProfiler()
        _behavior_profiler.load()
    return _behavior_profiler


def get_noshow_predictor():
    global _noshow_predictor
    if _noshow_predictor is None:
        _noshow_predictor = NoShowPredictor()
        _noshow_predictor.load()
    return _noshow_predictor


def get_security_scorer():
    return _security_scorer


def get_utilization_analyzer():
    return _utilization_analyzer
