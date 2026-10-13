import re

import nh3
from django.utils.html import strip_tags

ALLOWED_TAGS = {
    "p", "br", "strong", "em", "u", "s", "ol", "ul", "li",
    "table", "thead", "tbody", "tr", "th", "td",
}
ALLOWED_ATTRS = {
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
}
BLOCK_BOUNDARY = re.compile(r"<(?:/?(?:p|ol|ul|li|table|thead|tbody|tr|th|td)\b[^>]*|br\b[^>]*)>", re.IGNORECASE)


def sanitize_rich_text(html):
    if not html:
        return html
    return nh3.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)


def plain_text(html):
    return " ".join(strip_tags(BLOCK_BOUNDARY.sub(" ", html or "")).split())
