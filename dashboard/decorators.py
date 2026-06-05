from functools import wraps
from django.shortcuts import redirect

def login_required_mongo(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.mongo_user.get('is_authenticated'):
            return redirect('login_employe')
        return view_func(request, *args, **kwargs)
    return wrapper

def staff_required_mongo(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.mongo_user.get('is_staff'):
            return redirect('login_employe')
        return view_func(request, *args, **kwargs)
    return wrapper