from contextlib import AsyncExitStack, asynccontextmanager

from asgiref.sync import ThreadSensitiveContext, sync_to_async
from django.conf import settings
from django.core import signals
from django.utils.translation import gettext as _

from apps.administration.models import SystemSettings
from apps.core.site import site_host
from apps.mcp import auth
from apps.mcp.server import build_application, build_server


def header(scope, name):
    wanted = name.encode('latin-1')
    for key, value in scope.get('headers', ()):
        if key == wanted:
            return value.decode('latin-1')
    return None


async def respond(send, status, body=b'', headers=()):
    await send({
        'type': 'http.response.start',
        'status': status,
        'headers': [
            (b'content-type', b'application/json'),
            (b'content-length', str(len(body)).encode()),
            (b'cache-control', b'no-store'),
            *headers,
        ],
    })
    await send({'type': 'http.response.body', 'body': body})


def no_store(send):
    async def wrapped(message):
        if message['type'] == 'http.response.start':
            headers = list(message.get('headers', []))
            if not any(key.lower() == b'cache-control' for key, value in headers):
                headers.append((b'cache-control', b'no-store'))
            message = {**message, 'headers': headers}
        await send(message)
    return wrapped


def mcp_enabled():
    return SystemSettings.load().mcp_enabled


class McpGateway:

    def __init__(self):
        self.application = None

    @asynccontextmanager
    async def running(self):
        server = build_server()
        application = build_application(server)
        async with server.session_manager.run():
            self.application = application
            try:
                yield
            finally:
                self.application = None

    async def lifespan(self, scope, receive, send):
        async with AsyncExitStack() as stack:
            while True:
                message = await receive()
                if message['type'] == 'lifespan.startup':
                    try:
                        await stack.enter_async_context(self.running())
                    except Exception as exc:
                        await send({'type': 'lifespan.startup.failed', 'message': str(exc)})
                        return
                    await send({'type': 'lifespan.startup.complete'})
                elif message['type'] == 'lifespan.shutdown':
                    await stack.aclose()
                    await send({'type': 'lifespan.shutdown.complete'})
                    return

    async def __call__(self, scope, receive, send):
        async with ThreadSensitiveContext():
            await signals.request_started.asend(sender=self.__class__, scope=scope)
            try:
                await self.handle(scope, receive, send)
            finally:
                await signals.request_finished.asend(sender=self.__class__)

    async def handle(self, scope, receive, send):
        if header(scope, 'host') != site_host():
            return await respond(send, 421, auth.error_body(_('The Host header does not name this site.')))
        origin = header(scope, 'origin')
        if origin is not None and origin != settings.SITE_URL:
            return await respond(send, 403, auth.error_body(_('The Origin header does not name this site.')))
        authorization = header(scope, 'authorization')
        error = 'invalid_token' if authorization else None
        challenge = [(b'www-authenticate', auth.challenge(error).encode('latin-1'))]
        if not await sync_to_async(mcp_enabled)():
            return await respond(send, 401, auth.error_body(_('The MCP server is turned off.'), error), challenge)
        if scope['method'] != 'POST':
            return await respond(send, 405, auth.error_body(_('Only POST is accepted.')), [(b'allow', b'POST')])
        raw_token = authorization[7:] if authorization and authorization[:7].lower() == 'bearer ' else ''
        token = await sync_to_async(auth.authenticate)(raw_token) if raw_token else None
        if token is None:
            return await respond(send, 401, auth.error_body(_('A valid access token is required.'), error), challenge)
        if self.application is None:
            raise RuntimeError('The MCP application has not started.')
        reset = auth.current_token.set(token)
        try:
            await self.application(scope, receive, no_store(send))
        finally:
            auth.current_token.reset(reset)


gateway = McpGateway()
