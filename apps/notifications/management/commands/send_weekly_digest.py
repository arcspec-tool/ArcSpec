from django.core.management.base import BaseCommand

from apps.notifications.jobs import send_weekly_digest


class Command(BaseCommand):
    help = 'Email the activity digest of the last 7 days to users who opted in'

    def handle(self, *args, **options):
        send_weekly_digest()
