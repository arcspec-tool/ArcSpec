import json
from datetime import timedelta
from unittest.mock import patch

from asgiref.sync import sync_to_async
from asgiref.testing import ApplicationCommunicator
from django.conf import settings
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.core.site import site_host
from apps.mcp.asgi import McpGateway
from apps.mcp.models import Connection
from apps.mcp.server import TOOLS
from apps.mcp.tests.support import client_application, mint, switch
from config.asgi import application

METADATA = f'{settings.SITE_URL}/.well-known/oauth-protected-resource/mcp/'
CHALLENGE = f'Bearer resource_metadata="{METADATA}", scope="read"'
INVALID = f'Bearer error="invalid_token", resource_metadata="{METADATA}", scope="read"'
INSUFFICIENT = f'Bearer error="insufficient_scope", resource_metadata="{METADATA}", scope="write"'
CALL_WHOAMI = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'whoami', 'arguments': {}}}).encode()


def http_scope(method='POST', path='/mcp/', headers=None):
    merged = {
        'host': site_host(),
        'accept': 'application/json, text/event-stream',
        'content-type': 'application/json',
    }
    merged.update(headers or {})
    return {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.3'},
        'http_version': '1.1',
        'method': method,
        'scheme': 'http',
        'path': path,
        'raw_path': path.encode(),
        'query_string': b'',
        'root_path': '',
        'headers': [(key.encode('latin-1'), value.encode('latin-1')) for key, value in merged.items() if value is not None],
        'client': ('127.0.0.1', 40000),
        'server': ('127.0.0.1', 27415),
    }


async def call(app, method='POST', path='/mcp/', headers=None, body=b''):
    communicator = ApplicationCommunicator(app, http_scope(method, path, headers))
    await communicator.send_input({'type': 'http.request', 'body': body, 'more_body': False})
    start = await communicator.receive_output(5)
    chunks = []
    while True:
        message = await communicator.receive_output(5)
        chunks.append(message.get('body', b''))
        if not message.get('more_body'):
            break
    await communicator.wait(5)
    return start['status'], {key.decode().lower(): value.decode() for key, value in start['headers']}, b''.join(chunks)


def sse_result(body):
    for line in body.decode().splitlines():
        if line.startswith('data: '):
            return json.loads(line[6:])
    return None


class LifespanTests(SimpleTestCase):

    async def test_the_lifespan_reports_startup_complete_and_shutdown_complete(self):
        communicator = ApplicationCommunicator(application, {'type': 'lifespan', 'asgi': {'version': '3.0'}})
        await communicator.send_input({'type': 'lifespan.startup'})
        self.assertEqual(await communicator.receive_output(5), {'type': 'lifespan.startup.complete'})
        await communicator.send_input({'type': 'lifespan.shutdown'})
        self.assertEqual(await communicator.receive_output(5), {'type': 'lifespan.shutdown.complete'})
        await communicator.wait(5)

    async def test_a_startup_error_is_reported_as_startup_failed(self):
        communicator = ApplicationCommunicator(application, {'type': 'lifespan', 'asgi': {'version': '3.0'}})
        with patch('apps.mcp.asgi.build_server', side_effect=RuntimeError('no server')):
            await communicator.send_input({'type': 'lifespan.startup'})
            self.assertEqual(await communicator.receive_output(5), {'type': 'lifespan.startup.failed', 'message': 'no server'})
            await communicator.wait(5)


