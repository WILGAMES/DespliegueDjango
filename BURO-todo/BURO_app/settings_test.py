from .settings import *  # noqa: F403,F401


# Keep tests independent from external Postgres/Neon.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",  # noqa: F405
    }
}

# Faster and deterministic test behavior.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Reduce noise and accidental outbound integrations in tests.
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
