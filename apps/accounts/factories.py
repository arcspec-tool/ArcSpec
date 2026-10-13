import factory
from django.contrib.auth import get_user_model

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f'user{n}@example.com')
    first_name = factory.Faker('first_name')
    last_name = factory.Faker('last_name')
    system_role = 'user'
    is_active = True
    avatar_color = '#284E8A'


class AdminUserFactory(UserFactory):
    system_role = 'admin'


class ViewerUserFactory(UserFactory):
    system_role = 'viewer'


class UserSettingsFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = 'accounts.UserSettings'
        django_get_or_create = ('user',)

    user = factory.SubFactory(UserFactory)
