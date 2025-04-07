from rest_framework import serializers
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError

from auddy_backend.extraction.models import Extraction


class URLValidator(URLValidator):
    """Custom URL validator that supports YouTube URLs."""

    def __call__(self, value):
        super().__call__(value)
        # Additional validation specific to video URLs could be added here
        return value


class ExtractionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating extraction requests."""

    class Meta:
        model = Extraction
        fields = ["source_url", "audio_format"]

    def validate_source_url(self, value):
        validator = URLValidator()
        try:
            validator(value)
        except ValidationError:
            raise serializers.ValidationError("Invalid URL format")
        return value


class ExtractionStatusSerializer(serializers.ModelSerializer):
    """Serializer for extraction status."""

    class Meta:
        model = Extraction
        fields = [
            "id",
            "source_url",
            "title",
            "audio_format",
            "status",
            "created",
            "completed_at",
            "file_size",
            "duration",
            "error_message",
            "task_id",
        ]
        read_only_fields = fields


class ExtractionDetailSerializer(serializers.ModelSerializer):
    """Serializer for extraction details."""
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Extraction
        fields = [
            "id",
            "source_url",
            "title",
            "audio_format",
            "status",
            "created",
            "completed_at",
            "file_size",
            "duration",
            "error_message",
            "download_url",
        ]
        read_only_fields = fields

    def get_download_url(self, obj):
        if obj.status == Extraction.Status.COMPLETED:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(f"/api/download/{obj.id}/")
        return None


class FormatSerializer(serializers.Serializer):
    """Serializer for available audio formats."""

    value = serializers.CharField()
    label = serializers.CharField() 