def employe_photo(request):
    if not request.user.is_authenticated or request.user.is_staff:
        return {'employe_photo': ''}
    try:
        from .views import db
        employe = (
            db.employees.find_one({'django_user_id': request.user.id})
            or db.employees.find_one({'django_username': request.user.username})
        )
        if not employe:
            return {'employe_photo': ''}
        photo = employe.get('photo') or ''
        if photo and not photo.startswith('data:'):
            if photo.startswith('/9j') or photo.upper().startswith('FFD8'):
                mime = 'image/jpeg'
            elif photo.startswith('iVBOR'):
                mime = 'image/png'
            elif photo.startswith('R0lG'):
                mime = 'image/gif'
            else:
                mime = 'image/jpeg'
            photo = f'data:{mime};base64,{photo}'
        return {'employe_photo': photo}
    except Exception:
        return {'employe_photo': ''}