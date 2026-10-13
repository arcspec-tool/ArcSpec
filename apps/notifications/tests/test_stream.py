import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from asgiref.sync import sync_to_async
from django.core import mail
from django.db import OperationalError
from django.test import AsyncClient, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.accounts.factories import UserFactory
from apps.accounts.models import User
from apps.notifications import stream
from apps.notifications.factories import NotificationFactory
from apps.notifications.models import Notification
from apps.notifications.push import push_notification
from apps.notifications.stream import RESYNC, NotificationBroker, notify
from apps.notifications.views import events

STREAM_URL = '/api/notifications/stream/'
READY = 'event: ready\ndata: {}\n\n'
PING = ': ping\n\n'


class FakeBroker:

    def __init__(self):
        self.queue = asyncio.Queue()
        self.unsubscribed = []

    def subscribe(self, user_id):
        return self.queue

    def unsubscribe(self, user_id, queue):
        self.unsubscribed.append((user_id, queue))


async def _idle(self):
    await asyncio.Event().wait()


async def _next(generator):
    return await asyncio.wait_for(generator.__anext__(), 5)


class BrokerTest(SimpleTestCase):

    def setUp(self):
        patcher = patch.object(NotificationBroker, '_listen', _idle)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_dispatch_reaches_only_the_named_users_queues(self):
        broker = NotificationBroker()
        first = broker.subscribe(7)
        second = broker.subscribe(7)
        other = broker.subscribe(8)
        broker.dispatch('7:12')
        await broker.stop()
        self.assertEqual(first.get_nowait(), 12)
        self.assertEqual(second.get_nowait(), 12)
        self.assertTrue(other.empty())

    async def test_dispatch_ignores_a_malformed_payload(self):
        broker = NotificationBroker()
        queue = broker.subscribe(7)
        with self.assertLogs('apps.notifications.stream', 'WARNING'):
            broker.dispatch('nonsense')
        await broker.stop()
        self.assertTrue(queue.empty())

    async def test_unsubscribed_queue_receives_nothing(self):
        broker = NotificationBroker()
        queue = broker.subscribe(7)
        broker.unsubscribe(7, queue)
        broker.dispatch('7:12')
        await broker.stop()
        self.assertTrue(queue.empty())

    async def test_resync_all_marks_every_queue(self):
        broker = NotificationBroker()
        first = broker.subscribe(7)
        other = broker.subscribe(8)
        broker.resync_all()
        await broker.stop()
        self.assertEqual(first.get_nowait(), RESYNC)
        self.assertEqual(other.get_nowait(), RESYNC)


class ListenerTest(TransactionTestCase):

    async def test_notify_reaches_the_subscribed_queue(self):
        broker = NotificationBroker()
        queue = broker.subscribe(3)
        try:
            await asyncio.wait_for(broker.ready.wait(), 10)
            await sync_to_async(notify)(3, 9)
            self.assertEqual(await asyncio.wait_for(queue.get(), 10), 9)
        finally:
            await broker.stop()


class EventsGeneratorTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory()

    async def test_sends_ready_then_replays_unpushed_notifications(self):
        notification = await sync_to_async(NotificationFactory)(user=self.user, message='Replayed')
        broker = FakeBroker()
        generator = events(self.user.pk, broker, 30)
        try:
            first = await _next(generator)
            second = await _next(generator)
        finally:
            await generator.aclose()
        self.assertEqual(first, READY)
        self.assertTrue(second.startswith('data: '))
        self.assertIn('"Replayed"', second)
        self.assertIn(f'"id": {notification.pk}', second)
        self.assertIn('"unread_count": 1', second)
        await notification.arefresh_from_db()
        self.assertIsNotNone(notification.pushed_at)

    async def test_a_replayed_event_carries_the_unread_count_the_page_already_shows(self):
        await sync_to_async(NotificationFactory)(user=self.user, pushed_at=timezone.now())
        await sync_to_async(NotificationFactory)(user=self.user, is_read=True)
        await sync_to_async(NotificationFactory)(user=self.user, message='Replayed')
        generator = events(self.user.pk, FakeBroker(), 30)
        try:
            await _next(generator)
            chunk = await _next(generator)
        finally:
            await generator.aclose()
        self.assertIn('"Replayed"', chunk)
        self.assertIn('"unread_count": 2', chunk)

    async def test_does_not_replay_old_or_read_or_pushed_notifications(self):
        old = await sync_to_async(NotificationFactory)(user=self.user)
        await Notification.objects.filter(pk=old.pk).aupdate(created_at=timezone.now() - timedelta(minutes=3))
        await sync_to_async(NotificationFactory)(user=self.user, is_read=True)
        await sync_to_async(NotificationFactory)(user=self.user, pushed_at=timezone.now())
        generator = events(self.user.pk, FakeBroker(), 0.05)
        try:
            await _next(generator)
            second = await _next(generator)
        finally:
            await generator.aclose()
        self.assertEqual(second, PING)

    async def test_delivers_a_queued_notification_and_marks_it_pushed(self):
        broker = FakeBroker()
        generator = events(self.user.pk, broker, 30)
        try:
            await _next(generator)
            notification = await sync_to_async(NotificationFactory)(user=self.user, message='Queued')
            broker.queue.put_nowait(notification.pk)
            chunk = await _next(generator)
        finally:
            await generator.aclose()
        self.assertIn('"Queued"', chunk)
        self.assertIn('"unread_count": 1', chunk)
        await notification.arefresh_from_db()
        self.assertIsNotNone(notification.pushed_at)

    async def test_ignores_a_queued_notification_of_another_user(self):
        other = await sync_to_async(NotificationFactory)()
        broker = FakeBroker()
        generator = events(self.user.pk, broker, 0.05)
        try:
            await _next(generator)
            broker.queue.put_nowait(other.pk)
            chunk = await _next(generator)
        finally:
            await generator.aclose()
        self.assertEqual(chunk, PING)
        await other.arefresh_from_db()
        self.assertIsNone(other.pushed_at)

    async def test_resync_replays_what_arrived_meanwhile(self):
        broker = FakeBroker()
        generator = events(self.user.pk, broker, 30)
        try:
            await _next(generator)
            notification = await sync_to_async(NotificationFactory)(user=self.user, message='Missed')
            broker.queue.put_nowait(RESYNC)
            chunk = await _next(generator)
        finally:
            await generator.aclose()
        self.assertIn('"Missed"', chunk)
        await notification.arefresh_from_db()
        self.assertIsNotNone(notification.pushed_at)

    async def test_sends_a_heartbeat_when_idle(self):
        generator = events(self.user.pk, FakeBroker(), 0.05)
        try:
            await _next(generator)
            chunk = await _next(generator)
        finally:
            await generator.aclose()
        self.assertEqual(chunk, PING)

    async def test_ends_without_delivering_once_the_user_is_deactivated(self):
        broker = FakeBroker()
        generator = events(self.user.pk, broker, 0.05)
        try:
            await _next(generator)
            self.assertEqual(await _next(generator), PING)
            await User.objects.filter(pk=self.user.pk).aupdate(is_active=False)
            notification = await sync_to_async(NotificationFactory)(user=self.user)
            broker.queue.put_nowait(notification.pk)
            with self.assertRaises(StopAsyncIteration):
                await _next(generator)
        finally:
            await generator.aclose()
        await notification.arefresh_from_db()
        self.assertIsNone(notification.pushed_at)
        self.assertEqual(broker.unsubscribed, [(self.user.pk, broker.queue)])

    async def test_closing_unsubscribes(self):
        broker = FakeBroker()
        generator = events(self.user.pk, broker, 30)
        await _next(generator)
        await generator.aclose()
        self.assertEqual(broker.unsubscribed, [(self.user.pk, broker.queue)])

    async def test_a_dead_database_connection_is_reset_and_the_query_retried(self):
        fetch = AsyncMock(side_effect=[OperationalError('server closed the connection'), []])
        reset = AsyncMock()
        generator = events(self.user.pk, FakeBroker(), 0.05)
        with patch('apps.notifications.views._fetch_unpushed', fetch), \
                patch('apps.notifications.views._reset_connection', reset):
            try:
                first = await _next(generator)
                second = await _next(generator)
            finally:
                await generator.aclose()
        self.assertEqual(first, READY)
        self.assertEqual(second, PING)
        self.assertEqual(fetch.await_count, 2)
        reset.assert_awaited_once_with()


class StreamViewTest(TestCase):

    async def test_anonymous_is_refused(self):
        response = await AsyncClient().get(STREAM_URL)
        self.assertEqual(response.status_code, 403)

    async def test_post_is_refused(self):
        client = AsyncClient()
        await client.aforce_login(await sync_to_async(UserFactory)())
        response = await client.post(STREAM_URL)
        self.assertEqual(response.status_code, 405)

    async def test_authenticated_user_gets_an_event_stream(self):
        client = AsyncClient()
        await client.aforce_login(await sync_to_async(UserFactory)())
        with patch.object(stream, 'broker', FakeBroker()):
            response = await client.get(STREAM_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/event-stream')
        self.assertEqual(response['Cache-Control'], 'no-cache')
        self.assertTrue(response.streaming)


@override_settings(DEFAULT_FROM_EMAIL='noreply@arcspec.test')
class PushNotificationTest(TestCase):

    def test_notifies_after_commit_and_sends_the_email(self):
        user = UserFactory()
        notification = NotificationFactory(user=user, type='comment', message='Hello')
        with patch('apps.notifications.push.notify') as notify_mock, self.captureOnCommitCallbacks(execute=True):
            push_notification(notification)
        notify_mock.assert_called_once_with(user.pk, notification.pk)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])

    def test_does_nothing_when_the_actor_is_the_recipient(self):
        user = UserFactory()
        notification = NotificationFactory(user=user, actor=user, type='comment', message='Hello')
        with patch('apps.notifications.push.notify') as notify_mock, self.captureOnCommitCallbacks(execute=True):
            push_notification(notification)
        notify_mock.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)
