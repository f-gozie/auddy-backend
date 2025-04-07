from django.db import models
from django.utils import timezone
import uuid


class BaseModel(models.Model):
    id = models.AutoField(primary_key=True, auto_created=True)
    public_id = models.UUIDField(
        unique=True, primary_key=False, default=uuid.uuid4, editable=False
    )
    created = models.DateTimeField(default=timezone.now, editable=False)
    modified = models.DateTimeField(auto_now=True, blank=True, null=True)
    is_deleted = models.BooleanField(default=False)

    objects = models.Manager()

    class Meta:
        abstract = True
