import secrets

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = 'Create the first system administrator with a generated password, printed once; refused once any account exists'

    def add_arguments(self, parser):
        parser.add_argument('email')

    def handle(self, *args, **options):
        if User.objects.exists():
            raise CommandError('create_admin runs only on a new installation. Invite administrators from the Admin Panel.')
        password = secrets.token_urlsafe(18)
        user = User.objects.create_superuser(options['email'], password)
        self.stdout.write(f'Administrator created: {user.email}')
        self.stdout.write(f'Password: {password}')
        self.stdout.write('Sign in with it and change it on the Settings page.')
