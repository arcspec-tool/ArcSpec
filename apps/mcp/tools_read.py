from typing import Annotated, Literal, NotRequired, TypedDict

from asgiref.sync import sync_to_async
from mcp.server.auth.middleware.auth_context import get_access_token
from pydantic import Field

from apps.doctemplates.models import Template
from apps.mcp import services
from apps.mcp.server import tool
from apps.notifications.models import AuditLog
from apps.projects.models import Item, Project
from apps.projects.queries import AUDIT_ACTION_GROUPS

ProjectStatus = Literal[tuple(key for key, label in Project.STATUS_CHOICES)]
ItemStatus = Literal[tuple(key for key, label in Item.STATUS_CHOICES)]
ItemPriority = Literal[tuple(key for key, label in Item.PRIORITY_CHOICES)]
DocType = Literal[tuple(key for key, label in Template.DOC_TYPE_CHOICES)]
AuditAction = Literal[tuple(AUDIT_ACTION_GROUPS) + tuple(key for key, label in AuditLog.ACTION_CHOICES)]

ProjectSlug = Annotated[str, Field(description='The project slug, as list_projects returns it.')]
Offset = Annotated[int, Field(description='Rows to skip; 0 by default.')]
Limit = Annotated[int, Field(description='Rows per page; the default and the maximum are in the tool description.')]


class NoArguments(TypedDict):
    pass


class Account(TypedDict):
    name: str
    email: str
    system_role: str


class Person(TypedDict):
    name: str
    email: str


class ListProjectsArguments(TypedDict):
    status: NotRequired[ProjectStatus]
    q: NotRequired[Annotated[str, Field(description='A text to find in the project name or description.')]]
    offset: NotRequired[Offset]
    limit: NotRequired[Limit]


class ProjectRow(TypedDict):
    slug: str
    name: str
    description: str
    status: str
    template: str
    role: str
    item_count: int
    member_count: int
    updated_at: str


class ProjectList(TypedDict):
    projects: list[ProjectRow]
    has_more: bool


class ProjectArguments(TypedDict):
    project: ProjectSlug


class TemplateReference(TypedDict):
    public_key: str
    name: str
    doc_type: str
    item_prefix: str


class Member(TypedDict):
    name: str
    email: str
    role: str


class ProjectDetail(TypedDict):
    slug: str
    name: str
    description: str
    status: str
    template: TemplateReference
    members: list[Member]
    role: str
    can_write: bool
    created_at: str
    updated_at: str


class SectionNode(TypedDict):
    public_key: str
    number: str
    title: str
    description: str
    item_count: int
    total_items: int
    children: list['SectionNode']


class SectionList(TypedDict):
    sections: list[SectionNode]


class ListItemsArguments(TypedDict):
    project: ProjectSlug
    section: NotRequired[Annotated[str, Field(description='A section key or number such as 2.1; its own items, not its subsections.')]]
    status: NotRequired[ItemStatus]
    priority: NotRequired[ItemPriority]
    tag: NotRequired[Annotated[str, Field(description='A tag key or name.')]]
    assignee: NotRequired[Annotated[str, Field(description='The email address of the assignee.')]]
    text: NotRequired[Annotated[str, Field(min_length=2, description='A text to find in the item id or text, at least 2 characters.')]]
    offset: NotRequired[Offset]
    limit: NotRequired[Limit]


class AttributeValue(TypedDict):
    name: str
    value: str


class ItemRow(TypedDict):
    item_id: str
    public_key: str
    section: str
    text: str
    status: str
    priority: str
    assignee: Person | None
    tags: list[str]
    attributes: list[AttributeValue]


class ItemList(TypedDict):
    items: list[ItemRow]
    has_more: bool


class ItemArguments(TypedDict):
    project: ProjectSlug
    item: Annotated[str, Field(description='The item id such as REQ-001, or the item key.')]


class SectionReference(TypedDict):
    public_key: str
    number: str
    title: str


class TagReference(TypedDict):
    public_key: str
    name: str


class TypedAttributeValue(TypedDict):
    name: str
    type: str
    value: str


class AttachmentRow(TypedDict):
    filename: str
    size: int


class CommentRow(TypedDict):
    public_key: str
    author: str
    text: str
    created_at: str
    reply_to: str | None


class LinkRow(TypedDict):
    public_key: str
    type: str
    item_id: str
    project_name: str
    project_slug: str | None
    item_key: str | None


class ItemDetail(TypedDict):
    item_id: str
    public_key: str
    section: SectionReference
    text: str
    status: str
    priority: str
    assignee: Person | None
    tags: list[TagReference]
    attributes: list[TypedAttributeValue]
    image_caption: str
    has_image: bool
    attachments: list[AttachmentRow]
    comments: list[CommentRow]
    outgoing_links: list[LinkRow]
    incoming_links: list[LinkRow]
    created_by: str
    created_at: str
    updated_at: str


class TagRow(TypedDict):
    public_key: str
    name: str
    preset: bool


class TagList(TypedDict):
    tags: list[TagRow]


class AttributeRow(TypedDict):
    public_key: str
    name: str
    type: str
    options: list[str]
    builtin: bool


class AttributeList(TypedDict):
    attributes: list[AttributeRow]


class PagedProjectArguments(TypedDict):
    project: ProjectSlug
    offset: NotRequired[Offset]
    limit: NotRequired[Limit]


