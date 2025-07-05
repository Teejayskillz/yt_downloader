# downloader/views.py
from django.shortcuts import render, get_object_or_404
from pytube import YouTube
from .models import TemporaryDownload
from .utils import cleanup_expired_downloads, get_temporary_storage_path, generate_share_link
from django.http import FileResponse, Http404, HttpResponseBadRequest
from django.conf import settings
import os
import re
from urllib.parse import urlparse, parse_qs
from pytube.exceptions import (
    RegexMatchError, 
    VideoUnavailable, 
    AgeRestrictedError,
    MembersOnly,
    LiveStreamError,
    VideoPrivate,
    RecordingUnavailable,
    PytubeError
)
from datetime import datetime
import logging
from moviepy.editor import AudioFileClip
from django.utils import timezone
import time
import random

logger = logging.getLogger(__name__)

# Custom headers to mimic browser requests
CUSTOM_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

def validate_youtube_url(url):
    """Improved YouTube URL validation"""
    patterns = [
        r'^https?://(www\.)?youtube\.com/watch\?v=[\w-]{11}',
        r'^https?://youtu\.be/[\w-]{11}',
        r'^https?://(www\.)?youtube\.com/shorts/[\w-]{11}',
        r'^https?://(www\.)?youtube\.com/live/[\w-]{11}',
        r'^https?://(www\.)?youtube\.com/embed/[\w-]{11}'
    ]
    return any(re.match(pattern, url) for pattern in patterns)

def extract_video_id(url):
    """More robust video ID extraction"""
    if 'youtu.be/' in url:
        match = re.search(r'youtu\.be/([\w-]{11})', url)
        return match.group(1) if match else None
    elif 'youtube.com/watch' in url:
        match = re.search(r'v=([\w-]{11})', url)
        return match.group(1) if match else None
    elif 'youtube.com/shorts/' in url:
        match = re.search(r'shorts/([\w-]{11})', url)
        return match.group(1) if match else None
    elif 'youtube.com/live/' in url:
        match = re.search(r'live/([\w-]{11})', url)
        return match.group(1) if match else None
    elif 'youtube.com/embed/' in url:
        match = re.search(r'embed/([\w-]{11})', url)
        return match.group(1) if match else None
    return None

def get_yt_streams(video_id, max_retries=3):
    """Handle YouTube stream retrieval with retries"""
    for attempt in range(max_retries):
        try:
            # Add delay between retries
            if attempt > 0:
                time.sleep(random.uniform(1, 3))
            
            # Initialize YouTube object
            yt = YouTube(
                f'https://www.youtube.com/watch?v={video_id}',
                use_oauth=False,
                allow_oauth_cache=False
            )
            
            # Bypass age restriction
            try:
                yt.bypass_age_gate()
            except:
                pass  # Continue even if age gate bypass fails
            
            # Get available streams
            streams = yt.streams.filter(
                progressive=True,
                file_extension='mp4'
            ).order_by('resolution').desc()
            
            audio_streams = yt.streams.filter(
                only_audio=True
            ).order_by('abr').desc()
            
            return {
                'yt': yt,
                'streams': streams,
                'audio_streams': audio_streams,
                'success': True
            }
            
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed for {video_id}: {str(e)}")
            if attempt < max_retries - 1:
                continue
            return {
                'success': False,
                'error': str(e)
            }

def home(request):
    cleanup_expired_downloads()
    if request.method == 'POST':
        video_url = request.POST.get('video_url', '').strip()
        
        try:
            # Validate URL format
            if not validate_youtube_url(video_url):
                raise ValueError("Invalid YouTube URL format")
            
            video_id = extract_video_id(video_url)
            if not video_id:
                raise ValueError("Could not extract video ID from URL")
            
            # Get streams with error handling
            result = get_yt_streams(video_id)
            if not result['success']:
                raise ValueError(f"Could not fetch video: {result['error']}")
            
            if not result['streams'] and not result['audio_streams']:
                raise ValueError("No downloadable streams found")
            
            context = {
                'title': result['yt'].title,
                'thumbnail': result['yt'].thumbnail_url,
                'streams': result['streams'],
                'audio_streams': result['audio_streams'],
                'url': video_url,
                'video_id': video_id
            }
            return render(request, 'downloader/download.html', context)
            
        except ValueError as e:
            error = str(e)
        except Exception as e:
            error = f"An error occurred: {str(e)}"
            logger.error(f"Home view error: {error}")
        
        return render(request, 'downloader/home.html', {
            'error': error,
            'video_url': video_url,
            'supported_formats': [
                "https://www.youtube.com/watch?v=VIDEO_ID",
                "https://youtu.be/VIDEO_ID",
                "https://youtube.com/shorts/VIDEO_ID",
                "https://youtube.com/live/VIDEO_ID"
            ]
        })
    
    return render(request, 'downloader/home.html')

