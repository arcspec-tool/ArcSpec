import factory

from apps.accounts.factories import UserFactory
from apps.notifications.models import AuditLog, Notification
from apps.projects.factories import ProjectFactory


class AuditLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AuditLog

    project = factory.SubFactory(ProjectFactory)
    user = factory.SubFactory(UserFactory)
    action = 'created'
    target_type = 'Item'
    target_id = 'REQ-001'


class NotificationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    type = 'comment'
    message = factory.Faker('sentence')
