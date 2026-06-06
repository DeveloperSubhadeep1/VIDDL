import asyncio
import os

import yt_dlp.utils as _ydl_utils

from config import MAX_QUEUE_SIZE, MAX_RETRIES, DOWNLOAD_DIR
from database import insert_or_update_video
from downloader import download_video, UnsupportedURLError
from uploader import upload_video

# Bounded queue — prevents memory exhaustion from huge batch uploads
download_queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)

# Module-level counter so task numbers survive handler restarts within a session
_task_counter = 0

# Errors that should NOT be retried (yt-dlp already handles internal retries)
_NO_RETRY_ERRORS = (
    UnsupportedURLError,
    _ydl_utils.DownloadError,
)


async def worker(client):
    global _task_counter

    while True:
        task = await download_queue.get()
        url          = task["url"]
        chat_id      = task["chat_id"]
        quality      = task["quality"]
        user_mention = task.get("user_mention", "N/A")
        attempt      = task.get("attempt", 1)

        _task_counter += 1
        index = _task_counter

        status_msg = await client.send_message(chat_id, "⏳ Initialising task…")
        file_path  = None

        try:
            # Phase 1 — Download
            await insert_or_update_video(url, {"status": "downloading"})
            file_path = await download_video(
                url, quality, status_msg,
                index=index, user_mention=user_mention,
            )

            # Phase 2 — Upload
            await insert_or_update_video(url, {"status": "uploading"})
            await upload_video(
                chat_id, file_path, status_msg, client,
                index=index, user_mention=user_mention,
            )

            # Phase 3 — Finalise
            await insert_or_update_video(url, {"status": "uploaded", "uploaded": True})
            await status_msg.delete()

        except _NO_RETRY_ERRORS as exc:
            # These errors won't benefit from retrying — fail immediately
            await insert_or_update_video(url, {"status": "failed"})
            msg = (
                "❌ This URL is not supported by yt-dlp.\n"
                "See supported sites: https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md"
                if isinstance(exc, UnsupportedURLError)
                else f"❌ Download failed:\n`{exc}`"
            )
            try:
                await status_msg.edit_text(msg)
            except Exception:
                pass

        except Exception as exc:
            print(f"[worker] attempt {attempt}/{MAX_RETRIES} failed for {url}: {exc}")

            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)
                await download_queue.put({**task, "attempt": attempt + 1})
                try:
                    await status_msg.edit_text(
                        f"⚠️ Error on attempt {attempt}/{MAX_RETRIES}. Retrying…\n`{exc}`"
                    )
                except Exception:
                    pass
            else:
                await insert_or_update_video(url, {"status": "failed"})
                try:
                    await status_msg.edit_text(
                        f"❌ Failed after {MAX_RETRIES} attempts.\n`{exc}`"
                    )
                except Exception:
                    pass

        finally:
            # Always clean up any partial file left on disk
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except OSError:
                    pass

            download_queue.task_done()


async def add_to_queue(
    url: str,
    chat_id: int,
    quality: str,
    user_mention: str = "N/A",
) -> bool:
    """Enqueue a download task. Returns False if the queue is full."""
    if download_queue.full():
        return False
    # Save all task fields to DB so they can be re-queued after a restart
    await insert_or_update_video(url, {
        "status":       "pending",
        "url":          url,
        "chat_id":      chat_id,
        "quality":      quality,
        "user_mention": user_mention,
    })
    await download_queue.put({
        "url":          url,
        "chat_id":      chat_id,
        "quality":      quality,
        "user_mention": user_mention,
        "attempt":      1,
    })
    return True