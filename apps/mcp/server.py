import json
from dataclasses import dataclass

from django.conf import settings
from django.utils.translation import gettext as _
from mcp.server.auth.settings import AuthSettings
from mcp.server.lowlevel.server import Server
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations
from pydantic import TypeAdapter, ValidationError

from apps.core.site import site_host
from apps.mcp.auth import ContextTokenVerifier, resource_url
from apps.mcp.errors import ToolRefusal, validation_text

MCP_PATH = '/mcp/'
MCP_PATHS = ('/mcp', MCP_PATH)
TOOLS = {}


@dataclass
class ToolSpec:
    name: str
    description: str
    function: object
    input_adapter: TypeAdapter
    input_schema: dict
    output_schema: dict
    annotations: ToolAnnotations

    def definition(self):
        return Tool(
            name=self.name, description=self.description,
            input_schema=self.input_schema, output_schema=self.output_schema, annotations=self.annotations,
        )


def tool(name, description, arguments, result, read_only=False, destructive=None, idempotent=None):
    def specify(function):
        return ToolSpec(
            name=name, description=description, function=function,
            input_adapter=TypeAdapter(arguments),
            input_schema=TypeAdapter(arguments).json_schema(),
            output_schema=TypeAdapter(result).json_schema(),
            annotations=ToolAnnotations(
                read_only_hint=read_only, destructive_hint=destructive, idempotent_hint=idempotent, open_world_hint=False,
            ),
        )
    return specify


def refused(text):
    return CallToolResult(content=[TextContent(text=text)], is_error=True)


async def on_list_tools(context, params):
    return ListToolsResult(tools=[spec.definition() for spec in TOOLS.values()])


async def on_call_tool(context, params):
    spec = TOOLS.get(params.name)
    if spec is None:
        return refused(_('Not found: tool %(name)s.') % {'name': params.name})
    try:
        arguments = spec.input_adapter.validate_python(params.arguments or {})
    except ValidationError as exc:
        return refused(validation_text(exc.errors()))
    try:
        result = await spec.function(arguments)
    except ToolRefusal as exc:
        return refused(str(exc))
    return CallToolResult(content=[TextContent(text=json.dumps(result))], structured_content=result)


def get_tool_input_schema(name):
    spec = TOOLS.get(name)
    return spec.input_schema if spec else None


def build_server():
    from apps.mcp import tools_read, tools_write
    TOOLS.update({spec.name: spec for spec in tools_read.TOOLS + tools_write.TOOLS})
    return Server(
        'ArcSpec',
        instructions=(
            'ArcSpec holds specifications as projects. A project has numbered sections, and each item is in one '
            'section. Before you create items in a project or move an item to another section, call get_project and '
            'list_sections for that project; call list_attributes and list_tags before you set attributes or tags. '
            'Put each item in the section whose description fits it, or whose title fits it when the section has no '
            'description, and write the item as that description asks. When no section fits, tell the user and do '
            'not choose one.'
        ),
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
        get_tool_input_schema=get_tool_input_schema,
    )


def build_application(server):
    return server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        stateless_http=True,
        max_request_body_size=settings.DATA_UPLOAD_MAX_MEMORY_SIZE,
        transport_security=TransportSecuritySettings(allowed_hosts=[site_host()], allowed_origins=[settings.SITE_URL]),
        auth=AuthSettings(
            issuer_url=settings.SITE_URL,
            resource_server_url=resource_url(),
            required_scopes=['read'],
            validate_token_resource=True,
        ),
        token_verifier=ContextTokenVerifier(),
    )
