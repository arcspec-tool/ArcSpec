from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from markdown_it import MarkdownIt

from apps.projects.sanitize import plain_text, sanitize_rich_text

DISABLED_RULES = [
    'heading', 'lheading', 'code', 'fence', 'blockquote', 'hr', 'backticks', 'link', 'image', 'autolink', 'reference',
]

parser = MarkdownIt('commonmark', {'html': False}).enable(['table', 'strikethrough']).disable(DISABLED_RULES)


def item_html(markdown):
    html = sanitize_rich_text(parser.render(markdown))
    if not plain_text(html):
        raise ValidationError({'text': _('The text is empty after conversion.')})
    return html
