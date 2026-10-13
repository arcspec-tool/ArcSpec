from django.core.management.base import BaseCommand

from apps.notifications.jobs import auto_archive_projects


class Command(BaseCommand):
    help = 'Archive active projects not updated for auto_archive_days, when enabled in system settings'

    def handle(self, *args, **options):
        auto_archive_projects()
