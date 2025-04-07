from auddy_backend.extraction.models import Extraction
from auddy_backend.extraction.tasks import extract_audio

class ExtractionService:
    """Service for managing extraction requests."""

    @staticmethod
    def initialize_extraction(data: dict) -> Extraction:
        """Initialize an extraction request."""
        extraction = Extraction.objects.create(**data)

        task = extract_audio.delay(str(extraction.id))
        extraction.task_id = task.id
        extraction.save(update_fields=['task_id'])

        return extraction
    
    def get_extraction_status(self, extraction_id: str) -> Extraction:
        """Get the status of an extraction request."""
        extraction = Extraction.objects.get(id=extraction_id)
        return extraction