from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse

from auddy_backend.extraction.models import Extraction


class ExtractionAdmin(admin.ModelAdmin):
    list_display = ('id', 'title_display', 'source_url', 'audio_format', 'status', 'created', 'completed_at', 'user')
    list_filter = ('status', 'audio_format', 'created')
    search_fields = ('title', 'source_url', 'id')
    readonly_fields = ('id', 'created', 'completed_at', 'file_size', 'duration', 'task_id')
    fieldsets = (
        (None, {'fields': ('id', 'user', 'source_url', 'title', 'audio_format')}),
        ('Status', {'fields': ('status', 'error_message', 'task_id')}),
        ('File Information', {'fields': ('file_path', 'file_size', 'duration')}),
        ('Timestamps', {'fields': ('created', 'completed_at')}),
    )
    
    def title_display(self, obj):
        if obj.status == Extraction.Status.COMPLETED and obj.file_path:
            url = reverse('admin:extraction_download', args=[obj.id])
            return format_html('<a href="{}">{}</a>', url, obj.title or "Untitled")
        return obj.title or "Untitled"
    
    title_display.short_description = 'Title'
    title_display.admin_order_field = 'title'


admin.site.register(Extraction, ExtractionAdmin) 