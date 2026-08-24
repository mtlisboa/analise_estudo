from .base import *  # noqa: F403

DEBUG = False

# Stable Railway production URL. Keep the environment-driven origins from base
# and guarantee that the primary deployment remains trusted even when Railway's
# RAILWAY_PUBLIC_DOMAIN variable is unavailable during a rollout.
PRIMARY_PRODUCTION_ORIGIN = "https://analiseestudo-production.up.railway.app"
if PRIMARY_PRODUCTION_ORIGIN not in CSRF_TRUSTED_ORIGINS:  # noqa: F405
    CSRF_TRUSTED_ORIGINS.append(PRIMARY_PRODUCTION_ORIGIN)  # noqa: F405

# Railway terminates TLS before forwarding requests to the application.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
