# downloader/utils.py
import os
from django.conf import settings
from .models import TemporaryDownload
from django.utils import timezone
from datetime import timedelta
import shutil

# downloader/utils.py
import re

def validate_youtube_url(url):
    patterns = [
        r'(https?://)?(www\.)?youtube\.com/watch\?v=[\w-]+',
        r'(https?://)?youtu\.be/[\w-]+',
        r'(https?://)?(www\.)?youtube\.com/shorts/[\w-]+'
    ]
    return any(re.match(pattern, url) for pattern in patterns)

def cleanup_expired_downloads():
    """Delete expired downloads and their files"""
    expired = TemporaryDownload.objects.filter(expires_at__lte=timezone.now())
    for download in expired:
        if os.path.exists(download.file_path):
            try:
                os.remove(download.file_path)
            except:
                pass
    expired.delete()

def get_temporary_storage_path(filename):
    """Get path in temporary storage directory"""
    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    return os.path.join(temp_dir, filename)

def generate_share_link(request, download_id):
    """Generate full shareable URL"""
    return request.build_absolute_uri(f'/convert/{download_id}/')