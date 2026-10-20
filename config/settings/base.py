from pathlib import Path

import environ
from csp.constants import NONCE

env = environ.Env()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('SECRET_KEY')
DEBUG = False

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.microsoft',
    'rest_framework',
    'crispy_forms',
    'crispy_bootstrap5',
    'compressor',
    'oauth2_provider',

    'apps.core',
    'apps.accounts',
    'apps.doctemplates',
    'apps.projects',
    'apps.administration',
    'apps.notifications',
    'apps.mcp',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'csp.middleware.CSPMiddleware',
    'apps.core.middleware.AjaxRedirectMiddleware',
]

ROOT_URLCONF = 'config.urls'

AUTH_USER_MODEL = 'accounts.User'
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_SIGNUP_FIELDS = ['email*']
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_ONLY = True
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapters.InviteOnlySocialAccountAdapter'
ACCOUNT_ADAPTER = 'apps.accounts.adapters.AccountAdapter'
LOGIN_URL = '/'
LOGIN_REDIRECT_URL = '/dashboard/'
PASSWORD_RESET_TIMEOUT = 86400
AUTH_CALLBACK_PREFIX = env('AUTH_CALLBACK_PREFIX')
SITE_URL = env('SITE_URL').rstrip('/')

OAUTH2_PROVIDER = {
    'COMPLIANT_BCP_RFC9700_TOKEN_STORAGE': True,
    'REFRESH_TOKEN_GRACE_PERIOD_SECONDS': 0,
    'ACCESS_TOKEN_EXPIRE_SECONDS': 3600,
    'REFRESH_TOKEN_EXPIRE_SECONDS': 2592000,
    'SCOPES': {'read': 'Read', 'write': 'Write'},
    'DEFAULT_SCOPES': ['read'],
    'OIDC_ENABLED': False,
    'OIDC_ISS_ENDPOINT': SITE_URL,
    'OAUTH2_PROTECTED_RESOURCE_IDENTIFIER': f'{SITE_URL}/mcp/',
}

SOCIALACCOUNT_PROVIDERS = {
    'microsoft': {
        'APPS': [{
            'client_id': env('ENTRA_CLIENT_ID', default=''),
            'secret': env('ENTRA_CLIENT_SECRET', default=''),
            'settings': {
                'tenant': env('ENTRA_TENANT_ID', default=''),
            },
        }],
        'SCOPE': ['openid', 'email', 'profile', 'User.Read'],
        'AUTH_PARAMS': {'prompt': 'select_account'},
    }
}

CAPTCHA_KEYS = {
    'turnstile': {
        'site_key': env('TURNSTILE_SITE_KEY', default=''),
        'secret_key': env('TURNSTILE_SECRET_KEY', default=''),
    },
    'hcaptcha': {
        'site_key': env('HCAPTCHA_SITE_KEY', default=''),
        'secret_key': env('HCAPTCHA_SECRET_KEY', default=''),
    },
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_THROTTLE_RATES': {
        'login_ip': '30/m',
        'login_email': '5/5m',
        'forgot_ip': '20/m',
        'forgot_email': '5/m',
    },
}

CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

TIME_ZONE = 'Europe/Vilnius'
USE_TZ = True
LANGUAGE_CODE = 'en'
LANGUAGES = [('en', 'English')]
USE_I18N = True
LOCALE_PATHS = [BASE_DIR / 'locale']

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
]
COMPRESS_OFFLINE = True
COMPRESS_FILTERS = {
    'css': ['compressor.filters.css_default.CssAbsoluteFilter'],
    'js': [],
}
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.debug',
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'apps.core.context_processors.unread_notification_count',
            'apps.core.context_processors.system_settings',
        ],
    },
}]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('POSTGRES_DB'),
        'USER': env('POSTGRES_USER'),
        'PASSWORD': env('POSTGRES_PASSWORD'),
        'HOST': 'db',
        'PORT': '5432',
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

TEST_RUNNER = 'config.test_runner.TemporaryMediaTestRunner'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.mailgun.org')
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": ["'self'", NONCE],
        "style-src": ["'self'", "'unsafe-inline'"],
        "font-src": ["'self'"],
        "img-src": ["'self'", "data:"],
        "connect-src": ["'self'"],
    }
}
