"""
fix_chatbot_views.py
Remplace les 3 vues chatbot (ORM Django) et la lecture d'historique dans
_ai_response par des opérations PyMongo directes.

Usage : python fix_chatbot_views.py
"""
import re, shutil, sys
from pathlib import Path

VIEWS = Path(r"C:\Users\hp\SIGR-CA-System\dashboard\views.py")

if not VIEWS.exists():
    sys.exit(f"Fichier introuvable : {VIEWS}")

shutil.copy(VIEWS, VIEWS.with_suffix(".py.bak_fix_chatbot"))
print(f"Backup : {VIEWS.with_suffix('.py.bak_fix_chatbot')}")

src = VIEWS.read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# 1. REMPLACER api_chatbot_message
# ─────────────────────────────────────────────────────────────────────────────
OLD_MSG = '''\
@login_required
def api_chatbot_message(request):
    """API pour le chatbot employé"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data             = json.loads(request.body)
        user_message     = data.get('message', '').strip()
        conversation_id  = data.get('conversation_id', '')

        if not user_message:
            return JsonResponse({'error': 'Message vide'}, status=400)

        if conversation_id:
            try:
                conversation = ChatbotConversation.objects.get(id=conversation_id, user=request.user)
            except ChatbotConversation.DoesNotExist:
                conversation = ChatbotConversation.objects.create(user=request.user)
        else:
            conversation = ChatbotConversation.objects.create(user=request.user)

        ChatbotMessage.objects.create(
            conversation=conversation,
            role='user',
            content=user_message,
        )

        response_data = process_chatbot_message(request.user, user_message, conversation)

        ChatbotMessage.objects.create(
            conversation=conversation,
            role='assistant',
            content=response_data['message'],
            intent=response_data.get('intent', ''),
            entities=response_data.get('entities', {}),
        )

        return JsonResponse({
            'status':          'success',
            'message':         response_data['message'],
            'intent':          response_data.get('intent', ''),
            'data':            response_data.get('data', {}),
            'conversation_id': conversation.id,
            'suggestions':     response_data.get('suggestions', []),
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)'''

NEW_MSG = '''\
@login_required
def api_chatbot_message(request):
    """API pour le chatbot employé — PyMongo direct (MongoUser sans ForeignKey)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data            = json.loads(request.body)
        user_message    = data.get('message', '').strip()
        conversation_id = data.get('conversation_id', '')

        if not user_message:
            return JsonResponse({'error': 'Message vide'}, status=400)

        user_key = str(request.session.get('user_id', request.user.username))
        now      = datetime.now()

        # ── Récupérer ou créer la conversation ───────────────────
        conversation = None
        if conversation_id:
            try:
                conversation = db['chatbot_conversations'].find_one({
                    '_id':      ObjectId(conversation_id),
                    'user_key': user_key,
                })
            except Exception:
                pass
        if not conversation:
            result       = db['chatbot_conversations'].insert_one({
                'user_key':  user_key,
                'username':  request.user.username,
                'is_active': True,
                'created_at': now,
                'updated_at': now,
            })
            conversation = db['chatbot_conversations'].find_one({'_id': result.inserted_id})

        conv_id = conversation['_id']

        # ── Sauvegarder le message utilisateur ───────────────────
        db['chatbot_messages'].insert_one({
            'conversation_id': conv_id,
            'role':            'user',
            'content':         user_message,
            'created_at':      now,
        })

        # ── Générer la réponse ────────────────────────────────────
        response_data = process_chatbot_message(request.user, user_message, conversation)

        # ── Sauvegarder la réponse assistante ────────────────────
        db['chatbot_messages'].insert_one({
            'conversation_id': conv_id,
            'role':            'assistant',
            'content':         response_data['message'],
            'intent':          response_data.get('intent', ''),
            'entities':        response_data.get('entities', {}),
            'created_at':      datetime.now(),
        })

        # Mettre à jour updated_at
        db['chatbot_conversations'].update_one(
            {'_id': conv_id},
            {'$set': {'updated_at': datetime.now()}}
        )

        return JsonResponse({
            'status':          'success',
            'message':         response_data['message'],
            'intent':          response_data.get('intent', ''),
            'data':            response_data.get('data', {}),
            'conversation_id': str(conv_id),
            'suggestions':     response_data.get('suggestions', []),
        })

    except Exception as e:
        import traceback; traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)'''

