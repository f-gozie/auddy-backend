import os
import time
import tempfile
import shutil
import subprocess
import logging
import re
from urllib.parse import urlparse, parse_qs
from datetime import datetime

import yt_dlp
import requests
from pydub import AudioSegment
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from auddy_backend.extraction.models import Extraction

logger = logging.getLogger(__name__)

# Configure media storage directory
MEDIA_ROOT = getattr(settings, 'MEDIA_ROOT', os.path.join(settings.BASE_DIR, 'media'))
EXTRACTION_DIR = os.path.join(MEDIA_ROOT, 'extractions')


def is_youtube_url(url):
    """Check if a URL is from YouTube."""
    parsed_url = urlparse(url)
    return ('youtube.com' in parsed_url.netloc or 
            'youtu.be' in parsed_url.netloc or 
            'youtube' in parsed_url.netloc)


def is_google_drive_url(url):
    """Check if a URL is from Google Drive."""
    parsed_url = urlparse(url)
    return ('drive.google.com' in parsed_url.netloc or
            'docs.google.com' in parsed_url.netloc)


def extract_google_drive_file_id(url):
    """Extract the file ID from a Google Drive URL."""
    parsed_url = urlparse(url)
    
    # Pattern 1: /file/d/{file_id}/
    file_id_match = re.search(r'/file/d/([^/]+)', parsed_url.path)
    if file_id_match:
        return file_id_match.group(1)
    
    # Pattern 2: /open?id={file_id}
    if 'open' in parsed_url.path:
        query_params = parse_qs(parsed_url.query)
        if 'id' in query_params:
            return query_params['id'][0]
    
    # Pattern 3: /uc?id={file_id}
    if 'uc' in parsed_url.path:
        query_params = parse_qs(parsed_url.query)
        if 'id' in query_params:
            return query_params['id'][0]
            
    # Pattern 4: /view?usp=sharing
    if 'view' in parsed_url.path:
        # Extract from path for GDrive's sharing URLs
        path_parts = parsed_url.path.split('/')
        if len(path_parts) >= 3:
            return path_parts[-2]
    
    # If no pattern matches, return None
    logger.error(f"Could not extract Google Drive file ID from URL: {url}")
    return None


def create_directory_safely(directory_path):
    """
    Attempts to create a directory if it doesn't exist.
    Returns True if the directory exists or was created successfully.
    Returns False if there was a permission error.
    """
    if os.path.exists(directory_path):
        return True
    
    try:
        os.makedirs(directory_path, exist_ok=True)
        return True
    except PermissionError:
        logger.warning(f"Permission denied when creating directory: {directory_path}")
        return False
    except Exception as e:
        logger.warning(f"Error creating directory {directory_path}: {str(e)}")
        return False


def download_from_google_drive(file_id, output_path):
    """Download a file from Google Drive."""
    logger.info(f"Downloading Google Drive file: {file_id}")
    
    # First, get a download URL
    session = requests.Session()
    
    # First request to get the confirmation token
    url = f"https://drive.google.com/uc?export=download&id={file_id}"
    response = session.get(url, stream=True)
    
    # Check if there's a download warning (large file)
    for key, value in response.cookies.items():
        if key.startswith('download_warning'):
            # Get the token
            token = value
            # Make a second request with the token
            url = f"https://drive.google.com/uc?export=download&confirm={token}&id={file_id}"
            break
    
    # Download the file
    response = session.get(url, stream=True)
    
    if response.status_code != 200:
        logger.error(f"Failed to download Google Drive file: {response.status_code}")
        raise Exception(f"Failed to download from Google Drive: HTTP {response.status_code}")
    
    # Make sure the directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Save the file
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    
    # Return the size of the file
    return os.path.getsize(output_path)


def get_video_info(url):
    """Get video information using yt-dlp."""
    with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
        info = ydl.extract_info(url, download=False)
        return {
            'title': info.get('title', ''),
            'duration': info.get('duration', 0),
        }