class VersionRow(TypedDict):
    public_key: str
    version: str
    changed_by: str
    changed_at: str
    summary: str
    item_count: int


class VersionList(TypedDict):
    versions: list[VersionRow]
    has_more: bool


class ListAuditLogArguments(TypedDict):
    project: ProjectSlug
    action: NotRequired[Annotated[AuditAction, Field(description='One action, or the collaboration group.')]]
    user: NotRequired[Annotated[str, Field(description='The email address of the user who acted.')]]
    item: NotRequired[Annotated[str, Field(description='An item id such as REQ-001.')]]
    offset: NotRequired[Offset]
    limit: NotRequired[Limit]


class AuditEntry(TypedDict):
    action: str
    target_type: str
    target_id: str
    user: str
    details: dict
    created_at: str


class AuditList(TypedDict):
    entries: list[AuditEntry]
    has_more: bool


class ListTemplatesArguments(TypedDict):
    q: NotRequired[Annotated[str, Field(description='A text to find in the template name.')]]
    doc_type: NotRequired[DocType]


class TemplateRow(TypedDict):
    public_key: str
    name: str
    doc_type: str
    description: str
    builtin: bool
    section_count: int
    attribute_count: int


class TemplateList(TypedDict):
    templates: list[TemplateRow]


class TemplateArguments(TypedDict):
    template: Annotated[str, Field(description='The template key, as list_templates returns it.')]


class TemplateSectionNode(TypedDict):
    number: str
    title: str
    description: str
    children: list['TemplateSectionNode']


class TemplateAttributeRow(TypedDict):
    name: str
    type: str
    options: list[str]


class TemplateDetail(TypedDict):
    public_key: str
    name: str
    doc_type: str
    description: str
    builtin: bool
    sections: list[TemplateSectionNode]
    attributes: list[TemplateAttributeRow]


class SearchArguments(TypedDict):
    q: Annotated[str, Field(min_length=2, description='The text to search for, at least 2 characters.')]


class SearchProject(TypedDict):
    slug: str
    name: str
    status: str


class SearchItem(TypedDict):
    project: str
    item_id: str
    public_key: str
    status: str
    section: str
    text: str


class SearchResult(TypedDict):
    projects: list[SearchProject]
    items: list[SearchItem]


def user_key():
    token = get_access_token()
    return token.subject if token else None


def read_tool(name, description, arguments, result, function):
    async def run(validated):
        return await sync_to_async(function)(user_key(), **validated)
    return tool(name, description, arguments, result, read_only=True)(run)


TOOLS = (
    read_tool(
        'whoami', 'The connected account: its name, email address and system role.',
        NoArguments, Account, services.whoami,
    ),
    read_tool(
        'list_projects',
        'The projects the connected account can open, with its role in each, last changed first. '
        'Filter by status or by a text in the name or description. '
        'Paged with offset and limit (50 by default, at most 100); has_more says whether rows follow.',
        ListProjectsArguments, ProjectList, services.list_projects,
    ),
    read_tool(
        'get_project',
        'One project by its slug: its template, members, the connected account\'s role and whether it may write.',
        ProjectArguments, ProjectDetail, services.get_project,
    ),
    read_tool(
        'list_sections',
        'The section tree of a project. item_count counts the section\'s own items; total_items includes its subsections.',
        ProjectArguments, SectionList, services.list_sections,
    ),
    read_tool(
        'list_items',
        'The items of a project in document order, with section number, status, priority, assignee, tag names and '
        'attribute values. Filter by section, status, priority, tag, assignee or a text. '
        'Paged with offset and limit (50 by default, at most 100); has_more says whether rows follow.',
        ListItemsArguments, ItemList, services.list_items,
    ),
    read_tool(
        'get_item',
        'One item of a project: its text as stored HTML, tags, attribute values, attachments, comments and the links '
        'to and from other items. A linked item in a project the account cannot open carries only the project name '
        'and the item id.',
        ItemArguments, ItemDetail, services.get_item,
    ),
    read_tool(
        'list_tags', 'The tags available in a project: the site-wide presets and the project\'s own tags.',
        ProjectArguments, TagList, services.list_tags,
    ),
    read_tool(
        'list_attributes',
        'The attributes of a project with their types and options. A built-in attribute cannot be set.',
        ProjectArguments, AttributeList, services.list_attributes,
    ),
    read_tool(
        'list_versions',
        'The versions of a project, newest first: who changed it, when and a summary. '
        'Paged with offset and limit (20 by default, at most 50); has_more says whether rows follow.',
        PagedProjectArguments, VersionList, services.list_versions,
    ),
    read_tool(
        'list_audit_log',
        'The audit log of a project, newest first. Filter by action, by the acting user\'s email address or by an '
        'item id. Paged with offset and limit (50 by default, at most 100); has_more says whether rows follow.',
        ListAuditLogArguments, AuditList, services.list_audit_log,
    ),
    read_tool(
        'list_templates',
        'The document templates the connected account can use. Filter by a text in the name or by document type.',
        ListTemplatesArguments, TemplateList, services.list_templates,
    ),
    read_tool(
        'get_template', 'One template by its key: its section tree and its attributes.',
        TemplateArguments, TemplateDetail, services.get_template,
    ),
    read_tool(
        'search',
        'Search the projects the connected account can open: up to 5 projects by name or description and up to 10 '
        'items by item id or text, each with the first 100 characters of its text.',
        SearchArguments, SearchResult, services.search,
    ),
)
