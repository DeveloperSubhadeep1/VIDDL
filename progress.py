import time
import math


def human_readable_size(size_bytes: int | float) -> str:
    if not size_bytes:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


def human_readable_time(seconds: float) -> str:
    if not seconds or math.isnan(seconds) or seconds < 0:
        return "0s"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


def make_bar(percentage: float, total_blocks: int = 12) -> str:
    filled = max(0, min(total_blocks, round((percentage / 100) * total_blocks)))
    empty  = total_blocks - filled
    return "⬢" * filled + "⬡" * empty


def build_progress_string(
    index: int,
    title: str,
    status: str,
    percentage: float,
    current_bytes: int,
    total_bytes: int,
    speed_bps: float,
    start_time: float,
    user_mention: str = "N/A",
) -> str:
    elapsed_time = time.time() - start_time

    if speed_bps > 0 and total_bytes > current_bytes:
        eta_seconds = (total_bytes - current_bytes) / speed_bps
    else:
        eta_seconds = 0

    status_emoji = "📥" if status.lower() == "download" else "📤"
    bar_str      = make_bar(percentage)
    current_str  = human_readable_size(current_bytes)
    total_str    = human_readable_size(total_bytes)
    speed_str    = f"{human_readable_size(speed_bps)}/s" if speed_bps > 0 else "0 B/s"

    return (
        f"{status_emoji} **[{status}] Task #{index}**\n"
        f"📝 **Name:** `{title}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f" • [{bar_str}] {percentage:.1f}%\n"
        f" • **Done:** `{current_str}` of `{total_str}`\n"
        f" • **Speed:** `{speed_str}`\n"
        f" • **ETA:** `{human_readable_time(eta_seconds)}` | "
        f"**Elapsed:** `{human_readable_time(elapsed_time)}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Requested by:** {user_mention}"
    )