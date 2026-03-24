from django_ratelimit.decorators import ratelimit
from functools import wraps


def rate_limit_login(view_func):
    """Rate limit authentication endpoints: 5 attempts per minute per IP."""
    @ratelimit(key='ip', rate='5/m', method='POST', block=True)
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapped


def rate_limit_password_reset(view_func):
    """Rate limit password reset: 3 attempts per hour per email."""
    @ratelimit(key='user_or_email', rate='3/h', method='POST', block=True)
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapped


def rate_limit_file_upload(view_func):
    """Rate limit file uploads: 20 uploads per minute per user."""
    @ratelimit(key='user', rate='20/m', method='POST', block=True)
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)
    return wrapped