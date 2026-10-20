from contextlib import contextmanager
from contextvars import ContextVar
from datetime import timedelta

from django.utils import timezone

EMAIL_LIMIT = 3
EMAIL_WINDOW = timedelta(minutes=15)

tool_write = ContextVar('mcp_tool_write', default=False)


@contextmanager
def writing():
    reset = tool_write.set(True)
    try:
        yield
    finally:
        tool_write.reset(reset)


def limit_email(sender, instance, raw=False, **kwargs):
    if raw or not tool_write.get() or not instance._state.adding or instance.actor_id is None:
        return
    recent = sender.objects.filter(
        user_id=instance.user_id,
        actor_id=instance.actor_id,
        project_id=instance.project_id,
        created_at__gte=timezone.now() - EMAIL_WINDOW,
    ).count()
    if recent >= EMAIL_LIMIT:
        instance._skip_email = True
