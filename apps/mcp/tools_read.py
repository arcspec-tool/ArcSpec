from typing import TypedDict

from asgiref.sync import sync_to_async
from mcp.server.auth.middleware.auth_context import get_access_token

from apps.mcp import services
from apps.mcp.server import tool


class NoArguments(TypedDict):
    pass


class Account(TypedDict):
    name: str
    email: str
    system_role: str


def user_key():
    token = get_access_token()
    return token.subject if token else None


@tool('whoami', 'The connected account: its name, email address and system role.', NoArguments, Account, read_only=True)
async def whoami(arguments):
    return await sync_to_async(services.whoami)(user_key())


TOOLS = (whoami,)
