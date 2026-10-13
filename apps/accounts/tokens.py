from django.contrib.auth.tokens import default_token_generator
from django.urls import reverse

from apps.accounts.models import User


def make_link(request, user):
    return request.build_absolute_uri(reverse('set_password', kwargs={
        'public_key': user.public_key,
        'token': default_token_generator.make_token(user),
    }))


def user_from_link(public_key, token):
    user = User.objects.filter(public_key=public_key, is_active=True).first()
    if user is not None and default_token_generator.check_token(user, token):
        return user
    return None
