from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from auddy_backend.contrib.models import BaseModel


class Extraction(BaseModel):
    """Model for audio extraction from various sources."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    class Format(models.TextChoices):
        MP3 = "mp3", _("MP3")
        AAC = "aac", _("AAC")
        WAV = "wav", _("WAV")
        FLAC = "flac", _("FLAC")
        OGG = "ogg", _("OGG")
        M4A = "m4a", _("M4A")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="extractions",
        null=True,
        blank=True,
    )
    source_url = models.URLField(_("Source URL"), max_length=2000)
    title = models.CharField(_("Title"), max_length=255, blank=True)
    audio_format = models.CharField(
        _("Format"),
        max_length=10,
        choices=Format.choices,
        default=Format.MP3,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    file_path = models.CharField(_("File Path"), max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField(_("File Size"), null=True, blank=True)
    duration = models.PositiveIntegerField(_("Duration (seconds)"), null=True, blank=True)
    error_message = models.TextField(_("Error Message"), blank=True)
    task_id = models.CharField(_("Celery Task ID"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("Extraction")
        verbose_name_plural = _("Extractions")
        ordering = ["-created"]

    def __str__(self):
        return f"{self.title or self.source_url} ({self.audio_format})"

    def get_absolute_url(self):
        return reverse("extraction:detail", kwargs={"id": self.id}) 
