import os
import tempfile

import magic
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

ANY_TEXT = 'text/'
MAX_IMAGE_SIZE = 5 * 1024 * 1024

IMAGE_TYPES = {
    '.png': ('image/png',),
    '.jpg': ('image/jpeg',),
    '.jpeg': ('image/jpeg',),
    '.gif': ('image/gif',),
    '.webp': ('image/webp',),
}

ATTACHMENT_TYPES = {
    '.pdf': ('application/pdf',),
    '.doc': ('application/msword',),
    '.docx': ('application/vnd.openxmlformats-officedocument.wordprocessingml.document',),
    '.xls': ('application/vnd.ms-excel',),
    '.xlsx': ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',),
    '.ppt': ('application/vnd.ms-powerpoint',),
    '.pptx': ('application/vnd.openxmlformats-officedocument.presentationml.presentation',),
    '.odt': ('application/vnd.oasis.opendocument.text',),
    '.ods': ('application/vnd.oasis.opendocument.spreadsheet',),
    '.odp': ('application/vnd.oasis.opendocument.presentation',),
    '.rtf': ('text/rtf',),
    '.txt': (ANY_TEXT,),
    '.csv': (ANY_TEXT,),
    '.md': (ANY_TEXT,),
    '.xml': (ANY_TEXT,),
    '.yaml': (ANY_TEXT,),
    '.yml': (ANY_TEXT,),
    '.json': ('application/json', ANY_TEXT),
    '.png': ('image/png',),
    '.jpg': ('image/jpeg',),
    '.jpeg': ('image/jpeg',),
    '.gif': ('image/gif',),
    '.bmp': ('image/bmp',),
    '.webp': ('image/webp',),
    '.zip': ('application/zip',),
    '.rar': ('application/vnd.rar',),
    '.7z': ('application/x-7z-compressed',),
    '.tar': ('application/x-tar',),
    '.gz': ('application/gzip',),
}


def extension(name):
    return os.path.splitext(name)[1].lower()


def detected_type(uploaded):
    if hasattr(uploaded, 'temporary_file_path'):
        return magic.from_file(uploaded.temporary_file_path(), mime=True)
    with tempfile.NamedTemporaryFile() as copy:
        for chunk in uploaded.chunks():
            copy.write(chunk)
        copy.flush()
        return magic.from_file(copy.name, mime=True)


def check_content(uploaded, allowed):
    detected = detected_type(uploaded)
    uploaded.seek(0)
    if not any(detected == kind or (kind.endswith('/') and detected.startswith(kind)) for kind in allowed):
        raise ValidationError(_('The content of the file is %(type)s, which does not match %(ext)s.') % {
            'type': detected, 'ext': extension(uploaded.name),
        })


def check_image(uploaded):
    ext = extension(uploaded.name)
    if ext not in IMAGE_TYPES:
        raise ValidationError(_('Image type "%(ext)s" is not allowed. Use PNG, JPG, GIF, or WebP.') % {'ext': ext})
    if uploaded.size > MAX_IMAGE_SIZE:
        raise ValidationError(_('Image size exceeds 5 MB limit.'))
    forms.ImageField().to_python(uploaded)
    check_content(uploaded, IMAGE_TYPES[ext])
    return uploaded


def check_attachment(uploaded):
    from apps.administration.models import SystemSettings
    ext = extension(uploaded.name)
    if ext not in ATTACHMENT_TYPES:
        raise ValidationError(_('File type "%(ext)s" is not allowed.') % {'ext': ext})
    limit = SystemSettings.load().max_attachment_size_mb
    if uploaded.size > limit * 1024 * 1024:
        raise ValidationError(_('File size exceeds the %(size)s MB limit.') % {'size': limit})
    check_content(uploaded, ATTACHMENT_TYPES[ext])
    return uploaded
