"""
Unified caching utilities.
Extracted from voiceover.py and visuals.py caching patterns.
"""

import hashlib
import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_ROOT = os.path.join(BASE_DIR, "cache")


def ensure_cache_dir(subdir=None):
    """
    Ensure a cache directory exists.

    Args:
        subdir: Subdirectory name (e.g. "tts", "footage", "images", "ai_video")
                If None, ensures root cache dir.

    Returns:
        Full path to the cache directory
    """
    if subdir:
        path = os.path.join(CACHE_ROOT, subdir)
    else:
        path = CACHE_ROOT
    os.makedirs(path, exist_ok=True)
    return path


def get_cache_path(key_string, subdir, extension=".mp3"):
    """
    Generate a deterministic cache file path from a key string.

    Args:
        key_string: String to hash for filename
        subdir: Cache subdirectory
        extension: File extension including dot

    Returns:
        Full file path in cache
    """
    h = hashlib.md5(key_string.encode("utf-8")).hexdigest()[:16]
    cache_dir = ensure_cache_dir(subdir)
    return os.path.join(cache_dir, f"{h}{extension}")


def is_cached(path):
    """Check if a cached file exists and is non-empty."""
    return os.path.exists(path) and os.path.getsize(path) > 0


def load_cache_index(subdir):
    """
    Load JSON cache index for a subdirectory.

    Args:
        subdir: Cache subdirectory name

    Returns:
        Dict from the index file, or empty dict
    """
    index_path = os.path.join(CACHE_ROOT, subdir, "_index.json")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache_index(subdir, index_data):
    """
    Save JSON cache index for a subdirectory.

    Args:
        subdir: Cache subdirectory name
        index_data: Dict to save
    """
    cache_dir = ensure_cache_dir(subdir)
    index_path = os.path.join(cache_dir, "_index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2)


def hash_string(s, length=12):
    """Generate MD5 hash of a string, truncated to length."""
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:length]
