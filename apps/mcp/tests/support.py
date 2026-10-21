import base64
import hashlib
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application, set_token_value

from apps.administration.models import SystemSettings

CLIENT_ID = 'https://client.example/oauth/metadata.json'
CLIENT_NAME = 'Fixed Client'
REDIRECT_URI = 'http://localhost:51515/callback'
STATE = 'state-of-the-check'
VERIFIER = 'verifier-verifier-verifier-verifier-verifier-1'
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b'=').decode()
RESOURCE = settings.SITE_URL + '/mcp/'


class FixedFetcher:
    calls = 0
    document = {
        'client_name': CLIENT_NAME,
        'redirect_uris': ['http://localhost/callback', 'http://client.example/callback'],
        'grant_types': ['authorization_code', 'refresh_token'],
        'token_endpoint_auth_method': 'none',
    }

    def fetch(self, client_id):
        FixedFetcher.calls += 1
        return {**self.document, 'client_id': client_id}, 3600


def oauth_settings(**overrides):
    return {**settings.OAUTH2_PROVIDER, **overrides}


def mint(user, raw='phase-two-token', scope='read', resource=None, expires=None, application=None):
    token = AccessToken(
        user=user, scope=scope, application=application,
        expires=expires or timezone.now() + timedelta(hours=1),
        resource=[RESOURCE] if resource is None else resource,
    )
    set_token_value(token, raw)
    token.save()
    return raw


def switch(on):
    row = SystemSettings.load()
    row.mcp_enabled = on
    row.save()


def client_application(client_id=CLIENT_ID, name=CLIENT_NAME):
    return Application.objects.create(
        client_id=client_id, name=name, user=None,
        client_type=Application.CLIENT_PUBLIC, authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=' '.join(FixedFetcher.document['redirect_uris']),
        registration_source=Application.RegistrationSource.CIMD,
    )


def authorize_params(**overrides):
    params = {
        'response_type': 'code', 'client_id': CLIENT_ID, 'redirect_uri': REDIRECT_URI, 'state': STATE,
        'code_challenge': CHALLENGE, 'code_challenge_method': 'S256', 'scope': 'read write', 'resource': RESOURCE,
    }
    params.update(overrides)
    return {key: value for key, value in params.items() if value is not None}


def consent_data(scope='read', allow=True, **overrides):
    data = {
        'redirect_uri': REDIRECT_URI, 'scope': scope, 'client_id': CLIENT_ID, 'state': STATE, 'response_type': 'code',
        'code_challenge': CHALLENGE, 'code_challenge_method': 'S256', 'resource': RESOURCE,
    }
    if allow:
        data['allow'] = '1'
    data.update(overrides)
    return data


def redirect_query(response):
    parts = urlsplit(response['Location'])
    return f'{parts.scheme}://{parts.netloc}{parts.path}', parse_qs(parts.query)


def exchange(client, code):
    return client.post(reverse('oauth2_provider:token'), {
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID, 'code_verifier': VERIFIER,
    })


def refresh(client, refresh_token):
    return client.post(reverse('oauth2_provider:token'), {
        'grant_type': 'refresh_token', 'refresh_token': refresh_token, 'client_id': CLIENT_ID,
    })


def authorize_and_exchange(client, scope='read write'):
    consent = client.post(reverse('oauth2_provider:authorize'), consent_data(scope=scope))
    base, query = redirect_query(consent)
    return exchange(client, query['code'][0]).json()
