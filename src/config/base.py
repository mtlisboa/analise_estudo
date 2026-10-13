from pathlib import Path

import environ


BASE_DIR = Path(__file__).resolve().parent.parent.parent


env = environ.Env(
    DEBUG=(bool, False),
)


environ.Env.read_env(BASE_DIR / ".env")


SECRET_KEY = env("SECRET_KEY")

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1"],
)


INSTALLED_APPS = [
    # apps Django
]


MIDDLEWARE = [
    # middlewares
]


ROOT_URLCONF = "config.settings.urls"


DATABASES = {
    "default": env.db("DATABASE_URL")
}