if OLD_MSG in src:
    src = src.replace(OLD_MSG, NEW_MSG, 1)
    print("✓ api_chatbot_message remplacée.")
else:
    print("⚠ api_chatbot_message non trouvée — vérification de la variante...")
    # Chercher par regex plus souple
    m = re.search(
        r'(@login_required\s*\ndef api_chatbot_message\(request\):.*?'
        r'except Exception as e:.*?return JsonResponse\(\{\'error\': str\(e\)\},\s*status=500\))',
        src, re.DOTALL
    )
    if m:
        src = src[:m.start()] + NEW_MSG + src[m.end():]
        print("✓ api_chatbot_message remplacée (variante regex).")
    else:
        print("❌ api_chatbot_message introuvable — correction manuelle requise.")

# ─────────────────────────────────────────────────────────────────────────────
# 2. REMPLACER api_chatbot_conversations
# ─────────────────────────────────────────────────────────────────────────────
OLD_CONVS = '''\
@login_required
def api_chatbot_conversations(request):
    """Récupérer l'historique des conversations"""
    conversations = (
        ChatbotConversation.objects
        .filter(user=request.user, is_active=True)
        .order_by('-updated_at')[:10]
    )
    data = []
    for conv in conversations:
        last_message = conv.messages.filter(role='assistant').last()
        data.append({
            'id':            conv.id,
            'created_at':    conv.created_at.strftime('%d/%m/%Y %H:%M'),
            'last_message':  last_message.content[:100] if last_message else '',
            'message_count': conv.messages.count(),
        })
    return JsonResponse({'conversations': data})'''

NEW_CONVS = '''\
@login_required
def api_chatbot_conversations(request):
    """Récupérer l'historique des conversations — PyMongo direct"""
    user_key = str(request.session.get('user_id', request.user.username))
    raw = list(
        db['chatbot_conversations']
        .find({'user_key': user_key, 'is_active': True})
        .sort('updated_at', -1)
        .limit(10)
    )
    data = []
    for conv in raw:
        conv_id = conv['_id']
        last_msg = db['chatbot_messages'].find_one(
            {'conversation_id': conv_id, 'role': 'assistant'},
            sort=[('created_at', -1)]
        )
        msg_count = db['chatbot_messages'].count_documents({'conversation_id': conv_id})
        created   = conv.get('created_at')
        data.append({
            'id':            str(conv_id),
            'created_at':    created.strftime('%d/%m/%Y %H:%M') if created else '',
            'last_message':  (last_msg['content'][:100] if last_msg else ''),
            'message_count': msg_count,
        })
    return JsonResponse({'conversations': data})'''

if OLD_CONVS in src:
    src = src.replace(OLD_CONVS, NEW_CONVS, 1)
    print("✓ api_chatbot_conversations remplacée.")
else:
    print("⚠ api_chatbot_conversations — recherche variante...")
    m = re.search(
        r'(@login_required\s*\ndef api_chatbot_conversations\(request\):.*?'
        r'return JsonResponse\(\{\'conversations\': data\}\))',
        src, re.DOTALL
    )
    if m:
        src = src[:m.start()] + NEW_CONVS + src[m.end():]
        print("✓ api_chatbot_conversations remplacée (variante regex).")
    else:
        print("❌ api_chatbot_conversations introuvable.")

# ─────────────────────────────────────────────────────────────────────────────
# 3. REMPLACER api_chatbot_conversation_detail (les 2 occurrences)
# ─────────────────────────────────────────────────────────────────────────────
NEW_DETAIL = '''\
@login_required
def api_chatbot_conversation_detail(request, conversation_id):
    """Détail d\'une conversation — PyMongo direct"""
    user_key = str(request.session.get('user_id', request.user.username))
    try:
        conv = db['chatbot_conversations'].find_one({
            '_id':      ObjectId(conversation_id),
            'user_key': user_key,
        })
        if not conv:
            return JsonResponse({'error': 'Conversation non trouvée'}, status=404)
        msgs_raw = list(
            db['chatbot_messages']
            .find({'conversation_id': conv['_id']})
            .sort('created_at', 1)
        )
        msgs = []
        for m in msgs_raw:
            ts = m.get('created_at')
            msgs.append({
                'role':       m.get('role', ''),
                'content':    m.get('content', ''),
                'created_at': ts.strftime('%H:%M') if ts else '',
            })
        return JsonResponse({'messages': msgs, 'conversation_id': str(conv['_id'])})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=404)'''

