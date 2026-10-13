import asyncio
import logging

import psycopg
from django.db import connection

logger = logging.getLogger(__name__)

CHANNEL = 'arcspec_notifications'
RESYNC = 'resync'
HEARTBEAT_SECONDS = 30
RECONNECT_MAX_SECONDS = 30


def notify(user_id, notification_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_notify(%s, %s)', [CHANNEL, f'{user_id}:{notification_id}'])


def conninfo():
    db = connection.settings_dict
    params = {
        'dbname': db['NAME'],
        'user': db['USER'],
        'password': db['PASSWORD'],
        'host': db['HOST'],
        'port': db['PORT'],
    }
    return psycopg.conninfo.make_conninfo(**{key: value for key, value in params.items() if value})


class NotificationBroker:

    def __init__(self):
        self._queues = {}
        self._task = None
        self.ready = asyncio.Event()

    def subscribe(self, user_id):
        queue = asyncio.Queue()
        self._queues.setdefault(user_id, set()).add(queue)
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._listen())
        return queue

    def unsubscribe(self, user_id, queue):
        queues = self._queues.get(user_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            del self._queues[user_id]

    def dispatch(self, payload):
        try:
            user_id, notification_id = (int(part) for part in payload.split(':'))
        except ValueError:
            logger.warning('ignoring notification payload %r', payload)
            return
        for queue in self._queues.get(user_id, ()):
            queue.put_nowait(notification_id)

    def resync_all(self):
        for queues in self._queues.values():
            for queue in queues:
                queue.put_nowait(RESYNC)

    async def stop(self):
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self.ready.clear()

    async def _listen(self):
        delay = 1
        connected_before = False
        while True:
            try:
                async with await psycopg.AsyncConnection.connect(conninfo(), autocommit=True) as conn:
                    await conn.execute(f'LISTEN {CHANNEL}')
                    logger.info('notification listener connected')
                    delay = 1
                    if connected_before:
                        self.resync_all()
                    connected_before = True
                    self.ready.set()
                    async for message in conn.notifies():
                        self.dispatch(message.payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.ready.clear()
                logger.exception('notification listener disconnected; retrying in %s s', delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX_SECONDS)


broker = NotificationBroker()
