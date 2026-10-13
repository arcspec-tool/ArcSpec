import secrets
import time
import uuid

from django.db import models

VERSION_7 = 0x7
RFC_VARIANT = 0b10


def uuid7():
    if hasattr(uuid, 'uuid7'):
        return uuid.uuid7()
    timestamp_ms = time.time_ns() // 1_000_000
    value = (
        (timestamp_ms << 80)
        | (VERSION_7 << 76)
        | (secrets.randbits(12) << 64)
        | (RFC_VARIANT << 62)
        | secrets.randbits(62)
    )
    return uuid.UUID(int=value)


def public_key_field():
    return models.UUIDField(default=uuid7, unique=True, editable=False)


def fill_public_keys(app_label, *model_names):
    def fill(apps, schema_editor):
        for name in model_names:
            model = apps.get_model(app_label, name)
            for pk in model.objects.filter(public_key__isnull=True).values_list('pk', flat=True):
                model.objects.filter(pk=pk).update(public_key=uuid7())
    return fill


class PublicKeyModel(models.Model):
    public_key = public_key_field()

    class Meta:
        abstract = True
