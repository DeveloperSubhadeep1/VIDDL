import asyncio
import os
import threading


import asyncio

# 👇 FIX FOR PYTHON 3.14+ ASYNCIO BREAKING CHANGES
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())


import pyrogram
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask, jsonify
from aiohttp import web
import psutil
import shutil

from config import API_ID, API_HASH, BOT_TOKEN, MAX_BATCH_URLS
from database import (
    get_video,
    reset_stuck_downloads,
    insert_or_update_video,
    links_collection,
    ensure_indexes,
    generate_url_hash,
    get_pending_downloads,
)
from queue_manager import worker, add_to_queue, download_queue

app = Client("leech_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quality_buttons(url_hash: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("360p",  callback_data=f"dl|360|{url_hash}"),
            InlineKeyboardButton("720p",  callback_data=f"dl|720|{url_hash}"),
            InlineKeyboardButton("1080p", callback_data=f"dl|1080|{url_hash}"),
        ]
    ])


def _status_payload() -> dict:
    ram  = psutil.virtual_memory()
    cpu  = psutil.cpu_percent()
    total, used, _ = shutil.disk_usage("/")
    return {
        "status":     "online",
        "queue":      {"current": download_queue.qsize(), "max": download_queue.maxsize},
        "cpu_pct":    cpu,
        "ram_mb":     {"used": ram.used // 1024 // 1024, "total": ram.total // 1024 // 1024, "pct": ram.percent},
        "disk_gb":    {"used": round(used / 1024**3, 2), "total": round(total / 1024**3, 2)},
    }


# ---------------------------------------------------------------------------
# Flask — runs in a daemon thread (sync, port 8080)
# Koyeb routes external HTTP traffic here
# ---------------------------------------------------------------------------

_flask = Flask(__name__)


@_flask.route("/")
@_flask.route("/health")
def flask_health():
    d = _status_payload()
    return jsonify(d), 200


@_flask.route("/ping")
def flask_ping():
    return "pong", 200


def _run_flask():
    port = int(os.environ.get("PORT", "8080"))
    print(f"[Flask] Listening on port {port}")
    _flask.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ---------------------------------------------------------------------------
# aiohttp — runs inside the asyncio event loop (port 8081)
# Internal async health endpoint; also useful for inter-service calls
# ---------------------------------------------------------------------------

async def _aiohttp_health(request: web.Request) -> web.Response:
    import json
    d = _status_payload()
    return web.Response(
        text=json.dumps(d, indent=2),
        content_type="application/json",
    )


async def _aiohttp_ping(request: web.Request) -> web.Response:
    return web.Response(text="pong")


async def start_aiohttp_server():
    aio_app = web.Application()
    aio_app.router.add_get("/",       _aiohttp_health)
    aio_app.router.add_get("/health", _aiohttp_health)
    aio_app.router.add_get("/ping",   _aiohttp_ping)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    aio_port = int(os.environ.get("AIOHTTP_PORT", "8081"))
    site = web.TCPSite(runner, "0.0.0.0", aio_port)
    await site.start()
    print(f"[aiohttp] Listening on port {aio_port}")


# ---------------------------------------------------------------------------
# Link handler
# ---------------------------------------------------------------------------

@app.on_message(filters.regex(r"https?://[^\s]+"))
async def handle_link(client, message):
    url      = message.text.strip()
    url_hash = generate_url_hash(url)

    await insert_or_update_video(url, {"url": url, "url_hash": url_hash})

    video = await get_video(url)
    if video and video.get("status") == "uploaded":
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬇️ Download again", callback_data=f"redownload|{url_hash}")],
            [InlineKeyboardButton("Skip",              callback_data="skip")],
        ])
        await message.reply_text(
            "✅ This video was already uploaded. Download again?",
            reply_markup=buttons,
        )
        return

    await message.reply_text("Select quality:", reply_markup=_quality_buttons(url_hash))


# ---------------------------------------------------------------------------
# Quality selection
# ---------------------------------------------------------------------------

@app.on_callback_query(filters.regex(r"^dl\|"))
async def handle_quality_selection(client, callback_query):
    _, quality, url_hash = callback_query.data.split("|", 2)

    video = await links_collection.find_one({"url_hash": url_hash})
    if not video:
        await callback_query.answer(
            "❌ Session expired — please resend the link.", show_alert=True
        )
        return

    url          = video["url"]
    chat_id      = callback_query.message.chat.id
    user_mention = callback_query.from_user.mention if callback_query.from_user else "User"

    queued = await add_to_queue(url, chat_id, quality, user_mention=user_mention)
    if queued:
        pos = download_queue.qsize()
        await callback_query.message.edit_text(
            f"✅ Added to queue at position {pos} ({quality}p)."
        )
    else:
        await callback_query.answer(
            "⚠️ Queue is full. Please try again shortly.", show_alert=True
        )


# ---------------------------------------------------------------------------
# Redownload / skip
# ---------------------------------------------------------------------------

@app.on_callback_query(filters.regex(r"^redownload\|"))
async def handle_redownload(client, callback_query):
    _, url_hash = callback_query.data.split("|", 1)
    video = await links_collection.find_one({"url_hash": url_hash})
    if not video:
        await callback_query.answer("❌ Link data lost.", show_alert=True)
        return
    await callback_query.message.edit_text(
        "Select quality:", reply_markup=_quality_buttons(url_hash)
    )


@app.on_callback_query(filters.regex(r"^skip$"))
async def handle_skip(client, callback_query):
    await callback_query.message.delete()


# ---------------------------------------------------------------------------
# Bulk .txt upload
# ---------------------------------------------------------------------------

