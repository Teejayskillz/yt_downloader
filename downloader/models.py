# downloader/models.py
from django.db import models
import uuid
from django.utils import timezone
from datetime import timedelta

class TemporaryDownload(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video_url = models.URLField()
    video_title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    file_path = models.CharField(max_length=255)
    format_type = models.CharField(max_length=50)
    expires_at = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=1)
        super().save(*args, **kwargs)

    def is_expired(self):
        return timezone.now() > self.expires_at

    def __str__(self):
        return f"{self.video_title} (expires: {self.expires_at})"