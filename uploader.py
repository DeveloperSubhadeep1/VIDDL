import os
import time
from collections import deque

from config import MAX_FILE_SIZE_GB
from progress import build_progress_string

# Telegram bot file-size hard limit
_MAX_BYTES = int(MAX_FILE_SIZE_GB * 1024 ** 3)

# Sliding-window size for speed calculation
_WINDOW = 4


async def upload_progress_hook(
    current: int,
    total: int,
    message,
    start_time: float,
    last_edit_ref: list,
    window: deque,
    index: int,
    title: str,
    user_mention: str,
):
    now = time.time()
    if now - last_edit_ref[0] < 3:
        return
    last_edit_ref[0] = now

    # Sliding-window speed: Δbytes / Δtime over last _WINDOW samples
    window.append((now, current))
    if len(window) >= 2:
        t0, b0 = window[0]
        dt = now - t0
        speed = (current - b0) / dt if dt > 0 else 0
    else:
        elapsed = now - start_time
        speed   = current / elapsed if elapsed > 0 else 0

    percentage = (current / total * 100) if total > 0 else 0

    text = build_progress_string(
        index         = index,
        title         = title,
        status        = "Upload",
        percentage    = percentage,
        current_bytes = current,
        total_bytes   = total,
        speed_bps     = speed,
        start_time    = start_time,
        user_mention  = user_mention,
    )

    try:
        await message.edit_text(text)
    except Exception:
        pass


async def upload_video(
    chat_id: int,
    file_path: str,
    message,
    client,
    index: int = 1,
    user_mention: str = "N/A",
):
    title      = os.path.basename(file_path)
    total_size = os.path.getsize(file_path)

    # Guard: reject files that exceed Telegram's bot upload limit
    if total_size > _MAX_BYTES:
        size_gb = total_size / 1024 ** 3
        await message.edit_text(
            f"❌ File too large ({size_gb:.2f} GB). "
            f"Telegram bots cannot send files larger than {MAX_FILE_SIZE_GB} GB."
        )
        return

    start_time    = time.time()
    last_edit_ref = [0.0]
    window        = deque(maxlen=_WINDOW)

    await message.edit_text(f"📤 Starting upload: `{title}`")

    await client.send_video(
        chat_id       = chat_id,
        video         = file_path,
        caption       = f"✅ **{title}**\n👤 Requested by: {user_mention}",
        progress      = upload_progress_hook,
        progress_args = (
            message, start_time, last_edit_ref, window,
            index, title, user_mention,
        ),
    )