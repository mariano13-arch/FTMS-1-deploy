import os

import dj_database_url

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-local-development-only")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = [
    host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
]

INSTALLED_APPS = [
    "daphne",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "channels",
    "corsheaders",
    "accounts",
    "health",
    "fleet",
    "ml",
    "transport_requests",
    "telemetry",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default="postgis://ftms:local-development-only@localhost:5432/ftms",
        engine="django.contrib.gis.db.backends.postgis",
        conn_max_age=60,
    )
}
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TWO_FACTOR_ENCRYPTION_KEY = os.getenv("TWO_FACTOR_ENCRYPTION_KEY", "")
TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "")
TOMTOM_MATRIX_API_KEY = os.getenv(
    "TOMTOM_MATRIX_API_KEY",
    TOMTOM_API_KEY,
)
# Search can use a separately provisioned key. In local Compose, this falls back
# to the browser map key so an older Orbis-only server key cannot break search.
TOMTOM_SEARCH_API_KEY = os.getenv("TOMTOM_SEARCH_API_KEY", "")
FLIGHTRADAR24_API_TOKEN = os.getenv("FLIGHTRADAR24_API_TOKEN", "")
# Intentionally have no defaults: airport-pickup timing is blocked until operations
# explicitly approves these values.
AIRPORT_PASSENGER_READY_ALLOWANCE_MINUTES = os.getenv(
    "AIRPORT_PASSENGER_READY_ALLOWANCE_MINUTES", ""
)
DISPATCH_OPERATIONAL_BUFFER_MINUTES = os.getenv(
    "DISPATCH_OPERATIONAL_BUFFER_MINUTES", ""
)
DISPATCH_TELEMETRY_MAX_AGE_SECONDS = int(
    os.getenv("DISPATCH_TELEMETRY_MAX_AGE_SECONDS", "300")
)
DISPATCH_SIMULATED_TELEMETRY_MAX_AGE_SECONDS = int(
    os.getenv("DISPATCH_SIMULATED_TELEMETRY_MAX_AGE_SECONDS", "86400")
)
FTMS_TELEMETRY_CLOCK_SKEW_SECONDS = int(
    os.getenv("FTMS_TELEMETRY_CLOCK_SKEW_SECONDS", "300")
)
FTMS_DEMO_TELEMETRY_ENABLED = os.getenv("FTMS_DEMO_TELEMETRY_ENABLED", "false").lower() == "true"
FTMS_DEMO_TELEMETRY_CENTER_LATITUDE = os.getenv("FTMS_DEMO_TELEMETRY_CENTER_LATITUDE", "")
FTMS_DEMO_TELEMETRY_CENTER_LONGITUDE = os.getenv("FTMS_DEMO_TELEMETRY_CENTER_LONGITUDE", "")
FTMS_DEMO_TELEMETRY_RADIUS_METERS = os.getenv("FTMS_DEMO_TELEMETRY_RADIUS_METERS", "1500")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Manila")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

def env_list(name, default=""):
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


CORS_ALLOWED_ORIGINS = env_list("DJANGO_CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SESSION_COOKIE_SECURE", "true").lower() == "true"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
FTMS_SESSION_IDLE_TIMEOUT_SECONDS = int(
    os.getenv("FTMS_SESSION_IDLE_TIMEOUT_SECONDS", "43200")
)
FTMS_SESSION_ABSOLUTE_TIMEOUT_SECONDS = int(
    os.getenv("FTMS_SESSION_ABSOLUTE_TIMEOUT_SECONDS", "86400")
)
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_CSRF_COOKIE_SECURE", "true").lower() == "true"
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("DJANGO_EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.getenv("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("DJANGO_EMAIL_USE_TLS", "false").lower() == "true"
DEFAULT_FROM_EMAIL = os.getenv(
    "DJANGO_DEFAULT_FROM_EMAIL", "FTMS Driver Mobile <no-reply@localhost>"
)
DRIVER_MOBILE_ACCOUNT_SETUP_URL = os.getenv(
    "DRIVER_MOBILE_ACCOUNT_SETUP_URL", "ftms-driver://setup-password"
)
STAFF_ACCOUNT_SETUP_URL = os.getenv("STAFF_ACCOUNT_SETUP_URL", "")
STAFF_PASSWORD_RESET_URL = os.getenv("STAFF_PASSWORD_RESET_URL", "")
PASSWORD_RESET_TIMEOUT = int(os.getenv("DJANGO_PASSWORD_RESET_TIMEOUT", "3600"))
DRIVER_MOBILE_APP_DOWNLOAD_URL = os.getenv("DRIVER_MOBILE_APP_DOWNLOAD_URL", "")
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.StaffSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {
        "login": os.getenv("DJANGO_LOGIN_THROTTLE", "5/min"),
        "two_factor_verify": os.getenv("DJANGO_TWO_FACTOR_VERIFY_THROTTLE", "10/min"),
        "password_reset": os.getenv("DJANGO_PASSWORD_RESET_THROTTLE", "5/hour"),
        "password_reset_completion": os.getenv(
            "DJANGO_PASSWORD_RESET_COMPLETION_THROTTLE", "10/hour"
        ),
    },
}
