from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.utils.translation import ngettext


def link_days():
    return max(settings.PASSWORD_RESET_TIMEOUT // 86400, 1)


def send_invitation_email(user, inviter, site_url, link_url, entra):
    days = link_days()
    context = {
        'user': user,
        'inviter': inviter,
        'site_url': site_url,
        'link_url': link_url,
        'entra': entra,
        'link_days': days,
    }
    lines = [
        _('Hi %(name)s,') % {'name': user.first_name or user.email},
        '',
        _('%(inviter)s invited you to ArcSpec.') % {'inviter': inviter},
        '',
    ]
    if link_url:
        lines += [
            ngettext(
                'Set your password with this link, valid for %(days)d day:',
                'Set your password with this link, valid for %(days)d days:',
                days,
            ) % {'days': days},
            link_url,
            '',
        ]
    if entra:
        lines += [_('Your Microsoft account for %(email)s signs in at %(site_url)s') % {'email': user.email, 'site_url': site_url}, '']
    if not link_url and not entra:
        lines += [_('Ask your administrator how to sign in.'), '']
    lines.append('ArcSpec')
    send_mail(
        subject=_('ArcSpec - Invitation'),
        message='\n'.join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=render_to_string('accounts/email/invitation.html', context),
    )


def send_password_link_email(user, link_url):
    days = link_days()
    context = {
        'user': user,
        'link_url': link_url,
        'link_days': days,
    }
    lines = [
        _('Hi %(name)s,') % {'name': user.first_name or user.email},
        '',
        ngettext(
            'Set a new password for your ArcSpec account with this link, valid for %(days)d day:',
            'Set a new password for your ArcSpec account with this link, valid for %(days)d days:',
            days,
        ) % {'days': days},
        link_url,
        '',
        _('If you did not ask for this, ignore this email. Your password stays as it is.'),
        '',
        'ArcSpec',
    ]
    send_mail(
        subject=_('ArcSpec - Set your password'),
        message='\n'.join(lines),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=render_to_string('accounts/email/password_link.html', context),
    )
