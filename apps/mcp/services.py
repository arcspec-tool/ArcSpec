from django.utils.translation import gettext as _

from apps.accounts.models import User
from apps.mcp.errors import ToolRefusal


def load_user(user_key):
    try:
        return User.objects.get(public_key=user_key, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        raise ToolRefusal(_('Not found: your account.'))


def whoami(user_key):
    user = load_user(user_key)
    return {'name': str(user), 'email': user.email, 'system_role': user.system_role}
