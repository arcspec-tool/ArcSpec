import logging
from contextlib import contextmanager

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import Http404
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


class ToolRefusal(Exception):
    pass


def validation_text(errors, prefix=''):
    parts = []
    for error in errors:
        location = '.'.join(str(part) for part in error.get('loc', ()))
        parts.append(f'{prefix}{location}: {error["msg"]}' if location else error['msg'])
    return '; '.join(parts)


def message_text(exc, prefix=''):
    if hasattr(exc, 'error_dict'):
        return '; '.join(
            f'{prefix}{field}: {message}' for field, messages in exc.message_dict.items() for message in messages
        )
    return '; '.join(exc.messages)


def refusal_text(exc, what=''):
    if isinstance(exc, Http404):
        return _('Not found: %(what)s.') % {'what': what}
    if isinstance(exc, PermissionDenied):
        return str(exc) if exc.args else _('Your role in this project does not allow this.')
    if isinstance(exc, ValidationError):
        return message_text(exc)
    if isinstance(exc, IntegrityError):
        logger.exception('A write was refused by a database constraint.')
        return _('A conflicting change was saved at the same time. Nothing was saved.')
    raise exc


@contextmanager
def refusing(what=''):
    try:
        yield
    except (Http404, PermissionDenied, ValidationError, IntegrityError) as exc:
        raise ToolRefusal(refusal_text(exc, what)) from None
