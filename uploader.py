import time
import os
from progress import build_progress_string

async def upload_progress_hook(current, total, message, start_time, last_edit_wrapper, index, title, user_mention):
    now = time.time()
    if now - last_edit_wrapper[0] < 3:
        return
        
    last_edit_wrapper[0] = now
    elapsed = now - start_time
    
    speed = current / elapsed if elapsed > 0 else 0
    percentage = (current / total) * 100 if total > 0 else 0

    text = build_progress_string(
        index=index,
        title=title,
        status="Upload",
        percentage=percentage,
        current_bytes=current,
        total_bytes=total,
        speed_bps=speed,
        start_time=start_time,
        user_mention=user_mention  # <-- Passed user mention here
    )
    
    try:
        await message.edit_text(text)
    except Exception:
        pass

async def upload_video(chat_id, file_path, message, client, index=1, user_mention="N/A"):
    title = os.path.basename(file_path)
    start_time = time.time()
    last_edit_wrapper = [0] 
    total_size = os.path.getsize(file_path)

    await message.edit_text(f"{index}. {title}\n • Starting upload...")

    await client.send_video(
        chat_id=chat_id,
        video=file_path,
        caption=f"{title}",
        progress=upload_progress_hook,
        progress_args=(message, start_time, last_edit_wrapper, index, title, user_mention) # <-- Added user_mention to tuple
    )