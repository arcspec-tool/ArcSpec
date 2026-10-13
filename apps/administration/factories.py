import factory

from apps.administration.models import SystemSettings


class SystemSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SystemSettings
        django_get_or_create = ('pk',)

    pk = 1
