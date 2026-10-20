import re
import secrets
import uuid
from datetime import timedelta

from django.contrib.messages import get_messages
from django.db import connection as database
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application, Grant, RefreshToken, set_token_value

from apps.accounts.factories import UserFactory
from apps.mcp.models import Connection, TokenFamily
from apps.mcp.tests.support import CHALLENGE, REDIRECT_URI, RESOURCE, client_application, switch


def connect(user, application, authorized_at=None, revoked=False):
    family = uuid.uuid4()
    access = AccessToken(
        user=user, application=application, scope='read write',
        expires=timezone.now() + timedelta(hours=1), resource=[RESOURCE],
    )
    set_token_value(access, secrets.token_urlsafe(32))
    access.save()
    refresh = RefreshToken(
        user=user, application=application, access_token=access, token_family=family,
        revoked=timezone.now() if revoked else None,
    )
    set_token_value(refresh, secrets.token_urlsafe(32))
    refresh.save()
    row, created = Connection.objects.get_or_create(user=user, application=application, defaults={'scope': 'read write'})
    TokenFamily.objects.create(connection=row, token_family=family, authorized_at=authorized_at or timezone.now())
    return row


def listed(response):
    return re.findall(r'data-connection="([^"]+)"', response.content.decode())


class ConnectedAppsTests(TestCase):

    def setUp(self):
        switch(True)
        self.user = UserFactory()
        self.other = UserFactory()
        self.application = client_application()
        self.client.force_login(self.user)

    def second_application(self, n):
        return client_application(client_id=f'https://client{n}.example/oauth/metadata.json', name=f'Client {n}')

    def test_the_section_lists_the_users_own_connections_and_not_another_users(self):
        mine = connect(self.user, self.application)
        connect(self.other, self.application)
        self.assertEqual(listed(self.client.get(reverse('settings'))), [str(mine.public_key)])

    def test_a_connection_with_revoked_tokens_or_an_authorization_thirty_days_old_is_not_listed(self):
        live = connect(self.user, self.application)
        cases = (
            ('revoked', 1, {'revoked': True}),
            ('thirty days old', 2, {'authorized_at': timezone.now() - timedelta(days=30)}),
        )
        for case, n, state in cases:
            with self.subTest(case=case):
                connect(self.user, self.second_application(n), **state)
                self.assertEqual(listed(self.client.get(reverse('settings'))), [str(live.public_key)])

    def test_while_the_switch_is_on_the_section_shows_without_a_connection_and_without_the_note(self):
        response = self.client.get(reverse('settings'))
        content = response.content.decode()
        self.assertEqual(('id="connected-apps"' in content, listed(response), 'data-mcp-off' in content), (True, [], False))

    def test_while_the_switch_is_off_the_section_is_hidden_without_a_connection_and_shows_the_rows_and_note_with_one(self):
        with_connection = UserFactory()
        row = connect(with_connection, self.application)
        switch(False)
        cases = (
            ('no connection', self.user, False, [], False),
            ('one connection', with_connection, True, [str(row.public_key)], True),
        )
        for case, user, shown, rows, note in cases:
            with self.subTest(case=case):
                self.client.force_login(user)
                response = self.client.get(reverse('settings'))
                content = response.content.decode()
                self.assertEqual(('id="connected-apps"' in content, listed(response), 'data-mcp-off' in content), (shown, rows, note))

    def test_disconnect_revokes_the_users_tokens_for_the_client_and_leaves_another_users(self):
        mine = connect(self.user, self.application)
        theirs = connect(self.other, self.application)
        Grant.objects.create(
            user=self.user, application=self.application, code='unused-code', expires=timezone.now() + timedelta(minutes=5),
            redirect_uri=REDIRECT_URI, scope='read', code_challenge=CHALLENGE, code_challenge_method='S256',
        )
        self.client.post(reverse('mcp_disconnect', kwargs={'public_key': mine.public_key}))
        self.assertEqual((
            AccessToken.objects.filter(user=self.user).count(),
            RefreshToken.objects.filter(user=self.user, revoked__isnull=True).count(),
            Grant.objects.filter(user=self.user).count(),
            Connection.objects.filter(user=self.user).count(),
        ), (0, 0, 0, 0))
        self.assertEqual((
            AccessToken.objects.filter(user=self.other).count(),
            RefreshToken.objects.filter(user=self.other, revoked__isnull=True).count(),
            Connection.objects.filter(pk=theirs.pk).count(),
            Application.objects.filter(pk=self.application.pk).count(),
        ), (1, 1, 1, 1))

    def test_disconnect_returns_to_the_section_with_the_apps_name_in_the_message(self):
        mine = connect(self.user, self.application)
        response = self.client.post(reverse('mcp_disconnect', kwargs={'public_key': mine.public_key}))
        self.assertEqual((response.status_code, response['Location']), (302, '/settings/#connected-apps'))
        self.assertEqual([str(message) for message in get_messages(response.wsgi_request)], ['Fixed Client is disconnected.'])

    def test_disconnect_with_another_users_key_answers_404_and_changes_nothing(self):
        theirs = connect(self.other, self.application)
        response = self.client.post(reverse('mcp_disconnect', kwargs={'public_key': theirs.public_key}))
        self.assertEqual(response.status_code, 404)
        self.assertEqual((
            Connection.objects.filter(pk=theirs.pk).count(),
            RefreshToken.objects.filter(user=self.other, revoked__isnull=True).count(),
        ), (1, 1))

    def test_the_page_runs_a_constant_number_of_queries_with_one_and_three_connections(self):
        connect(self.user, self.application)
        self.client.get(reverse('settings'))
        with CaptureQueriesContext(database) as one:
            first = self.client.get(reverse('settings'))
        connect(self.user, self.second_application(1))
        connect(self.user, self.second_application(2))
        with CaptureQueriesContext(database) as three:
            second = self.client.get(reverse('settings'))
        self.assertEqual((len(three), len(listed(first)), len(listed(second))), (len(one), 1, 3))
