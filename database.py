import hashlib
from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URI, DB_NAME

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]
links_collection = db.links
hash_collection  = db.link_hashes


def generate_url_hash(url: str) -> str:
    """Full 32-char MD5 hex digest — consistent across all modules."""
    return hashlib.md5(url.encode()).hexdigest()


async def ensure_indexes() -> None:
    """Create indexes on first startup. Safe to call repeatedly (no-op if they exist)."""
    await links_collection.create_index("url",      unique=True, background=True)
    await links_collection.create_index("url_hash",              background=True)
    await hash_collection.create_index( "url",                   background=True)


async def save_url_mapping(url: str) -> str:
    url_hash = generate_url_hash(url)
    await hash_collection.update_one(
        {"_id": url_hash},
        {"$set": {"url": url}},
        upsert=True,
    )
    return url_hash


async def get_url_from_hash(url_hash: str) -> str | None:
    doc = await hash_collection.find_one({"_id": url_hash})
    return doc["url"] if doc else None


async def get_video(url: str):
    return await links_collection.find_one({"url": url})


async def insert_or_update_video(url: str, data: dict):
    await links_collection.update_one(
        {"url": url},
        {"$set": data},
        upsert=True,
    )


async def reset_stuck_downloads():
    await links_collection.update_many(
        {"status": {"$in": ["downloading", "downloaded", "uploading"]}},
        {"$set": {"status": "pending"}},
    )


async def get_pending_downloads() -> list[dict]:
    """
    Return all documents that are pending restart re-queue.
    Includes anything stuck mid-download/upload (reset to pending by reset_stuck_downloads)
    as well as anything that was pending before the bot shut down.
    Each document is expected to have at least: url, chat_id, quality, user_mention.
    """
    cursor = links_collection.find(
        {"status": "pending"},
        {"url": 1, "chat_id": 1, "quality": 1, "user_mention": 1, "_id": 0}
    )
    return await cursor.to_list(length=None)