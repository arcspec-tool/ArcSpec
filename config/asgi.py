import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')

django_application = get_asgi_application()

from apps.mcp.asgi import gateway
from apps.mcp.server import MCP_PATHS


async def application(scope, receive, send):
    if scope['type'] == 'lifespan':
        await gateway.lifespan(scope, receive, send)
    elif scope['type'] == 'http' and scope['path'] in MCP_PATHS:
        await gateway(scope, receive, send)
    else:
        await django_application(scope, receive, send)