# Remplacer toutes les occurrences de api_chatbot_conversation_detail
count_detail = 0
for _ in range(5):  # max 5 occurrences
    m = re.search(
        r'@login_required\s*\ndef api_chatbot_conversation_detail\(request,\s*conversation_id\):.*?'
        r'(?=@login_required|\ndef |\Z)',
        src, re.DOTALL
    )
    if m:
        src = src[:m.start()] + NEW_DETAIL + '\n\n' + src[m.end():]
        count_detail += 1
    else:
        break

if count_detail:
    print(f"✓ api_chatbot_conversation_detail remplacée ({count_detail} occurrence(s)).")
else:
    print("❌ api_chatbot_conversation_detail introuvable.")

# ─────────────────────────────────────────────────────────────────────────────
# 4. CORRIGER _ai_response : conversation.messages.order_by(...)
#    → PyMongo direct
# ─────────────────────────────────────────────────────────────────────────────
OLD_HISTORY = '''\
    # Mémoire conversationnelle
    contents  = []
    last_msgs = list(conversation.messages.order_by('-created_at')[:12])
    last_msgs.reverse()
    for m in last_msgs:
        role = 'user' if m.role == 'user' else 'model'
        contents.append(types.Content(role=role, parts=[types.Part(text=m.content)]))
    if not contents or contents[-1].parts[0].text != message:
        contents.append(types.Content(role='user', parts=[types.Part(text=message)]))'''

NEW_HISTORY = '''\
    # Mémoire conversationnelle — PyMongo direct (conversation est un dict MongoDB)
    contents  = []
    try:
        conv_id   = conversation.get('_id') if isinstance(conversation, dict) else None
        if conv_id:
            raw_msgs  = list(
                db['chatbot_messages']
                .find({'conversation_id': conv_id})
                .sort('created_at', -1)
                .limit(12)
            )
            raw_msgs.reverse()
            for m in raw_msgs:
                role = 'user' if m.get('role') == 'user' else 'model'
                contents.append(types.Content(role=role, parts=[types.Part(text=m.get('content', ''))]))
    except Exception as _he:
        logger.warning(f"_ai_response history load échoué: {_he}")
    if not contents or (contents and contents[-1].parts[0].text != message):
        contents.append(types.Content(role='user', parts=[types.Part(text=message)]))'''

if OLD_HISTORY in src:
    src = src.replace(OLD_HISTORY, NEW_HISTORY, 1)
    print("✓ _ai_response : historique PyMongo corrigé.")
else:
    print("⚠ _ai_response historique — recherche variante...")
    m = re.search(
        r'# Mémoire conversationnelle\s*\n.*?contents\.append\(types\.Content\(role=\'user\'.*?\)\)',
        src, re.DOTALL
    )
    if m:
        src = src[:m.start()] + NEW_HISTORY + src[m.end():]
        print("✓ _ai_response historique corrigé (variante regex).")
    else:
        print("❌ _ai_response historique introuvable — correction manuelle nécessaire.")

# ─────────────────────────────────────────────────────────────────────────────
# 5. VÉRIFICATION finale
# ─────────────────────────────────────────────────────────────────────────────
remaining_orm = [
    m.start() for m in re.finditer(
        r'ChatbotConversation\.objects|ChatbotMessage\.objects',
        src
    )
]
if remaining_orm:
    print(f"\n⚠ {len(remaining_orm)} référence(s) ORM ChatbotConversation/ChatbotMessage encore présentes :")
    for pos in remaining_orm:
        line_no = src[:pos].count('\n') + 1
        print(f"  → ligne {line_no} : {src[pos:pos+60].strip()}")
else:
    print("✓ Aucune référence ORM ChatbotConversation/ChatbotMessage restante.")

# ─────────────────────────────────────────────────────────────────────────────
# 6. ÉCRIRE
# ─────────────────────────────────────────────────────────────────────────────
VIEWS.write_text(src, encoding="utf-8")
print(f"\n✅ Fichier corrigé : {VIEWS}")
print("   Redémarrez Django (Ctrl+C puis python manage.py runserver).")
