import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
# Load local Vercel variables first, then ordinary development variables. Values
# already supplied by the process or hosting platform always take precedence.
for env_file in (BASE_DIR / ".env.local", BASE_DIR / ".env"):
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
DEBUG = os.getenv("DEBUG", "False").lower() in {"true", "1", "yes"}
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("SECRET_KEY must be set when DEBUG=False.")
    SECRET_KEY = "local-development-key-only-do-not-deploy-4827"
render_external_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
vercel_hosts = [
    os.getenv(name, "").strip()
    for name in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL")
    if os.getenv(name, "").strip()
]
if DEBUG:
    default_allowed_hosts = "localhost,127.0.0.1"
elif os.getenv("VERCEL_URL") or os.getenv("VERCEL_PROJECT_PRODUCTION_URL"):
    default_allowed_hosts = ",".join([".vercel.app", *vercel_hosts])
else:
    default_allowed_hosts = render_external_hostname
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", default_allowed_hosts).split(",") if h.strip()]
if not DEBUG:
    if len(SECRET_KEY) < 50 or SECRET_KEY == "replace-with-a-long-random-secret":
        raise RuntimeError("Set SECRET_KEY to a private random value of at least 50 characters when DEBUG=False.")
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise RuntimeError("Set ALLOWED_HOSTS to the exact public hostnames when DEBUG=False.")
INSTALLED_APPS = [
    "config.apps.BookMyServiceAdminConfig", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "accounts", "services", "bookings", "reviews",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "config.middleware.ActiveUserMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
              "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages", "config.context_processors.notification_count"]}}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"




database_url = os.getenv("DATABASE_URL", "")
if not DEBUG and not database_url.startswith(("postgres://", "postgresql://")) and os.getenv("DB_ENGINE", "").lower() != "mysql":
    raise RuntimeError("Configure DATABASE_URL for PostgreSQL or DB_ENGINE=mysql before starting with DEBUG=False.")

if database_url.startswith(("postgres://", "postgresql://")):
    from urllib.parse import urlparse, unquote
    parsed = urlparse(database_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": parsed.port or "5432",
            "CONN_MAX_AGE": 0 if (os.getenv("VERCEL_URL") or os.getenv("VERCEL_PROJECT_PRODUCTION_URL")) else 60,
            "OPTIONS": {"sslmode": os.getenv("DB_SSLMODE", "prefer")},
        }
    }
elif os.getenv("DB_ENGINE", "").lower() == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "bookmyservice"),
            "USER": os.getenv("DB_USER", "root"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    sqlite_database_path = os.getenv("SQLITE_DB_PATH", "").strip()
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(sqlite_database_path).expanduser() if sqlite_database_path else BASE_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 30},
        }
    }


AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
blob_token = os.getenv("BLOB_READ_WRITE_TOKEN", "").strip()
if os.getenv("VERCEL") == "1" and not blob_token:
    raise RuntimeError("Create a Vercel Blob store and set BLOB_READ_WRITE_TOKEN before deploying.")
default_file_storage = (
    "config.storage.VercelBlobStorage" if blob_token
    else "django.core.files.storage.FileSystemStorage"
)
STORAGES = {"default": {"BACKEND": default_file_storage}, "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "service_list"
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in {"true", "1", "yes"}
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "BookMyService <no-reply@bookmyservice.local>")
production_hostname = render_external_hostname or os.getenv("VERCEL_PROJECT_PRODUCTION_URL", "").strip() or os.getenv("VERCEL_URL", "").strip()
SITE_URL = os.getenv("SITE_URL", "").strip() or (f"https://{production_hostname}" if production_hostname else "")
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND") or (
    "django.core.mail.backends.console.EmailBackend" if DEBUG and not EMAIL_HOST
    else "django.core.mail.backends.smtp.EmailBackend"
)
if not DEBUG:
    # Render and Vercel terminate TLS at their edge and forward the original scheme.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "True").lower() == "true"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
