from typing import Annotated, Literal, NotRequired, TypedDict

from asgiref.sync import sync_to_async
from django.utils.translation import gettext as _
from mcp.server.auth.middleware.auth_context import get_access_token
from pydantic import Field

from apps.mcp import services
from apps.mcp.errors import ToolRefusal
from apps.mcp.server import tool
from apps.doctemplates.models import TemplateAttribute
from apps.mcp.tools_read import (
    AttachmentRow,
    DocType,
    ItemArguments,
    ItemDetail,
    ItemPriority,
    ItemStatus,
    ProjectSlug,
    TagReference,
    TemplateDetail,
)
from apps.projects.models import TraceabilityLink

LinkType = Literal[tuple(key for key, label in TraceabilityLink.LINK_TYPE_CHOICES)]
AttributeType = Literal[tuple(key for key, label in TemplateAttribute.FIELD_TYPE_CHOICES)]
ItemReference = Annotated[str, Field(description='An item id such as REQ-001, or an item key.')]
SectionReference = Annotated[str, Field(description='A section key or number such as 2.1.')]
TagValue = Annotated[str, Field(description='A tag key or name, as list_tags returns it.')]
AttributeValue = str | bool | int | float | list[str] | None
Attributes = Annotated[dict[str, AttributeValue], Field(
    description='Attribute name or key to value: true or false for a boolean, a list for a multi-select, '
                'the email address of a project member for a user attribute.',
)]
Markdown = Annotated[str, Field(
    min_length=1,
    description='Markdown: paragraphs, bold, italic, strikethrough, lists and tables. Headings, code, block quotes, '
                'rules, links and images stay as typed characters.',
)]
Email = Annotated[str, Field(description='The email address of a project member or a system administrator.')]


class ItemEntry(TypedDict):
    section: SectionReference
    text: Markdown
    status: NotRequired[ItemStatus]
    priority: NotRequired[ItemPriority]
    assignee: NotRequired[Email]
    tags: NotRequired[list[TagValue]]
    attributes: NotRequired[Attributes]
    before: NotRequired[Annotated[str, Field(description='Place the item before this item of the same section.')]]
    after: NotRequired[Annotated[str, Field(description='Place the item after this item of the same section.')]]


class CreateItemArguments(ItemEntry):
    project: ProjectSlug


class CreateItemsArguments(TypedDict):
    project: ProjectSlug
    items: Annotated[list[ItemEntry], Field(min_length=1, max_length=100, description='1 to 100 items.')]


class CreatedItem(TypedDict):
    item_id: str
    public_key: str


class CreatedItems(TypedDict):
    items: list[CreatedItem]


class UpdateItemArguments(TypedDict):
    project: ProjectSlug
    item: ItemReference
    text: NotRequired[Markdown]
    section: NotRequired[SectionReference]
    before: NotRequired[Annotated[str, Field(description='Move the item before this item of its section.')]]
    after: NotRequired[Annotated[str, Field(description='Move the item after this item of its section.')]]
    end: NotRequired[Annotated[bool, Field(description='Move the item to the end of its section.')]]
    status: NotRequired[ItemStatus]
    priority: NotRequired[ItemPriority]
    assignee: NotRequired[Annotated[str | None, Field(description='An email address, or null to clear.')]]
    attributes: NotRequired[Annotated[Attributes, Field(description='Merged into the stored values; null clears one.')]]


class SetItemTagsArguments(TypedDict):
    project: ProjectSlug
    item: ItemReference
    add: NotRequired[list[TagValue]]
    remove: NotRequired[list[TagValue]]


class ItemTags(TypedDict):
    tags: list[TagReference]


class AddCommentArguments(TypedDict):
    project: ProjectSlug
    item: ItemReference
    text: Annotated[str, Field(min_length=1, description='Plain text, stored without conversion; spaces at the start and end are removed.')]
    reply_to: NotRequired[Annotated[str, Field(description='The key of a comment on the same item.')]]


class AddedComment(TypedDict):
    public_key: str
    created_at: str


class AddLinkArguments(TypedDict):
    project: ProjectSlug
    item: ItemReference
    target_project: NotRequired[Annotated[str, Field(description='The slug of the target project; the same project by default.')]]
    target_item: ItemReference
    type: LinkType


class AddedLink(TypedDict):
    public_key: str


FileName = Annotated[str, Field(min_length=1, max_length=255, description='The file name with its extension, such as diagram.png.')]
FileData = Annotated[str, Field(
    min_length=1, json_schema_extra={'contentEncoding': 'base64'},
    description='The file content in base64. A request holds at most 2.5 MB, so the file can have about 1.9 MB.',
)]


class SetItemImageArguments(TypedDict):
    project: ProjectSlug
    item: ItemReference
    filename: FileName
    data: FileData
    caption: NotRequired[Annotated[str, Field(max_length=255, description='The image caption; the stored caption stays when not given.')]]


class AddAttachmentArguments(TypedDict):
    project: ProjectSlug
    item: ItemReference
    filename: FileName
    data: FileData


class RemoveAttachmentArguments(TypedDict):
    project: ProjectSlug
    item: ItemReference
    attachment: Annotated[str, Field(description='The attachment key, as get_item returns it.')]


class Attachments(TypedDict):
    attachments: list[AttachmentRow]


class TemplateSectionEntry(TypedDict):
    title: Annotated[str, Field(min_length=1, max_length=200)]
    description: NotRequired[Annotated[str, Field(description='What the section holds; projects show it to writers.')]]
    children: NotRequired[list['TemplateSectionEntry']]


