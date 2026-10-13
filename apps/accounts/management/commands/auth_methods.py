from django.core.management.base import BaseCommand, CommandError

from apps.accounts.auth_methods import entra_configured, validate
from apps.administration.models import SystemSettings

SWITCH = {'on': True, 'off': False}


class Command(BaseCommand):
    help = 'Print the sign-in method switches, or set them with --entra and --password'

    def add_arguments(self, parser):
        parser.add_argument('--entra', choices=SWITCH, help='Microsoft sign-in')
        parser.add_argument('--password', choices=SWITCH, help='password sign-in')

    def handle(self, *args, **options):
        stored = SystemSettings.load()
        if options['entra'] or options['password']:
            entra = SWITCH[options['entra']] if options['entra'] else stored.entra_login_enabled
            password = SWITCH[options['password']] if options['password'] else stored.password_login_enabled
            errors = validate(entra, password)
            if errors:
                raise CommandError('\n'.join(errors))
            stored.entra_login_enabled = entra
            stored.password_login_enabled = password
            stored.save(update_fields=['entra_login_enabled', 'password_login_enabled'])
        self.stdout.write(f'entra: {"on" if stored.entra_login_enabled else "off"}')
        self.stdout.write(f'password: {"on" if stored.password_login_enabled else "off"}')
        self.stdout.write(f'entra configured: {"yes" if entra_configured() else "no"}')