def download_video(request):
    cleanup_expired_downloads()
    if request.method == 'POST':
        video_url = request.POST.get('video_url')
        video_id = request.POST.get('video_id')
        itag = request.POST.get('itag')
        convert_to_mp3 = request.POST.get('convert_to_mp3', False)
        
        if not all([video_url, video_id, itag]):
            return HttpResponseBadRequest("Missing required parameters")
        
        try:
            # Initialize with retry logic
            for attempt in range(3):
                try:
                    yt = YouTube(
                        f'https://www.youtube.com/watch?v={video_id}',
                        use_oauth=False,
                        allow_oauth_cache=False
                    )
                    
                    # Bypass age restriction
                    try:
                        yt.bypass_age_gate()
                    except:
                        pass
                    
                    stream = yt.streams.get_by_itag(itag)
                    if not stream:
                        raise ValueError("Requested video format not available")
                    
                    # Generate unique filename
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_ext = '.mp3' if convert_to_mp3 else '.mp4'
                    file_name = f"{video_id}_{timestamp}{file_ext}"
                    file_path = os.path.join(get_temporary_storage_path(''), file_name)
                    
                    # Download with timeout
                    stream.download(
                        output_path=os.path.dirname(file_path),
                        filename=os.path.basename(file_path),
                        timeout=15
                    )
                    
                    # Handle MP3 conversion
                    if convert_to_mp3:
                        mp3_path = file_path.replace('.mp4', '.mp3')
                        try:
                            audio_clip = AudioFileClip(file_path)
                            audio_clip.write_audiofile(mp3_path)
                            audio_clip.close()
                            os.remove(file_path)
                            file_path = mp3_path
                            content_type = 'audio/mpeg'
                            format_type = 'audio/mpeg'
                        except Exception as e:
                            raise ValueError(f"MP3 conversion failed: {str(e)}")
                    else:
                        content_type = 'video/mp4'
                        format_type = stream.mime_type
                    
                    # Create download record
                    download = TemporaryDownload.objects.create(
                        video_url=video_url,
                        video_title=yt.title,
                        file_path=file_path,
                        format_type=format_type
                    )
                    
                    # Return file for download
                    response = FileResponse(
                        open(file_path, 'rb'),
                        content_type=content_type,
                        as_attachment=True
                    )
                    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
                    return response
                    
                except Exception as e:
                    if attempt == 2:  # Last attempt
                        raise
                    time.sleep(random.uniform(1, 3))
                    continue
                    
        except Exception as e:
            error = f"Download failed after 3 attempts: {str(e)}"
            logger.error(f"Download error: {error}")
            return render(request, 'downloader/home.html', {
                'error': error,
                'video_url': video_url
            })
    
    return render(request, 'downloader/home.html')

# ... (keep convert_view and download_from_link the same as before)
# ... 
def convert_view(request, download_id):
    cleanup_expired_downloads()
    download = get_object_or_404(TemporaryDownload, id=download_id)
    
    if download.is_expired():
        # Clean up expired file
        if os.path.exists(download.file_path):
            try:
                os.remove(download.file_path)
            except:
                pass
        raise Http404("This download link has expired")
    
    if not os.path.exists(download.file_path):
        download.delete()
        raise Http404("File not found")
    
    context = {
        'title': download.video_title,
        'download': download,
        'share_link': generate_share_link(request, download_id),
        'expires_in': download.expires_at - timezone.now()
    }
    return render(request, 'downloader/convert.html', context)

def download_from_link(request, download_id):
    cleanup_expired_downloads()
    download = get_object_or_404(TemporaryDownload, id=download_id)
    
    if download.is_expired():
        if os.path.exists(download.file_path):
            try:
                os.remove(download.file_path)
            except:
                pass
        raise Http404("This download link has expired")
    
    if not os.path.exists(download.file_path):
        download.delete()
        raise Http404("File not found")
    
    response = FileResponse(
        open(download.file_path, 'rb'),
        content_type=download.format_type,
        as_attachment=True
    )
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(download.file_path)}"'
    return response