import hashlib
import re
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlsplit

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application, Grant, RefreshToken

from apps.accounts.factories import UserFactory
from apps.mcp.models import Connection, TokenFamily
from apps.mcp.tests.support import (
    CLIENT_ID, CLIENT_NAME, FixedFetcher, REDIRECT_URI, STATE, authorize_and_exchange, authorize_params,
    client_application, consent_data, exchange, mint, oauth_settings, redirect_query, refresh, switch,
)

FETCHER = 'apps.mcp.tests.support.FixedFetcher'


def hook(content, attribute):
    return re.search(rf'<strong {attribute}>([^<]*)</strong>', content).group(1)


def checksum(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


@override_settings(OAUTH2_PROVIDER=oauth_settings(CIMD_METADATA_FETCHER=FETCHER))
class ConsentPageTests(TestCase):

    def setUp(self):
        cache.clear()
        FixedFetcher.calls = 0
        switch(True)
        self.user = UserFactory()
        self.authorize = reverse('oauth2_provider:authorize')

    def test_the_consent_page_names_the_client_and_the_host_of_its_client_id(self):
        self.client.force_login(self.user)
        response = self.client.get(self.authorize, authorize_params())
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual((hook(content, 'data-client-name'), hook(content, 'data-client-host')), (CLIENT_NAME, 'client.example'))
        self.assertEqual((FixedFetcher.calls, Application.objects.get().name), (1, CLIENT_NAME))

    def test_approval_prompt_auto_still_shows_the_consent_page_and_issues_no_code(self):
        application = client_application()
        mint(self.user, scope='read write', application=application)
        self.client.force_login(self.user)
        response = self.client.get(self.authorize, authorize_params(approval_prompt='auto'))
        self.assertEqual((response.status_code, hook(response.content.decode(), 'data-client-name')), (200, CLIENT_NAME))
        self.assertEqual(Grant.objects.count(), 0)

    def test_read_and_write_is_preselected_only_when_the_client_asks_for_write(self):
        client_application()
        self.client.force_login(self.user)
        for requested, initial in (('read', 'read'), ('read write', 'read write')):
            with self.subTest(requested=requested):
                response = self.client.get(self.authorize, authorize_params(scope=requested))
                self.assertEqual(response.context['form'].initial['scope'], initial)

    def test_a_signed_out_request_goes_to_sign_in_before_any_client_is_loaded(self):
        params = authorize_params(client_id='https://unknown.example/metadata.json', prompt='none')
        url = f'{self.authorize}?{urlencode(params)}'
        response = self.client.get(url)
        location = urlsplit(response['Location'])
        self.assertEqual((response.status_code, location.path, parse_qs(location.query)), (302, '/', {'next': [url]}))
        self.assertEqual((FixedFetcher.calls, Application.objects.count()), (0, 0))

    def test_cancel_sends_the_client_access_denied_with_the_state_and_iss(self):
        client_application()
        self.client.force_login(self.user)
        response = self.client.post(self.authorize, consent_data(allow=False))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(redirect_query(response), (REDIRECT_URI, {'error': ['access_denied'], 'state': [STATE], 'iss': [settings.SITE_URL]}))
        self.assertEqual(Grant.objects.count(), 0)

    def test_the_chosen_access_level_is_the_granted_scope(self):
        client_application()
        self.client.force_login(self.user)
        for choice in ('read', 'read write'):
            with self.subTest(choice=choice):
                token = authorize_and_exchange(self.client, scope=choice)
                stored = AccessToken.objects.get(token_checksum=checksum(token['access_token']))
                self.assertEqual((token['scope'], stored.scope), (choice, choice))

    def test_a_request_without_the_mcp_resource_is_refused_with_invalid_target(self):
        client_application()
        self.client.force_login(self.user)
        expected = {
            'error': ['invalid_target'], 'error_description': ['The resource must be the MCP server of this site.'],
            'state': [STATE], 'iss': [settings.SITE_URL],
        }
        for case, resource in (('none', None), ('another path', settings.SITE_URL + '/api/'), ('two', [settings.SITE_URL + '/mcp/', settings.SITE_URL + '/api/'])):
            with self.subTest(case=case):
                response = self.client.get(self.authorize, authorize_params(resource=resource))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(redirect_query(response), (REDIRECT_URI, expected))

    def test_an_http_redirect_uri_outside_loopback_is_refused(self):
        client_application()
        self.client.force_login(self.user)
        response = self.client.get(self.authorize, authorize_params(redirect_uri='http://client.example/callback'))
        self.assertEqual((response.status_code, response.context['error'].error), (400, 'invalid_request'))


@override_settings(OAUTH2_PROVIDER=oauth_settings(CIMD_METADATA_FETCHER=FETCHER))
class TokenEndpointTests(TestCase):

    def setUp(self):
        cache.clear()
        FixedFetcher.calls = 0
        switch(True)
        self.user = UserFactory()
        self.application = client_application()
        self.client.force_login(self.user)

    def test_a_token_request_with_an_unknown_client_id_creates_no_application_row(self):
        response = self.client.post(reverse('oauth2_provider:token'), {
            'grant_type': 'authorization_code', 'code': 'never-issued', 'redirect_uri': REDIRECT_URI,
            'client_id': 'https://unknown.example/metadata.json', 'code_verifier': 'v' * 43,
        })
        self.assertEqual((response.status_code, response.json()['error']), (401, 'invalid_client'))
        self.assertEqual((FixedFetcher.calls, Application.objects.count()), (0, 1))

    def test_an_exchange_writes_a_connection_and_a_token_family_and_a_refresh_writes_neither(self):
        token = authorize_and_exchange(self.client)
        connection = Connection.objects.get()
        family = TokenFamily.objects.get()
        issued = RefreshToken.objects.get(token_checksum=checksum(token['refresh_token']))
        self.assertEqual((connection.user, connection.application, connection.scope), (self.user, self.application, 'read write'))
        self.assertEqual((family.connection, family.token_family), (connection, issued.token_family))
        refreshed = refresh(self.client, token['refresh_token'])
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual((Connection.objects.count(), TokenFamily.objects.count()), (1, 1))

    def test_a_refresh_thirty_days_after_the_authorization_is_refused_and_a_day_before_succeeds(self):
        token = authorize_and_exchange(self.client)
        for case, age, status, error in (('thirty days', 30, 400, 'invalid_grant'), ('twenty-nine days', 29, 200, None)):
            with self.subTest(case=case):
                TokenFamily.objects.update(authorized_at=timezone.now() - timedelta(days=age))
                response = refresh(self.client, token['refresh_token'])
                self.assertEqual((response.status_code, response.json().get('error')), (status, error))

    def test_a_refresh_by_a_deactivated_user_is_refused(self):
        token = authorize_and_exchange(self.client)
        self.user.is_active = False
        self.user.save()
        response = refresh(self.client, token['refresh_token'])
        self.assertEqual((response.status_code, response.json()['error']), (400, 'invalid_grant'))


class SwitchOffTests(TestCase):

    def setUp(self):
        switch(False)
        self.user = UserFactory()
        client_application()
        self.client.force_login(self.user)

    def test_the_discovery_documents_and_the_oauth_endpoints_answer_404(self):
        requests = (
            ('server metadata', 'get', reverse('oauth2_provider:oauth-server-metadata'), None),
            ('resource metadata', 'get', reverse('oauth2_provider:oauth-resource-metadata'), None),
            ('resource metadata path', 'get', reverse('oauth2_provider:oauth-resource-metadata-path'), None),
            ('authorize', 'get', reverse('oauth2_provider:authorize'), authorize_params()),
            ('token', 'post', reverse('oauth2_provider:token'), {'grant_type': 'authorization_code', 'code': 'x', 'client_id': CLIENT_ID, 'redirect_uri': REDIRECT_URI, 'code_verifier': 'v' * 43}),
            ('revoke', 'post', reverse('oauth2_provider:revoke-token'), {'token': 'x', 'client_id': CLIENT_ID}),
        )
        for case, method, url, data in requests:
            with self.subTest(case=case):
                response = getattr(self.client, method)(url, data)
                self.assertEqual(response.status_code, 404)


class DocumentCachingTests(TestCase):

    def setUp(self):
        switch(True)

    def test_the_discovery_documents_are_sent_with_no_store(self):
        for name in ('oauth-server-metadata', 'oauth-resource-metadata', 'oauth-resource-metadata-path'):
            with self.subTest(name=name):
                response = self.client.get(reverse(f'oauth2_provider:{name}'))
                self.assertEqual((response.status_code, response['Cache-Control']), (200, 'no-store'))