def extract_from_youtube(extraction, temp_dir):
    """Extract audio from YouTube video."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': extraction.audio_format,
            'preferredquality': '192',
        }],
        'progress_hooks': [lambda d: logger.info(f"Progress: {d.get('status')}, {d.get('_percent_str', 'N/A')}")],
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(extraction.source_url, download=True)
        extracted_file = None
        
        # Find the extracted audio file
        for file in os.listdir(temp_dir):
            if file.endswith(f".{extraction.audio_format}"):
                extracted_file = os.path.join(temp_dir, file)
                break
        
        if not extracted_file:
            raise Exception("Failed to find extracted audio file")
        
        extraction.title = info.get('title', '')
        extraction.duration = info.get('duration', 0)
        
        return extracted_file


def extract_from_google_drive(extraction, temp_dir):
    """Extract audio from a Google Drive video file."""
    # Extract the file ID from the URL
    file_id = extract_google_drive_file_id(extraction.source_url)
    if not file_id:
        raise Exception("Invalid Google Drive URL")
    
    # Download the video to a temporary file
    temp_video = os.path.join(temp_dir, 'google_drive_video')
    try:
        download_from_google_drive(file_id, temp_video)
    except Exception as e:
        logger.error(f"Failed to download from Google Drive: {str(e)}")
        raise Exception(f"Failed to download from Google Drive: {str(e)}")
    
    # Generate output filename
    output_filename = f"extracted_audio.{extraction.audio_format}"
    output_path = os.path.join(temp_dir, output_filename)
    
    try:
        # Extract audio using FFmpeg
        cmd = [
            'ffmpeg',
            '-i', temp_video,
            '-vn',  # Disable video
            '-c:a', 'libmp3lame' if extraction.audio_format == 'mp3' else extraction.audio_format,
            '-q:a', '2',  # Quality setting
            '-y',  # Overwrite output file
            output_path
        ]
        
        logger.info(f"Running FFmpeg: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info(f"FFmpeg stdout: {result.stdout}")
        logger.info(f"FFmpeg stderr: {result.stderr}")
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stdout}, {e.stderr}")
        raise Exception(f"Failed to extract audio: {e}")
    
    # Try to get the title and duration from the video
    try:
        # Get duration using FFprobe
        duration_cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            output_path
        ]
        
        duration = float(subprocess.check_output(duration_cmd).decode('utf-8').strip())
        extraction.duration = int(duration)
        
        # Try to get title from the video metadata
        title_cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format_tags=title',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            temp_video
        ]
        
        try:
            title = subprocess.check_output(title_cmd).decode('utf-8').strip()
            if title:
                extraction.title = title
            else:
                # Use file ID as title if metadata doesn't have a title
                extraction.title = f"Google Drive Video {file_id[:8]}"
        except subprocess.CalledProcessError:
            # Fall back to a default title
            extraction.title = f"Google Drive Video {file_id[:8]}"
    except Exception as e:
        logger.warning(f"Error getting video metadata: {str(e)}")
        extraction.title = f"Google Drive Video {file_id[:8]}"
        # Don't fail the whole process for metadata issues
    
    return output_path


def extract_from_video(extraction, temp_dir):
    """Extract audio from a video file using FFmpeg directly."""
    # Download the video to a temporary file
    temp_video = os.path.join(temp_dir, 'input_video')
    
    # Download video using curl
    try:
        subprocess.run(
            ['curl', '-L', '-o', temp_video, extraction.source_url],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to download video: {e.stdout} {e.stderr}")
        raise Exception(f"Failed to download video: {e}")
    
    # Generate output filename
    output_filename = f"extracted_audio.{extraction.audio_format}"
    output_path = os.path.join(temp_dir, output_filename)
    
    # Extract audio using FFmpeg
    cmd = [
        'ffmpeg',
        '-i', temp_video,
        '-vn',  # Disable video
        '-c:a', 'libmp3lame' if extraction.audio_format == 'mp3' else extraction.audio_format,
        '-q:a', '2',  # Quality setting
        '-y',  # Overwrite output file
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {str(e)}")
        raise Exception(f"Failed to extract audio: {str(e)}")
    
    # Get duration using FFprobe
    duration_cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        output_path
    ]
    
    duration = float(subprocess.check_output(duration_cmd).decode('utf-8').strip())
    extraction.duration = int(duration)
    
    # Try to get title from the video metadata
    title_cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format_tags=title',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        temp_video
    ]
    
    try:
        title = subprocess.check_output(title_cmd).decode('utf-8').strip()
        if title:
            extraction.title = title
        else:
            # Use filename as title if metadata doesn't have a title
            parsed_url = urlparse(extraction.source_url)
            extraction.title = os.path.basename(parsed_url.path)
    except subprocess.CalledProcessError:
        # Fall back to URL-based title
        parsed_url = urlparse(extraction.source_url)
        extraction.title = os.path.basename(parsed_url.path)
    
    return output_path


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def extract_audio(self, extraction_id):
    """Extract audio from a URL."""
    try:
        # Get the extraction object
        extraction = Extraction.objects.get(id=extraction_id)
        
        # Update status to processing
        extraction.status = Extraction.Status.PROCESSING
        extraction.save(update_fields=['status'])
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Process based on URL type
                if is_youtube_url(extraction.source_url):
                    # First, get video info to update the extraction title
                    try:
                        info = get_video_info(extraction.source_url)
                        extraction.title = info.get('title', '')
                        extraction.save(update_fields=['title'])
                    except Exception as e:
                        logger.warning(f"Failed to get video info: {str(e)}")
                    
                    # Extract audio from YouTube
                    extracted_file = extract_from_youtube(extraction, temp_dir)
                elif is_google_drive_url(extraction.source_url):
                    # Extract audio from Google Drive
                    extracted_file = extract_from_google_drive(extraction, temp_dir)
                else:
                    # Extract audio from direct video link
                    extracted_file = extract_from_video(extraction, temp_dir)
                
                # Create final directory based on extraction ID
                final_dir = os.path.join(EXTRACTION_DIR, str(extraction.id))
                
                # Verify if we can create the directory - if not, fail gracefully
                if not create_directory_safely(final_dir):
                    raise Exception("Unable to create extraction directory. Please contact administrator.")
                
                # Move file to final location
                filename = f"{extraction.title or 'extracted'}.{extraction.audio_format}"
                sanitized_filename = "".join(c for c in filename if c.isalnum() or c in ' ._-').strip()
                
                # Ensure filename is not too long
                if len(sanitized_filename) > 100:
                    sanitized_filename = sanitized_filename[:100] + f".{extraction.audio_format}"
                
                final_path = os.path.join(final_dir, sanitized_filename)
                
                try:
                    shutil.copy2(extracted_file, final_path)
                except (PermissionError, IOError) as e:
                    logger.error(f"Failed to copy file to {final_path}: {str(e)}")
                    raise Exception(f"Unable to save extracted audio file: {str(e)}")
                
                # Get file size
                try:
                    file_size = os.path.getsize(final_path)
                except (PermissionError, IOError) as e:
                    logger.warning(f"Unable to get file size for {final_path}: {str(e)}")
                    file_size = None
                
                # Update extraction object
                extraction.file_path = final_path
                extraction.file_size = file_size
                extraction.status = Extraction.Status.COMPLETED
                extraction.completed_at = timezone.now()
                extraction.save()
                
                logger.info(f"Successfully extracted audio: {extraction.id}")
                
            except Exception as e:
                logger.error(f"Error during extraction: {str(e)}")
                extraction.status = Extraction.Status.FAILED
                extraction.error_message = str(e)
                extraction.save()
                raise
    
    except Extraction.DoesNotExist:
        logger.error(f"Extraction with ID {extraction_id} does not exist")
    except Exception as e:
        logger.error(f"Error in extract_audio task: {str(e)}")
        try:
            extraction = Extraction.objects.get(id=extraction_id)
            extraction.status = Extraction.Status.FAILED
            extraction.error_message = str(e)
            extraction.save()
        except Exception:
            pass
        
        # Retry the task
        self.retry(exc=e) 