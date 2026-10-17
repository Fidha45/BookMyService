import os
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-that-is-never-used-outside-tests")
os.environ["DEBUG"] = "True"
from .settings import *

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "testserver"]
SECURE_SSL_REDIRECT = False
MIDDLEWARE = [m for m in MIDDLEWARE if m != "whitenoise.middleware.WhiteNoiseMiddleware"]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
# A file-backed test DB lets race tests use independent SQLite connections.
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"]["TEST"] = {"NAME": BASE_DIR / ".test_bookmyservice.sqlite3"}
