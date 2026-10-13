from urllib.parse import urlsplit

from django.conf import settings


def absolute_url(path=''):
    return f'{settings.SITE_URL}{path}'


def site_host():
    return urlsplit(settings.SITE_URL).netloc
