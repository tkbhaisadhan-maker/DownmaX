"""Downmax download engine (powered by yt-dlp)."""
from __future__ import annotations

import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import yt_dlp
from yt_dlp.utils import DownloadCancelled

VIDEO_QUALITIES = {
    "Best available": None,
    "2160p (4K)": 2160,
    "1440p (2K)": 1440,
    "1080p (Full HD)": 1080,
    "720p (HD)": 720,
    "480p": 480,
    "360p": 360,
    "240p": 240,
}
AUDIO_BITRATES = ["128", "192", "256", "320"]


@dataclass
class DownloadOptions:
    url: str
    out_dir: str
    mode: str = "video"            # "video" or "mp3"
    quality: str = "Best available"  # key of VIDEO_QUALITIES
    audio_bitrate: str = "192"
    playlist: bool = False
    cookies_file: Optional[str] = None


def normalize_url(url: str) -> str:
    url = url.strip()
    if url and "://" not in url:
        url = "https://" + url
    return url


def format_duration(seconds) -> str:
    if not seconds:
        return "--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def human_size(num) -> str:
    if not num:
        return "--"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def ensure_ffmpeg() -> Optional[str]:
    """Return a directory containing ffmpeg (system one, or the bundled imageio one)."""
    found = shutil.which("ffmpeg")
    if found:
        return str(Path(found).parent)
    try:
        import imageio_ffmpeg
        src = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None
    target_dir = Path.home() / ".downmax" / "bin"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    try:
        if not target.exists() or target.stat().st_size != src.stat().st_size:
            shutil.copy2(src, target)
            os.chmod(target, 0o755)
    except OSError:
        return str(src.parent)
    return str(target_dir)


class _Logger:
    def __init__(self, cb: Callable[[str], None]):
        self.cb = cb

    def debug(self, msg):
        if msg.startswith("[debug]"):
            return
        if msg.startswith("[download] Destination") or msg.startswith("[Merger]") \
                or msg.startswith("[ExtractAudio]"):
            self.cb(msg)

    def info(self, msg):
        pass

    def warning(self, msg):
        self.cb("Warning: " + str(msg))

    def error(self, msg):
        self.cb("Error: " + str(msg))


def fetch_info(url: str, cookies_file: Optional[str] = None) -> dict:
    """Quickly get title / thumbnail / duration for a link."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
        "socket_timeout": 20,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(normalize_url(url), download=False)
    is_playlist = info.get("_type") == "playlist" or "entries" in info
    entries = list(info.get("entries") or []) if is_playlist else []
    thumb = info.get("thumbnail")
    if not thumb and info.get("thumbnails"):
        thumb = info["thumbnails"][-1].get("url")
    return {
        "title": info.get("title") or "Untitled",
        "uploader": info.get("uploader") or info.get("channel") or info.get("extractor_key") or "",
        "duration": info.get("duration"),
        "thumbnail": thumb,
        "is_playlist": is_playlist,
        "count": len(entries),
        "site": info.get("extractor_key") or "",
    }


class DownloadEngine:
    def __init__(self, on_progress: Callable[[float, str], None],
                 on_log: Callable[[str], None]):
        self.on_progress = on_progress
        self.on_log = on_log
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def _hook(self, d):
        if self.cancel_event.is_set():
            raise DownloadCancelled()
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            pct = (done / total * 100) if total else 0
            speed = d.get("speed")
            eta = d.get("eta")
            text = f"{pct:.1f}%  •  {human_size(done)} / {human_size(total)}"
            if speed:
                text += f"  •  {human_size(speed)}/s"
            if eta is not None:
                text += f"  •  ETA {format_duration(eta)}"
            self.on_progress(pct / 100, text)
        elif status == "finished":
            self.on_progress(1.0, "Processing file (merging / converting)…")

    def _build_opts(self, o: DownloadOptions) -> dict:
        out_dir = Path(o.out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        if o.playlist:
            tmpl = "%(playlist_title).80s/%(playlist_index)03d - %(title).100s.%(ext)s"
        else:
            tmpl = "%(title).120s.%(ext)s"
        opts = {
            "outtmpl": str(out_dir / tmpl),
            "noplaylist": not o.playlist,
            "progress_hooks": [self._hook],
            "logger": _Logger(self.on_log),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "retries": 10,
            "fragment_retries": 10,
            "concurrent_fragment_downloads": 4,
            "windowsfilenames": True,
            "socket_timeout": 30,
            "ignoreerrors": o.playlist,   # skip broken items inside playlists
        }
        ffmpeg_dir = ensure_ffmpeg()
        if ffmpeg_dir:
            opts["ffmpeg_location"] = ffmpeg_dir
        if o.cookies_file:
            opts["cookiefile"] = o.cookies_file

        if o.mode == "mp3":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                 "preferredquality": o.audio_bitrate},
                {"key": "FFmpegMetadata"},
            ]
        else:
            h = VIDEO_QUALITIES.get(o.quality)
            if h:
                opts["format"] = f"bv*[height<={h}]+ba/b[height<={h}]/b"
            else:
                opts["format"] = "bv*+ba/b"
            opts["merge_output_format"] = "mp4"
            opts["format_sort"] = ["res", "vcodec:h264", "acodec:aac"]
            opts["postprocessors"] = [{"key": "FFmpegMetadata"}]
        return opts

    def run(self, o: DownloadOptions) -> str:
        """Blocking. Returns 'done', 'cancelled' or raises on error."""
        self.cancel_event.clear()
        url = normalize_url(o.url)
        opts = self._build_opts(o)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                code = ydl.download([url])
            if self.cancel_event.is_set():
                return "cancelled"
            if code != 0 and not o.playlist:
                raise RuntimeError("Download failed. Check the log for details.")
            return "done"
        except DownloadCancelled:
            return "cancelled"
        except yt_dlp.utils.DownloadError as e:
            if self.cancel_event.is_set():
                return "cancelled"
            raise RuntimeError(_friendly_error(str(e)))


def _friendly_error(msg: str) -> str:
    low = msg.lower()
    if "login" in low or "private" in low or "cookies" in low or "sign in" in low:
        return ("This video needs login / is private. Export your browser cookies "
                "(cookies.txt) and select them in 'Cookies file'.\n\n" + msg)
    if "unsupported url" in low or "no video" in low:
        return "No downloadable video found at this link.\n\n" + msg
    if "ffmpeg" in low:
        return "FFmpeg is missing. Install FFmpeg or run: pip install imageio-ffmpeg\n\n" + msg
    return msg
