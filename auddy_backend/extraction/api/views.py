import os
from django.http import FileResponse

from rest_framework import viewsets, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from auddy_backend.extraction.models import Extraction
from auddy_backend.extraction.api.serializers import (
    ExtractionCreateSerializer,
    ExtractionStatusSerializer,
    ExtractionDetailSerializer,
    FormatSerializer,
)
from auddy_backend.extraction.services import ExtractionService
from auddy_backend.contrib.responses import build_response


class ExtractionViewSet(mixins.CreateModelMixin,
                        mixins.RetrieveModelMixin,
                        mixins.ListModelMixin,
                        viewsets.GenericViewSet):
    """
    ViewSet for audio extraction operations.
    """
    # throttle_classes = [AnonRateThrottle, UserRateThrottle]
    permission_classes = []
    service = ExtractionService

    def get_queryset(self):
        """Return all extractions."""
        return Extraction.objects.all()

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'create':
            return ExtractionCreateSerializer
        return ExtractionDetailSerializer
    
    def create(self, request, *args, **kwargs):
        """Create an extraction request and start Celery task."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        extraction_process = self.service.initialize_extraction(serializer.validated_data)
        
        return build_response(
            status_code=status.HTTP_201_CREATED,
            message="Extraction request created successfully",
            data=ExtractionStatusSerializer(extraction_process).data
        )
        
    @action(detail=False, methods=['get'])
    def formats(self, request):
        """Return available audio formats."""
        formats = []
        for format_choice in Extraction.Format.choices:
            formats.append({
                'value': format_choice[0],
                'label': format_choice[1]
            })
        
        serializer = FormatSerializer(formats, many=True)
        return Response(serializer.data)


class ExtractionStatusView(APIView):
    """View to check extraction status by task_id."""
    # throttle_classes = [AnonRateThrottle]
    permission_classes = []

    def get(self, request, task_id):
        """Get extraction status."""
        try:
            extraction = Extraction.objects.get(task_id=task_id)
            serializer = ExtractionStatusSerializer(extraction)
            return Response(serializer.data)
        except Extraction.DoesNotExist:
            return Response(
                {"error": "Extraction not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class ExtractionDownloadView(APIView):
    """View to download completed extraction files."""
    # throttle_classes = [AnonRateThrottle, UserRateThrottle]
    permission_classes = []
    def get(self, request, extraction_id):
        """Download the audio file."""
        try:
            extraction = Extraction.objects.get(id=extraction_id)
            
            # Check if file exists
            if not extraction.file_path or not os.path.exists(extraction.file_path):
                return Response(
                    {"error": "File not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
            # Check if extraction is completed
            if extraction.status != Extraction.Status.COMPLETED:
                return Response(
                    {"error": "Extraction not completed"},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            # Set the filename for download
            filename = os.path.basename(extraction.file_path)
            
            # Return file response
            response = FileResponse(
                open(extraction.file_path, 'rb'),
                as_attachment=True,
                filename=filename
            )
            
            return response
            
        except Extraction.DoesNotExist:
            return Response(
                {"error": "Extraction not found"},
                status=status.HTTP_404_NOT_FOUND
            ) 