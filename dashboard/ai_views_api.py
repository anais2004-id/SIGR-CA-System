# dashboard/ai_views_api.py
# ─────────────────────────────────────────────────────────────────────────────
# Ajoutez ces routes dans dashboard/urls.py :
#
#   from dashboard import ai_views_api as ai
#   urlpatterns += [
#       path('api/ia/train/',          ai.ia_train,          name='ia_train'),
#       path('api/ia/security/',       ai.ia_security,       name='ia_security'),
#       path('api/ia/noshow/',         ai.ia_noshow,         name='ia_noshow'),
#       path('api/ia/utilisation/',    ai.ia_utilisation,    name='ia_utilisation'),
#       path('api/ia/comportement/',   ai.ia_comportement,   name='ia_comportement'),
#       path('api/ia/status/',         ai.ia_status,         name='ia_status'),
#   ]
# ─────────────────────────────────────────────────────────────────────────────
import json
import logging
from datetime import datetime

from django.http  import JsonResponse
from django.views.decorators.http  import require_http_methods
from django.views.decorators.csrf  import csrf_exempt

logger = logging.getLogger(__name__)


def _session_ok(request):
    return bool(request.session.get('user_id'))

def _staff_ok(request):
    return _session_ok(request) and request.session.get('is_staff', False)


# ─── 1. Entraîner les modèles ────────────────────────────────────────────────
@csrf_exempt
@require_http_methods(["POST"])
def ia_train(request):
    if not _staff_ok(request):
        return JsonResponse({'error': 'Non autorisé.'}, status=403)
    try:
        from dashboard.ai_engine_v2 import train_all_models
        results = train_all_models()
        return JsonResponse({'ok': True, 'results': results})
    except Exception as e:
        logger.exception("ia_train error")
        return JsonResponse({'error': str(e)}, status=500)


# ─── 2. Statut des modèles ───────────────────────────────────────────────────
def ia_status(request):
    if not _staff_ok(request):
        return JsonResponse({'error': 'Non autorisé.'}, status=403)
    try:
        from dashboard.ai_engine_v2 import get_models_status
        return JsonResponse({'status': get_models_status()})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ─── 3. Sécurité : alertes temps réel ───────────────────────────────────────
def ia_security(request):
    if not _staff_ok(request):
        return JsonResponse({'error': 'Non autorisé.'}, status=403)
    try:
        hours = int(request.GET.get('hours', 24))
        hours = min(hours, 168)  # max 1 semaine

        from dashboard.ai_engine_v2 import get_security_scorer, get_behavior_profiler
        security = get_security_scorer().analyse_recent_security(hours=hours)
        suspicious = get_behavior_profiler().get_suspicious_recent(hours=hours)

        return JsonResponse({
            'alertes':    security['alertes'],
            'bilan':      security['bilan'],
            'suspects':   suspicious,
        })
    except Exception as e:
        logger.exception("ia_security error")
        return JsonResponse({'error': str(e)}, status=500)


# ─── 4. No-show : réservations à risque ─────────────────────────────────────
def ia_noshow(request):
    if not _staff_ok(request):
        return JsonResponse({'error': 'Non autorisé.'}, status=403)
    try:
        hours = int(request.GET.get('hours', 4))
        hours = min(hours, 48)

        from dashboard.ai_engine_v2 import get_noshow_predictor
        at_risk = get_noshow_predictor().get_at_risk_reservations(hours_ahead=hours)
        return JsonResponse({'at_risk': at_risk, 'total': len(at_risk)})
    except Exception as e:
        logger.exception("ia_noshow error")
        return JsonResponse({'error': str(e)}, status=500)


# ─── 5. Utilisation réelle des ressources ────────────────────────────────────
def ia_utilisation(request):
    if not _staff_ok(request):
        return JsonResponse({'error': 'Non autorisé.'}, status=403)
    try:
        days = int(request.GET.get('days', 30))
        days = min(days, 180)

        from dashboard.ai_engine_v2 import get_utilization_analyzer
        data = get_utilization_analyzer().analyse(days=days)
        return JsonResponse(data)
    except Exception as e:
        logger.exception("ia_utilisation error")
        return JsonResponse({'error': str(e)}, status=500)


# ─── 6. Comportements employés : profils de risque ───────────────────────────
def ia_comportement(request):
    if not _staff_ok(request):
        return JsonResponse({'error': 'Non autorisé.'}, status=403)
    try:
        from dashboard.ai_engine_v2 import get_behavior_profiler
        stats = get_behavior_profiler().get_employee_risk_stats()
        return JsonResponse({'employes': stats})
    except Exception as e:
        logger.exception("ia_comportement error")
        return JsonResponse({'error': str(e)}, status=500)
