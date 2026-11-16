"""Django settings for StudHub's local development environment."""

from os import getenv
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


# Environment and base directory

BASE_DIR = Path(__file__).resolve().parent.parent


# Development and security

# Keep the secret key private in production.
SECRET_KEY = "django-insecure-##*f*!k^(fz+t&kzasd6ed9yvn5!+zp6bj@le-43ra627nfr&m"

# Disable debug mode in production.
DEBUG = True

ALLOWED_HOSTS = ["*"]


# Applications and middleware

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "academics.apps.AcademicsConfig",
    "notifications.apps.NotificationsConfig",
    "dashboard.apps.DashboardConfig",
    "tasks.apps.TasksConfig",
    "students.apps.StudentsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "students.middleware.ProfileCompletionMiddleware",
]


# URL routing and application entry point

ROOT_URLCONF = "core.urls"

WSGI_APPLICATION = "core.wsgi.application"


# Templates

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "dashboard.workspace.workspace_context",
            ],
        },
    },
]


# Database

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}


# Authentication and password validation

AUTHENTICATION_BACKENDS = [
    "allauth.account.auth_backends.AuthenticationBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LOGIN_REDIRECT_URL = "/dashboard/"


# Account login and signup (django-allauth)

SITE_ID = 1

ACCOUNT_LOGIN_METHODS = {"email"}

ACCOUNT_CHANGE_EMAIL = True

ACCOUNT_FORMS = {"login": "core.forms.LoginForm", "signup": "core.forms.SignupForm"}

ACCOUNT_SIGNUP_FIELDS = [
    "email*",
    "password1*",
    "password2*",
]


# Social authentication and Google OAuth

SOCIALACCOUNT_EMAIL_AUTHENTICATION = True

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APPS": [
            {
                "client_id": getenv("GOOGLE_CLIENT_ID"),
                "secret": getenv("GOOGLE_CLIENT_SECRET"),
                "key": "",
            },
        ],
        "SCOPE": [
            "profile",
            "email",
        ],
        "AUTH_PARAMS": {
            "access_type": "online",
        },
        "OAUTH_PKCE_ENABLED": True,
    },
}


# Sessions

SESSION_COOKIE_AGE = 60 * 60 * 24 * 30

SESSION_SAVE_EVERY_REQUEST = True


# Email

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.console.EmailBackend",
    },
}


# Language and time zone

LANGUAGE_CODE = "uk-ua"

TIME_ZONE = "Europe/Kyiv"

USE_I18N = True

USE_TZ = True


# Static files and Tailwind

STATIC_URL = "static/"

STATICFILES_DIRS = [BASE_DIR / "assets"]


# User-uploaded avatars (served by Django only in local development)

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"