class TemplateAttributeEntry(TypedDict):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    type: AttributeType
    options: NotRequired[Annotated[list[str], Field(
        description='The choices of a dropdown or multi-select attribute, at least one, none holding a comma; '
                    'no other type takes options.',
    )]]


TemplateName = Annotated[str, Field(min_length=1, max_length=150)]
TemplateDescription = Annotated[str, Field(description='What the template is for.')]
VisibleToAll = Annotated[bool, Field(description='Show the template to every user; otherwise only its owner and administrators see it.')]
TemplateSections = Annotated[list[TemplateSectionEntry], Field(
    description='The section tree in document order. Numbers follow the position in the tree: 1, 1.1, 1.2, 2.',
)]
TemplateAttributes = Annotated[list[TemplateAttributeEntry], Field(
    description='The custom attributes in order. Built-in attributes are kept and are not given here.',
)]


class CreateTemplateArguments(TypedDict):
    name: TemplateName
    doc_type: DocType
    description: NotRequired[TemplateDescription]
    visible_to_all: NotRequired[VisibleToAll]
    sections: NotRequired[TemplateSections]
    attributes: NotRequired[TemplateAttributes]


class UpdateTemplateArguments(TypedDict):
    template: Annotated[str, Field(description='The template key, as list_templates returns it.')]
    name: NotRequired[TemplateName]
    doc_type: NotRequired[DocType]
    description: NotRequired[TemplateDescription]
    visible_to_all: NotRequired[VisibleToAll]
    sections: NotRequired[Annotated[TemplateSections, Field(
        description='Replaces the whole section tree, in document order. Numbers follow the position in the tree: '
                    '1, 1.1, 1.2, 2.',
    )]]
    attributes: NotRequired[Annotated[TemplateAttributes, Field(
        description='Replaces the custom attributes, in order. Built-in attributes are kept and are not given here.',
    )]]


def write_tool(name, description, arguments, result, function, destructive, idempotent=None):
    async def run(validated):
        token = get_access_token()
        if token is None or 'write' not in token.scopes:
            raise ToolRefusal(_('This connection is read only.'))
        return await sync_to_async(function)(token.subject, **validated)
    return tool(name, description, arguments, result, destructive=destructive, idempotent=idempotent)(run)


TOOLS = (
    write_tool(
        'create_item',
        'Create one item in a section of a project, at the end of the section or before or after an item of it. '
        'Needs the Editor or Admin role and a project that is not archived.',
        CreateItemArguments, ItemDetail, services.create_item, destructive=False,
    ),
    write_tool(
        'create_items',
        'Create 1 to 100 items in one project in one call. Nothing is saved when one entry is refused; the error '
        'names the entry as items[<index>]. Members get one notification for the whole call.',
        CreateItemsArguments, CreatedItems, services.create_items, destructive=False,
    ),
    write_tool(
        'update_item',
        'Change an item: its text, section, place in the section, status, priority, assignee or attribute values. '
        'Only the fields given change.',
        UpdateItemArguments, ItemDetail, services.update_item, destructive=True, idempotent=True,
    ),
    write_tool(
        'set_item_tags',
        'Add tags to an item and remove tags from it in one call.',
        SetItemTagsArguments, ItemTags, services.set_item_tags, destructive=True, idempotent=True,
    ),
    write_tool(
        'add_comment',
        'Add a comment to an item, or a reply to a comment on it.',
        AddCommentArguments, AddedComment, services.add_comment, destructive=False,
    ),
    write_tool(
        'add_link',
        'Link an item to another item of this project or of another project the account can open.',
        AddLinkArguments, AddedLink, services.add_link, destructive=False,
    ),
    write_tool(
        'set_item_image',
        'Add an image to an item, or replace its image. PNG, JPG, GIF or WebP, at most 5 MB; the file content must '
        'be an image of the type its extension names.',
        SetItemImageArguments, ItemDetail, services.set_item_image, destructive=True, idempotent=True,
    ),
    write_tool(
        'remove_item_image', 'Remove the image and its caption from an item.',
        ItemArguments, ItemDetail, services.remove_item_image, destructive=True, idempotent=True,
    ),
    write_tool(
        'add_attachment',
        'Add a file to an item as an attachment. The extension must be one the project page accepts and the file '
        'content must match it; the size limit is set in the Admin Panel. To replace an attachment, add the new file '
        'and remove the old one.',
        AddAttachmentArguments, AttachmentRow, services.add_attachment, destructive=False,
    ),
    write_tool(
        'remove_attachment', 'Remove an attachment from an item and delete its file.',
        RemoveAttachmentArguments, Attachments, services.remove_attachment, destructive=True, idempotent=True,
    ),
    write_tool(
        'create_template',
        'Create a document template with its section tree and custom attributes. The connected account owns it. '
        'Needs a system role other than Viewer.',
        CreateTemplateArguments, TemplateDetail, services.create_template, destructive=False,
    ),
    write_tool(
        'update_template',
        'Change a template the connected account owns; an administrator can change any template that is not '
        'built-in. A built-in template cannot be changed. Only the fields given change: sections replaces the whole '
        'section tree and attributes replaces the custom attributes. Projects already made from the template keep '
        'their sections and attributes.',
        UpdateTemplateArguments, TemplateDetail, services.update_template, destructive=True, idempotent=True,
    ),
)
