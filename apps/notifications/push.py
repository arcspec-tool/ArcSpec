from django.db import transaction

from apps.notifications.jobs import send_email_notification
from apps.notifications.stream import notify


def notification_payload(notification):
    return {
        'id': notification.pk,
        'public_key': str(notification.public_key),
        'type': notification.type,
        'message': notification.message,
        'link': notification.link,
        'created_at': notification.created_at.isoformat(),
    }


def push_notification(notification):
    if notification.actor_id and notification.actor_id == notification.user_id:
        return

    transaction.on_commit(lambda: notify(notification.user_id, notification.pk))
    send_email_notification(notification)