@app.on_message(filters.document & filters.private)
async def handle_txt_file(client, message):
    if not message.document.file_name.endswith(".txt"):
        return

    file_path = await message.download()
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            all_urls = [line.strip() for line in f if line.strip().startswith("http")]
    finally:
        os.remove(file_path)

    if not all_urls:
        await message.reply_text("No valid URLs found in the file.")
        return

    if len(all_urls) > MAX_BATCH_URLS:
        await message.reply_text(
            f"⚠️ File contains {len(all_urls)} URLs. "
            f"Only the first {MAX_BATCH_URLS} will be queued."
        )
        all_urls = all_urls[:MAX_BATCH_URLS]

    user_mention = message.from_user.mention if message.from_user else "User"
    queued = skipped = 0

    for url in all_urls:
        ok = await add_to_queue(url, message.chat.id, "720", user_mention=user_mention)
        if ok:
            queued += 1
        else:
            skipped += 1

    reply = f"📋 Queued **{queued}** links at 720p."
    if skipped:
        reply += f"\n⚠️ {skipped} link(s) skipped — queue is full."
    await message.reply_text(reply)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    await message.reply_text(
        f"👋 **Hello {message.from_user.first_name}!**\n\n"
        "I'm a high-speed Video Leech Bot.\n\n"
        "**How to use:**\n"
        "1️⃣ Send a supported video link (YouTube, Vimeo, TikTok, etc.).\n"
        "2️⃣ Choose your preferred quality.\n"
        "3️⃣ Or upload a `.txt` file with multiple links for bulk queuing.\n\n"
        "Use /help for more details."
    )


@app.on_message(filters.command("help") & filters.private)
async def help_command(client, message):
    await message.reply_text(
        "📖 **Usage guide**\n\n"
        "**Single video:** paste a URL directly — the bot will show quality options.\n\n"
        "**Bulk batch:** upload a `.txt` file (one URL per line). "
        f"Up to {MAX_BATCH_URLS} links per file, processed at 720p.\n\n"
        "**System status:** /system — shows CPU, RAM, disk, and queue length."
    )


@app.on_message(filters.command("system") & filters.private)
async def system_command(client, message):
    d = _status_payload()
    await message.reply_text(
        "🖥️ **System status**\n\n"
        f"⚙️ **CPU:** {d['cpu_pct']}%\n"
        f"🧠 **RAM:** {d['ram_mb']['used']} MB / {d['ram_mb']['total']} MB ({d['ram_mb']['pct']}%)\n"
        f"💽 **Disk:** {d['disk_gb']['used']} GB / {d['disk_gb']['total']} GB\n"
        f"📥 **Queue:** {d['queue']['current']} / {d['queue']['max']} tasks"
    )


# ---------------------------------------------------------------------------
# Startup cleanup
# ---------------------------------------------------------------------------

def purge_incomplete_downloads():
    """
    Wipe everything in DOWNLOAD_DIR at boot time.
    Any file present on startup is either:
      - a partial yt-dlp fragment (.part / .ytdl) from a crash mid-download
      - a fully downloaded file that was never uploaded (bot killed mid-upload)
    Both are stale and safe to delete. yt-dlp will re-download fresh on retry.
    """
    from config import DOWNLOAD_DIR
    removed = 0
    errors  = 0
    try:
        entries = os.listdir(DOWNLOAD_DIR)
    except FileNotFoundError:
        return  # folder doesn't exist yet — nothing to clean

    for name in entries:
        path = os.path.join(DOWNLOAD_DIR, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
                removed += 1
            elif os.path.isdir(path):
                shutil.rmtree(path)
                removed += 1
        except OSError as e:
            print(f"[cleanup] Could not remove {path}: {e}")
            errors += 1

    suffix = f" ({errors} error(s))" if errors else ""
    print(f"[cleanup] Removed {removed} leftover file(s) from downloads folder{suffix}.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def requeue_pending_downloads():
    """
    On restart, fetch all URLs that were pending/stuck from the previous session
    and push them back into the in-memory asyncio.Queue so the worker picks them up.
    Only re-queues entries that have a chat_id saved (i.e. came from a real user request).
    """
    pending = await get_pending_downloads()
    requeued = 0
    skipped  = 0
    for doc in pending:
        chat_id = doc.get("chat_id")
        url     = doc.get("url")
        if not chat_id or not url:
            skipped += 1
            continue  # no chat_id means we can't notify anyone — skip
        quality      = doc.get("quality", "720")
        user_mention = doc.get("user_mention", "N/A")
        ok = await add_to_queue(url, chat_id, quality, user_mention=user_mention)
        if ok:
            requeued += 1
        else:
            skipped += 1
    print(f"[requeue] Restored {requeued} pending task(s) to queue"
          + (f" ({skipped} skipped — no chat_id or queue full)" if skipped else "") + ".")


async def main():
    print("Purging incomplete downloads from previous session…")
    purge_incomplete_downloads()

    print("Setting up database indexes…")
    await ensure_indexes()

    print("Resetting stuck downloads…")
    await reset_stuck_downloads()

    print("Re-queuing pending downloads from previous session…")
    await requeue_pending_downloads()

    print("Starting Flask server (port 8080)…")
    threading.Thread(target=_run_flask, daemon=True).start()

    print("Starting aiohttp server (port 8081)…")
    await start_aiohttp_server()

    print("Starting queue worker…")
    asyncio.create_task(worker(app))

    print("Starting bot…")
    await app.start()

    print("Bot is online.")
    await idle()


if __name__ == "__main__":
    app.run(main())
