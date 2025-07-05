# downloader/views.py
import os
import yt_dlp # Import yt-dlp
from django.shortcuts import render, get_object_or_404
from .models import TemporaryDownload
from .utils import cleanup_expired_downloads, get_temporary_storage_path, generate_share_link
from django.http import FileResponse, Http404, HttpResponseBadRequest, HttpResponse # Added HttpResponse import
from django.conf import settings
import re
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import logging
# from moviepy.editor import AudioFileClip # No longer strictly needed if yt-dlp handles MP3 conversion
from django.utils import timezone
import time
import random
import mimetypes # Import mimetypes for robust content type guessing

logger = logging.getLogger(__name__)

# Custom headers to mimic browser requests (yt-dlp handles this internally well, but can be set via options)
# CUSTOM_HEADERS = {
#     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
#     'Accept-Language': 'en-US,en;q=0.9',
# }

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

# Removed get_yt_streams as its logic is now integrated into home()

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
            
            # yt-dlp options for extracting info (no download)
            ydl_opts_info = {
                'quiet': True, # Suppress console output
                'simulate': True, # Do not download files
                'force_generic_extractor': True, # Try generic extractor if specific fails
                'noplaylist': True, # Ensure only single video info is extracted
                # 'retries': 3, # yt-dlp has internal retry logic
                # 'extractor_args': {'youtube': {'player_client': ['web']}}, # Often helps with 400 errors
            }

            video_info = None
            # yt-dlp can sometimes fail on first attempt, so add a simple retry
            for attempt in range(3):
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                        info_dict = ydl.extract_info(video_url, download=False)
                        # For single video URLs, info_dict is usually the video's info
                        # For playlist-like URLs (even for single video), it might be in 'entries'
                        video_info = info_dict.get('entries', [info_dict])[0]
                        break # Success, break out of retry loop
                except yt_dlp.utils.DownloadError as e:
                    logger.warning(f"yt-dlp info extraction attempt {attempt + 1} failed for {video_id}: {str(e)}")
                    if "HTTP Error 400" in str(e) or "Too Many Requests" in str(e):
                        time.sleep(random.uniform(2, 5)) # Longer delay for specific HTTP errors
                    else:
                        time.sleep(random.uniform(1, 3))
                    if attempt == 2: # Last attempt
                        raise # Re-raise if all attempts fail
                except Exception as e: # Catch other general exceptions during info extraction
                    logger.warning(f"General info extraction attempt {attempt + 1} failed for {video_id}: {str(e)}")
                    time.sleep(random.uniform(1, 3))
                    if attempt == 2:
                        raise

            if not video_info:
                raise ValueError("Could not retrieve video information from YouTube.")

            # Filter and prepare streams for the template
            streams_for_template = []
            # audio_streams_for_template = [] # Removed as per request

            # yt-dlp provides a 'formats' list. We need to parse it.
            # We'll use 'format_id' as the identifier for the form submission.
            for f in video_info.get('formats', []):
                # Ensure filesize is not None before adding to dict, or provide a default
                filesize = f.get('filesize')
                if filesize is None:
                    filesize = 0 # Default to 0 if filesize is None
                
                # Filter for progressive MP4 streams (video + audio in one file)
                # Or any video stream where vcodec is not 'none'
                if f.get('vcodec') != 'none' and f.get('height'): # Check for video stream with height
                    streams_for_template.append({
                        'itag': f.get('format_id'), # Using format_id as itag equivalent
                        'resolution': f.get('resolution') or f.get('height'),
                        'filesize': filesize,
                        'mime_type': f.get('ext'), # Use extension as mime_type for simplicity
                        'fps': f.get('fps'),
                        'url': f.get('url'), # This is the direct download URL for progressive streams
                        'ext': f.get('ext'),
                        'vcodec': f.get('vcodec'),
                        'acodec': f.get('acodec'),
                    })
                # Removed audio-only stream filtering

            # Define robust key functions for sorting
            def get_resolution_sort_key(stream):
                # Get resolution or height, default to '0' as string
                res_val_str = str(stream.get('resolution') or stream.get('height') or '0')
                # Extract only numeric parts
                numeric_res_str = re.sub(r'\D', '', res_val_str)
                try:
                    # Convert to int, if empty string, use '0' before converting
                    return int(numeric_res_str) if numeric_res_str else 0
                except ValueError:
                    return 0 # Fallback if conversion still fails

            # Removed get_abr_sort_key as it's no longer needed

            # Sort streams by resolution for display using the robust key
            streams_for_template.sort(key=get_resolution_sort_key, reverse=True)
            # Removed audio_streams_for_template sort

            if not streams_for_template: # Updated check
                raise ValueError("No downloadable video streams found for this video.")
            
            context = {
                'title': video_info.get('title'),
                'thumbnail': video_info.get('thumbnail'),
                'streams': streams_for_template,
                # 'audio_streams': audio_streams_for_template, # Removed
                'url': video_url,
                'video_id': video_id
            }
            return render(request, 'downloader/download.html', context)
            
        except ValueError as e:
            error = str(e)
        except yt_dlp.utils.DownloadError as e:
            error = f"Could not fetch video details (yt-dlp error): {str(e)}"
            logger.error(f"yt-dlp info error: {error}")
        except Exception as e:
            error = f"An unexpected error occurred: {str(e)}"
            logger.error(f"Home view general error: {error}")
        
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
        format_id = request.POST.get('itag') 
        
        missing_params = []
        if not video_url:
            missing_params.append('video URL')
        if not video_id:
            missing_params.append('video ID')
        if not format_id:
            missing_params.append('stream selection (resolution/quality)')

        if missing_params:
            error_message = f"Missing required parameters for download: {', '.join(missing_params)}. Please go back and select a video quality."
            logger.warning(f"Download request missing parameters: {error_message}")
            return render(request, 'downloader/home.html', {
                'error': error_message,
                'video_url': video_url 
            })
            
        downloaded_file_path = None 
        # The download_hook is primarily for logging component file progress.
        # The final path will be determined by predicting the outtmpl path.
        def download_hook(d):
            if d['status'] == 'finished':
                logger.info(f"Download hook: Component file finished: {d['filename']}")
            elif d['status'] == 'error':
                logger.error(f"Download hook: yt-dlp component download error: {d.get('error', 'Unknown error')}")


        try:
            download_path = os.path.join(settings.MEDIA_ROOT, 'downloads')
            os.makedirs(download_path, exist_ok=True) 
            
            # --- Step 1: Get initial video info to predict the filename ---
            ydl_opts_info_for_filename = {
                'quiet': True,
                'simulate': True,
                'noplaylist': True,
                'force_generic_extractor': True,
            }
            
            info_dict = None
            with yt_dlp.YoutubeDL(ydl_opts_info_for_filename) as ydl_info:
                info_dict = ydl_info.extract_info(video_url, download=False)
                info_dict = info_dict.get('entries', [info_dict])[0] # Get actual video info

            if not info_dict:
                raise Exception("Could not retrieve video information for filename prediction.")

            # --- Step 2: Define download options, including outtmpl and merge format ---
            ydl_opts_download = {
                'format': f'{format_id}+bestaudio/bestvideo+bestaudio', 
                'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'), # This is the template for the output filename
                'noplaylist': True,
                'progress_hooks': [download_hook], 
                'nooverwrites': False,
                'quiet': False, 
                'verbose': True, 
                'merge_output_format': 'mp4', # Ensure merging to MP4 if separate streams are downloaded
                'keep_vids_on_error': True, 
                'cookiefile': os.path.join(settings.BASE_DIR, 'cookies.txt'), 
                'http_headers': { 
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.72 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Sec-Fetch-Mode': 'navigate',
                },
            }

            # --- Step 3: Predict the final filename using yt-dlp's prepare_filename ---
            # yt-dlp's prepare_filename is the most reliable way to get the exact output path.
            # For merged formats, the final extension comes from merge_output_format.
            # We temporarily override 'ext' in info_dict to ensure correct prediction.
            temp_info_dict = info_dict.copy()
            final_ext = ydl_opts_download.get('merge_output_format', temp_info_dict.get('ext', 'mp4'))
            temp_info_dict['ext'] = final_ext
            
            with yt_dlp.YoutubeDL(ydl_opts_download) as ydl_prep_filename:
                expected_file_path = ydl_prep_filename.prepare_filename(temp_info_dict)
            
            logger.info(f"Expected final download path: {expected_file_path}")

            # --- Step 4: Execute download with retries ---
            for attempt in range(3):
                try:
                    logger.info(f"Attempting download for {video_id} (format {format_id}), attempt {attempt + 1}")
                    with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
                        # ydl.download() returns 0 on success, 1 on error
                        result_code = ydl.download([video_url])
                        
                        if result_code != 0: 
                            raise Exception(f"yt-dlp download failed with code: {result_code}")
                    
                    # After successful download (result_code is 0), verify the predicted file exists
                    if os.path.exists(expected_file_path):
                        downloaded_file_path = expected_file_path # Set the actual path here
                        logger.info(f"File downloaded successfully to: {downloaded_file_path}")
                        
                        file_size = os.path.getsize(downloaded_file_path)
                        logger.info(f"Downloaded file size: {file_size} bytes")
                        if file_size == 0:
                            # If file exists but is 0 bytes, it's still an issue
                            raise Exception("Downloaded file is empty (0 bytes) after merge.")
                        break # Success, break out of retry loop
                    else:
                        raise Exception(f"Download finished, but expected file '{expected_file_path}' does not exist.")

                except yt_dlp.utils.DownloadError as e:
                    logger.warning(f"yt-dlp download attempt {attempt + 1} failed for {video_id} (format {format_id}): {str(e)}")
                    if "HTTP Error 400" in str(e) or "Too Many Requests" in str(e) or "HTTP Error 403" in str(e):
                        time.sleep(random.uniform(2, 5)) 
                    else:
                        time.sleep(random.uniform(1, 3))
                    if attempt == 2:
                        raise 
                except Exception as e: 
                    logger.warning(f"General download attempt {attempt + 1} failed for {video_id} (format {format_id}): {str(e)}")
                    time.sleep(random.uniform(1, 3))
                    if attempt == 2:
                        raise

            # --- Check if downloaded_file_path was successfully set after loop ---
            if not downloaded_file_path or not os.path.exists(downloaded_file_path):
                raise Exception("Failed to download video or confirm file path after all attempts.")

            # Determine content type and format type for database
            file_ext = os.path.splitext(downloaded_file_path)[1].lower().lstrip('.')
            content_type, _ = mimetypes.guess_type(downloaded_file_path)
            if content_type is None:
                content_type = 'application/octet-stream' 
            format_type = content_type 

            logger.info(f"Preparing to serve file: {downloaded_file_path} with content type: {content_type}")

            # Get video title for database record (can reuse info_dict from earlier)
            video_title = info_dict.get('title', 'Unknown Title')

            # Create download record
            download = TemporaryDownload.objects.create(
                video_url=video_url,
                video_title=video_title,
                file_path=downloaded_file_path,
                format_type=format_type
            )
            
            # Return file for download
            try:
                response = FileResponse(open(downloaded_file_path, 'rb'), content_type=content_type)
                response['Content-Disposition'] = f'attachment; filename="{os.path.basename(downloaded_file_path)}"'
                return response
            except FileNotFoundError:
                logger.error(f"File not found when trying to serve: {downloaded_file_path}")
                raise Http404("Downloaded file not found on server.")
            except Exception as e:
                logger.error(f"Error serving downloaded file: {e}")
                raise Exception(f"Failed to serve downloaded file: {e}")
                    
        except yt_dlp.utils.DownloadError as e:
            error = f"Download failed: {str(e)}"
            logger.error(f"Download error: {error}")
            return render(request, 'downloader/home.html', {
                'error': error,
                'video_url': video_url
            })
        except Exception as e:
            error = f"An unexpected error occurred during download: {str(e)}"
            logger.error(f"Download general error: {error}")
            return render(request, 'downloader/home.html', {
                'error': error,
                'video_url': video_url
            })
    
    return render(request, 'downloader/home.html')

# ... (convert_view and download_from_link remain the same)
def convert_view(request, download_id):
    cleanup_expired_downloads()
    download = get_object_or_404(TemporaryDownload, id=download_id)
    
    if download.is_expired():
        # Clean up expired file
        if os.path.exists(download.file_path):
            try:
                os.remove(download.file_path)
            except Exception as e:
                logger.error(f"Error cleaning up expired file {download.file_path}: {e}")
        download.delete() # Delete record from DB
        raise Http404("This download link has expired")
    
    if not os.path.exists(download.file_path):
        download.delete() # Delete record from DB if file is missing
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
            except Exception as e:
                logger.error(f"Error cleaning up expired file {download.file_path}: {e}")
        download.delete() # Delete record from DB
        raise Http404("This download link has expired")
    
    if not os.path.exists(download.file_path):
        download.delete() # Delete record from DB if file is missing
        raise Http404("File not found")
    
    response = FileResponse(
        open(download.file_path, 'rb'),
        content_type=download.format_type,
        as_attachment=True
    )
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(download.file_path)}"'
    return response
