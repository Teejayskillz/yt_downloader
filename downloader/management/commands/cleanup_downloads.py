# downloader/management/commands/cleanup_downloads.py
from django.core.management.base import BaseCommand
from downloader.models import TemporaryDownload
from django.utils import timezone
import os

class Command(BaseCommand):
    help = 'Cleans up expired temporary downloads'

    def handle(self, *args, **options):
        expired = TemporaryDownload.objects.filter(expires_at__lte=timezone.now())
        count = expired.count()
        
        for download in expired:
            if os.path.exists(download.file_path):
                try:
                    os.remove(download.file_path)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Error deleting file {download.file_path}: {e}"))
        
        expired.delete()
        self.stdout.write(self.style.SUCCESS(f'Successfully cleaned up {count} expired downloads'))