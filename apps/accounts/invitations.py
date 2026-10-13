from apps.accounts.auth_methods import current
from apps.accounts.emails import send_invitation_email
from apps.accounts.tokens import make_link
from apps.administration.models import SystemSettings


def send_invitation(request, user):
    stored = SystemSettings.load()
    methods = current(stored)
    send_invitation_email(
        user=user,
        inviter=request.user,
        site_url=request.build_absolute_uri('/'),
        link_url=make_link(request, user) if methods.password else None,
        entra=methods.entra,
    )
