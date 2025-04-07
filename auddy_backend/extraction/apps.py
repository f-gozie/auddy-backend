from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ExtractionConfig(AppConfig):
    name = "auddy_backend.extraction"
    verbose_name = _("Audio Extraction")

    def ready(self):
        try:
            import auddy_backend.extraction.signals  # noqa
        except ImportError:
            pass 