from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from auddy_backend.extraction.models import Extraction
from auddy_backend.extraction.tasks import is_youtube_url


class ExtractionModelTests(TestCase):
    """Tests for the Extraction model."""

    def test_extraction_creation(self):
        """Test creating an extraction record."""
        extraction = Extraction.objects.create(
            source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            format=Extraction.Format.MP3,
        )
        self.assertEqual(extraction.status, Extraction.Status.PENDING)
        self.assertEqual(extraction.format, Extraction.Format.MP3)


class ExtractionTaskTests(TestCase):
    """Tests for extraction tasks and helpers."""

    def test_youtube_url_detection(self):
        """Test detection of YouTube URLs."""
        youtube_urls = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://youtube.com/watch?v=dQw4w9WgXcQ",
        ]
        non_youtube_urls = [
            "https://www.example.com/video.mp4",
            "https://vimeo.com/123456789",
            "https://www.dailymotion.com/video/x7tgad",
        ]

        for url in youtube_urls:
            self.assertTrue(is_youtube_url(url), f"Failed to detect YouTube URL: {url}")

        for url in non_youtube_urls:
            self.assertFalse(is_youtube_url(url), f"Incorrectly detected as YouTube URL: {url}")


class ExtractionAPITests(APITestCase):
    """Tests for the extraction API endpoints."""

    @patch('auddy_backend.extraction.api.views.extract_audio')
    def test_create_extraction(self, mock_task):
        """Test creating an extraction via API."""
        mock_task.delay.return_value = MagicMock(id="test-task-id")

        url = reverse("api:extract-list")
        data = {
            "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "format": Extraction.Format.MP3,
        }
        
        response = self.client.post(url, data, format="json")
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Extraction.objects.count(), 1)
        
        extraction = Extraction.objects.first()
        self.assertEqual(extraction.source_url, data["source_url"])
        self.assertEqual(extraction.format, data["format"])
        self.assertEqual(extraction.task_id, "test-task-id")
        
        mock_task.delay.assert_called_once_with(str(extraction.id))

    def test_formats_list(self):
        """Test listing available formats."""
        url = reverse("api:extract-formats")
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), len(Extraction.Format.choices))
        
        for format_data in response.data:
            self.assertIn("value", format_data)
            self.assertIn("label", format_data) 