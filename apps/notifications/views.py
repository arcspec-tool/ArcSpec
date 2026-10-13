import asyncio
import json
from datetime import timedelta

from asgiref.sync import sync_to_async
from django.db import OperationalError, connection
from django.http import HttpResponseForbidden, StreamingHttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.notifications import stream
from apps.notifications.models import Notification
from apps.notifications.push import notification_payload

REPLAY_WINDOW = timedelta(minutes=2)
REPLAY_LIMIT = 20


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, public_key):
        try:
            notification = Notification.objects.get(public_key=public_key, user=request.user)
        except Notification.DoesNotExist:
            return Response({'error': _('Not found')}, status=404)

        notification.is_read = True
        notification.save(update_fields=['is_read'])

        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'status': 'ok', 'unread_count': unread_count})


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'status': 'ok', 'unread_count': 0})


def _event(notification, unread_count):
    payload = notification_payload(notification)
    payload['unread_count'] = unread_count
    return f'data: {json.dumps(payload)}\n\n'


async def _reset_connection():
    await sync_to_async(lambda: connection.close())()


async def _retrying(operation, *args):
    try:
        return await operation(*args)
    except OperationalError:
        await _reset_connection()
        return await operation(*args)


async def _fetch_unpushed(user_id):
    cutoff = timezone.now() - REPLAY_WINDOW
    unpushed = Notification.objects.filter(
        user_id=user_id,
        is_read=False,
        pushed_at__isnull=True,
        created_at__gte=cutoff,
    ).order_by('created_at')[:REPLAY_LIMIT]
    return [notification async for notification in unpushed]


async def _fetch_one(notification_id, user_id):
    return await Notification.objects.filter(pk=notification_id, user_id=user_id).afirst()


async def _mark_pushed(ids):
    await Notification.objects.filter(pk__in=ids).aupdate(pushed_at=timezone.now())


async def _unread_count(user_id):
    return await Notification.objects.filter(user_id=user_id, is_read=False).acount()


async def _is_active(user_id):
    return await User.objects.filter(pk=user_id, is_active=True).aexists()


async def _replay(user_id):
    notifications = await _retrying(_fetch_unpushed, user_id)
    if not notifications:
        return
    await _retrying(_mark_pushed, [notification.pk for notification in notifications])
    unread_count = await _retrying(_unread_count, user_id)
    for notification in notifications:
        yield _event(notification, unread_count)


async def events(user_id, broker, heartbeat_seconds):
    queue = broker.subscribe(user_id)
    try:
        yield 'event: ready\ndata: {}\n\n'
        async for event in _replay(user_id):
            yield event
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except TimeoutError:
                item = None
            if not await _retrying(_is_active, user_id):
                return
            if item is None:
                yield ': ping\n\n'
                continue
            if item == stream.RESYNC:
                async for event in _replay(user_id):
                    yield event
                continue
            notification = await _retrying(_fetch_one, item, user_id)
            if notification is None:
                continue
            await _retrying(_mark_pushed, [item])
            yield _event(notification, await _retrying(_unread_count, user_id))
    finally:
        broker.unsubscribe(user_id, queue)


@require_GET
async def notification_stream(request):
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponseForbidden()
    response = StreamingHttpResponse(
        events(user.pk, stream.broker, stream.HEARTBEAT_SECONDS),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
