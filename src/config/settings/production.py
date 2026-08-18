from .base import *  # noqa: F403

DEBUG = False

# Railway terminates TLS before forwarding requests to the application.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
