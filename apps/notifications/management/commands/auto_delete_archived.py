from django.core.management.base import BaseCommand

from apps.notifications.jobs import auto_delete_archived


class Command(BaseCommand):
    help = 'Delete projects archived for longer than auto_delete_days, when enabled in system settings'

    def handle(self, *args, **options):
        auto_delete_archived()