class GateTests(TransactionTestCase):

    def setUp(self):
        self.user = UserFactory()

    def unusable_tokens(self):
        inactive = UserFactory(is_active=False)
        return (
            ('no token', None, CHALLENGE),
            ('unknown token', 'never-minted', INVALID),
            ('expired token', mint(self.user, 'expired', expires=timezone.now() - timedelta(seconds=1)), INVALID),
            ('another resource', mint(self.user, 'elsewhere', resource=[settings.SITE_URL + '/other/']), INVALID),
            ('no resource', mint(self.user, 'unbound', resource=[]), INVALID),
            ('deactivated user', mint(inactive, 'inactive'), INVALID),
        )

    async def test_every_path_but_the_endpoint_reaches_the_django_application(self):
        reached = []

        async def django_stub(scope, receive, send):
            reached.append(scope['path'])
            await send({'type': 'http.response.start', 'status': 204, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})

        with patch('config.asgi.django_application', django_stub):
            for path in ('/mcp/other', '/health/'):
                with self.subTest(path=path):
                    status, headers, body = await call(application, method='GET', path=path)
                    self.assertEqual((status, reached[-1]), (204, path))

    async def test_the_endpoint_with_and_without_the_final_slash_reaches_the_gate(self):
        reached = []

        async def django_stub(scope, receive, send):
            reached.append(scope['path'])
            await send({'type': 'http.response.start', 'status': 204, 'headers': []})
            await send({'type': 'http.response.body', 'body': b''})

        with patch('config.asgi.django_application', django_stub):
            for path in ('/mcp', '/mcp/'):
                with self.subTest(path=path):
                    status, headers, body = await call(application, path=path, body=CALL_WHOAMI)
                    self.assertEqual((status, headers['www-authenticate'], reached), (401, CHALLENGE, []))

    async def test_a_tool_answers_at_the_endpoint_without_the_final_slash(self):
        await sync_to_async(switch)(True)
        raw = await sync_to_async(mint)(self.user)
        gateway = McpGateway()
        async with gateway.running():
            status, headers, body = await call(gateway, path='/mcp', headers={'authorization': f'Bearer {raw}'}, body=CALL_WHOAMI)
        self.assertEqual((status, sse_result(body)['result']['structuredContent']['email']), (200, self.user.email))

    async def test_while_the_switch_is_off_every_request_gets_the_discovery_challenge(self):
        raw = await sync_to_async(mint)(self.user)
        gateway = McpGateway()
        async with gateway.running():
            for case, headers in (('no token', {}), ('valid token', {'authorization': f'Bearer {raw}'})):
                with self.subTest(case=case):
                    status, response_headers, body = await call(gateway, headers=headers, body=CALL_WHOAMI)
                    self.assertEqual(status, 401)
                    self.assertEqual(response_headers['www-authenticate'], INVALID if headers else CHALLENGE)
                    self.assertEqual(response_headers['cache-control'], 'no-store')

    async def test_get_and_delete_answer_405(self):
        await sync_to_async(switch)(True)
        gateway = McpGateway()
        async with gateway.running():
            for method in ('GET', 'DELETE'):
                with self.subTest(method=method):
                    status, headers, body = await call(gateway, method=method)
                    self.assertEqual((status, headers['allow']), (405, 'POST'))

    async def test_a_request_without_a_usable_token_gets_401_with_the_challenge(self):
        await sync_to_async(switch)(True)
        cases = await sync_to_async(self.unusable_tokens)()
        gateway = McpGateway()
        async with gateway.running():
            for case, raw, expected in cases:
                with self.subTest(case=case):
                    headers = {'authorization': f'Bearer {raw}'} if raw else {}
                    status, response_headers, body = await call(gateway, headers=headers, body=CALL_WHOAMI)
                    self.assertEqual((status, response_headers['www-authenticate']), (401, expected))

    async def test_a_wrong_host_answers_421_and_a_foreign_origin_403(self):
        await sync_to_async(switch)(True)
        gateway = McpGateway()
        async with gateway.running():
            for case, headers, expected, description in (
                ('wrong host', {'host': 'elsewhere.example:27415'}, 421, 'The Host header does not name this site.'),
                ('foreign origin', {'origin': 'https://elsewhere.example'}, 403, 'The Origin header does not name this site.'),
            ):
                with self.subTest(case=case):
                    status, response_headers, body = await call(gateway, headers=headers, body=CALL_WHOAMI)
                    self.assertEqual((status, json.loads(body)), (expected, {'error_description': description}))
                    self.assertNotIn('www-authenticate', response_headers)

    async def test_whoami_returns_the_token_users_name_email_and_system_role(self):
        await sync_to_async(switch)(True)
        raw = await sync_to_async(mint)(self.user)
        gateway = McpGateway()
        async with gateway.running():
            status, headers, body = await call(gateway, headers={'authorization': f'Bearer {raw}'}, body=CALL_WHOAMI)
        self.assertEqual(status, 200)
        result = sse_result(body)['result']
        self.assertEqual(result['isError'], False)
        self.assertEqual(result['structuredContent'], {'name': str(self.user), 'email': self.user.email, 'system_role': 'user'})

    async def test_a_read_only_token_gets_403_insufficient_scope_for_every_tool_that_is_not_read_only(self):
        await sync_to_async(switch)(True)
        raw = await sync_to_async(mint)(self.user)
        gateway = McpGateway()
        async with gateway.running():
            for spec in [spec for spec in TOOLS.values() if not spec.annotations.read_only_hint]:
                with self.subTest(tool=spec.name):
                    body = json.dumps({
                        'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': spec.name, 'arguments': {}},
                    }).encode()
                    status, headers, response = await call(gateway, headers={'authorization': f'Bearer {raw}'}, body=body)
                    self.assertEqual((status, headers['www-authenticate']), (403, INSUFFICIENT))

    async def test_a_read_only_token_with_a_body_that_does_not_parse_gets_400(self):
        await sync_to_async(switch)(True)
        raw = await sync_to_async(mint)(self.user)
        gateway = McpGateway()
        async with gateway.running():
            status, headers, body = await call(gateway, headers={'authorization': f'Bearer {raw}'}, body=b'{not json')
        self.assertEqual((status, json.loads(body)), (400, {'error_description': 'The request body is not valid JSON.'}))

    async def test_last_used_at_is_written_once_per_five_minutes(self):
        await sync_to_async(switch)(True)
        application = await sync_to_async(client_application)()
        connection = await sync_to_async(Connection.objects.create)(user=self.user, application=application, scope='read')
        raw = await sync_to_async(mint)(self.user, application=application)
        read = sync_to_async(lambda: Connection.objects.values_list('last_used_at', flat=True).get(pk=connection.pk))
        started = timezone.now()
        instants = (started, started + timedelta(minutes=4), started + timedelta(minutes=6))
        gateway = McpGateway()
        async with gateway.running():
            with patch('apps.mcp.auth.timezone') as clock:
                clock.now.side_effect = instants
                written = []
                for _ in instants:
                    await call(gateway, headers={'authorization': f'Bearer {raw}'}, body=CALL_WHOAMI)
                    written.append(await read())
        self.assertEqual(written, [started, started, started + timedelta(minutes=6)])
