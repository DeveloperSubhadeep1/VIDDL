import asyncio
import glob
import os
import random
import time

import yt_dlp
import yt_dlp.utils as _ydl_utils

from config import DOWNLOAD_DIR, COOKIES_FILE
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


# ---------------------------------------------------------------------------
# Rotating user-agent pool — randomised per download to reduce bot detection
# ---------------------------------------------------------------------------
_USER_AGENTS = [
    # Chrome on Windows (generic, widely accepted)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome on Android — works well for Indian/Asian OTT apps
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.165 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.179 Mobile Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    # Chrome on Linux (Render servers run Linux)
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

# ---------------------------------------------------------------------------
# Geo-bypass strategy
#   SG (Singapore) → fewest globally banned sites, covers Indian + global OTT
#   IN (India)     → fallback for strict Indian-only content
#   US (USA)       → fallback for US-only content (YouTube, Twitch, Reddit)
#   NL (Netherlands) → open internet, good EU coverage
# yt-dlp rotates through these via X-Forwarded-For spoofing
# ---------------------------------------------------------------------------
_GEO_COUNTRIES = ["SG", "IN", "US", "NL"]


def _build_ydl_opts(quality: str, tracker: "DownloadProgress") -> dict:
    ua      = random.choice(_USER_AGENTS)
    country = random.choice(_GEO_COUNTRIES)   # rotate country per download

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
        "keepvideo":           False,

        # --- Geo-bypass: spoof X-Forwarded-For header ---
        # SG is default — least geo-blocked globally
        "geo_bypass":         True,
        "geo_bypass_country": country,

        # --- Rotating user-agent + neutral Accept-Language ---
        "http_headers": {
            "User-Agent":      ua,
            "Accept-Language": "en-SG,en;q=0.9,en-IN;q=0.8,en-US;q=0.7",
            "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        },

        # --- Extractor-specific overrides for Indian streaming sites ---
        "extractor_args": {
            # JioCinema: force Android app path (avoids the videoModel KeyError)
            "jiocinema": {"platform": ["android"]},
            # Hotstar: pass resolution directly
            "hotstar":   {"res": [quality]},
        },
    }

    # Load cookies.txt if it exists (optional — not required for most sites)
    if os.path.isfile(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE
        print(f"[downloader] cookies=ON  geo={country}  UA={ua[:45]}…")
    else:
        print(f"[downloader] cookies=OFF  geo={country}  UA={ua[:45]}…")

    return ydl_opts


def _sync_download(url: str, quality: str, tracker: "DownloadProgress") -> str:
    ydl_opts = _build_ydl_opts(quality, tracker)

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