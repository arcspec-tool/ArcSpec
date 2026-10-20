from .base import *
from .base import MIDDLEWARE, env

DEBUG = True
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost'])

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
