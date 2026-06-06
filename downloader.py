import asyncio
import glob
import os
import time

import yt_dlp
import yt_dlp.utils as _ydl_utils

from config import DOWNLOAD_DIR
from progress import build_progress_string

UnsupportedURLError = getattr(
    _ydl_utils, "UnsupportedError",
    getattr(_ydl_utils, "ExtractorError", Exception),
)


def _build_format(quality: str) -> str:
    q = quality
    return (
        f"bestvideo[height<={q}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={q}]+bestaudio/"
        f"best[height<={q}]/"
        f"bestvideo+bestaudio/"
        f"best"
    )


class DownloadProgress:
    def __init__(self, message, loop, index: int = 1, user_mention: str = "N/A"):
        self.message      = message
        self.loop         = loop
        self.index        = index
        self.user_mention = user_mention
        self.start_time   = time.time()
        self.last_edit    = 0.0

    def hook(self, d: dict):
        if d["status"] != "downloading":
            return

        now = time.time()
        if now - self.last_edit < 3:
            return
        self.last_edit = now

        title       = os.path.basename(d.get("filename", "Video"))
        total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        done_bytes  = d.get("downloaded_bytes", 0)
        speed       = d.get("speed") or 0
        percentage  = (done_bytes / total_bytes * 100) if total_bytes > 0 else 0

        text = build_progress_string(
            index         = self.index,
            title         = title,
            status        = "Download",
            percentage    = percentage,
            current_bytes = done_bytes,
            total_bytes   = total_bytes,
            speed_bps     = speed,
            start_time    = self.start_time,
            user_mention  = self.user_mention,
        )

        # Schedule the coroutine on the event loop from this sync thread.
        # We do NOT call .result() — fire-and-forget is intentional here;
        # a failed progress update should never abort the download.
        try:
            asyncio.run_coroutine_threadsafe(
                _safe_edit(self.message, text),
                self.loop,
            )
        except Exception:
            pass


async def _safe_edit(message, text: str):
    """Thin async wrapper so run_coroutine_threadsafe always receives a coroutine."""
    try:
        await message.edit_text(text)
    except Exception:
        pass


def _sync_download(url: str, quality: str, tracker: DownloadProgress) -> str:
    ydl_opts = {
        "format":              _build_format(quality),
        "outtmpl":             os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "progress_hooks":      [tracker.hook],
        "merge_output_format": "mp4",
        "quiet":               True,
        "no_warnings":         True,
        "ignoreerrors":        False,
        "retries":             5,
        "fragment_retries":    5,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        },
        "keepvideo": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if info is None:
            raise RuntimeError(f"yt-dlp returned no info for: {url}")

        requested = info.get("requested_downloads")
        if requested and requested[0].get("filepath"):
            fp = requested[0]["filepath"]
            if os.path.exists(fp):
                return fp

        raw_path = ydl.prepare_filename(info)
        stem     = os.path.splitext(os.path.basename(raw_path))[0]

        mp4_path = os.path.join(DOWNLOAD_DIR, stem + ".mp4")
        if os.path.exists(mp4_path):
            return mp4_path

        matches = sorted(
            glob.glob(os.path.join(DOWNLOAD_DIR, glob.escape(stem) + ".*")),
            key=os.path.getmtime,
            reverse=True,
        )
        if matches:
            return matches[0]

        return raw_path


async def download_video(
    url: str,
    quality: str,
    message,
    index: int = 1,
    user_mention: str = "N/A",
) -> str:
    loop    = asyncio.get_running_loop()
    tracker = DownloadProgress(message, loop, index, user_mention)
    return await loop.run_in_executor(
        None, _sync_download, url, quality, tracker
    )