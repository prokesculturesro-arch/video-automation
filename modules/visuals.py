"""
Stock footage downloader using Pexels API (FREE — 200 req/hour).
Downloads portrait-oriented video clips matching search queries.
Caches everything locally to avoid re-downloading.
Includes fallback generators when no footage is available.
"""

import hashlib
import json
import os
import re

import requests
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "cache", "footage")
CACHE_INDEX = os.path.join(CACHE_DIR, "_index.json")


def _ensure_dirs():
    os.makedirs(CACHE_DIR, exist_ok=True)


def _load_cache_index():
    """Load the download cache index."""
    if os.path.exists(CACHE_INDEX):
        with open(CACHE_INDEX, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache_index(index):
    """Save the download cache index."""
    with open(CACHE_INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


def _query_hash(query):
    """Hash a query string for cache keys."""
    return hashlib.md5(query.lower().strip().encode()).hexdigest()[:12]


def get_pexels_api_key():
    """Get Pexels API key from config."""
    import yaml
    config_path = os.path.join(BASE_DIR, "config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        key = config.get("visuals", {}).get("pexels", {}).get("api_key", "")
        if key:
            return key
    return os.environ.get("PEXELS_API_KEY", "")


def search_pexels(query, count=3, orientation="portrait", min_duration=5, max_duration=30):
    """
    Search Pexels for stock footage.

    Args:
        query: Search query
        count: Number of videos to return
        orientation: portrait, landscape, or square
        min_duration: Minimum video duration in seconds
        max_duration: Maximum video duration in seconds

    Returns:
        List of dicts with video info (id, url, duration, width, height)
    """
    api_key = get_pexels_api_key()
    if not api_key:
        print("   [Visuals] No Pexels API key — using fallback visuals")
        return []

    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": min(count * 3, 15),  # Fetch extra for filtering
        "orientation": orientation,
    }

    try:
        resp = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"   [Visuals] Pexels API error: {e}")
        return []

    results = []
    for video in data.get("videos", []):
        dur = video.get("duration", 0)
        if dur < min_duration or dur > max_duration:
            continue

        # Find best quality HD file in portrait orientation
        best_file = None
        for vf in video.get("video_files", []):
            w = vf.get("width", 0)
            h = vf.get("height", 0)
            if h >= 1080 and (best_file is None or h <= 1920):
                best_file = vf

        # Fallback to any file
        if not best_file and video.get("video_files"):
            best_file = video["video_files"][0]

        if best_file:
            results.append({
                "id": video["id"],
                "url": best_file["link"],
                "duration": dur,
                "width": best_file.get("width", 1080),
                "height": best_file.get("height", 1920),
                "quality": best_file.get("quality", "hd"),
            })

        if len(results) >= count:
            break

    return results


def download_video(url, output_path):
    """Download a video file from URL."""
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"   [Visuals] Download error: {e}")
        return False


def search_and_download(query, output_dir=None, count=3, orientation="portrait",
                        min_duration=5, max_duration=30):
    """
    Search Pexels and download matching clips. Uses cache.

    Args:
        query: Search query
        output_dir: Where to save (default: cache/footage/)
        count: Number of clips
        orientation: Video orientation
        min_duration: Min clip duration
        max_duration: Max clip duration

    Returns:
        List of local file paths to downloaded videos
    """
    _ensure_dirs()
    if output_dir is None:
        output_dir = CACHE_DIR

    os.makedirs(output_dir, exist_ok=True)

    # Check cache first
    cached = get_cached(query)
    if cached and len(cached) >= count:
        print(f"   [Visuals] Cache hit for '{query}': {len(cached)} clips")
        return cached[:count]

    # Search Pexels
    videos = search_pexels(query, count, orientation, min_duration, max_duration)

    if not videos:
        print(f"   [Visuals] No footage found for '{query}' — generating fallback")
        fallback = create_fallback_clip(query, duration=8)
        return [fallback] if fallback else []

    # Download each video
    index = _load_cache_index()
    q_hash = _query_hash(query)
    downloaded = []

    for i, video in enumerate(videos):
        filename = f"{q_hash}_{video['id']}.mp4"
        filepath = os.path.join(output_dir, filename)

        if os.path.exists(filepath):
            downloaded.append(filepath)
            continue

        print(f"   [Visuals] Downloading clip {i+1}/{len(videos)}...")
        if download_video(video["url"], filepath):
            downloaded.append(filepath)

    # Update cache index
    index[q_hash] = {
        "query": query,
        "files": downloaded,
    }
    _save_cache_index(index)

    return downloaded


def get_cached(query):
    """Check if footage for a query is already cached."""
    index = _load_cache_index()
    q_hash = _query_hash(query)
    entry = index.get(q_hash)

    if entry:
        # Verify files still exist
        valid = [f for f in entry.get("files", []) if os.path.exists(f)]
        if valid:
            return valid
    return None


def create_fallback_clip(text, duration=8, width=1080, height=1920, style="gradient"):
    """
    Create a fallback video clip when no stock footage is available.
    Generates an image sequence that will be used by the composer.

    Args:
        text: Text to display on the fallback
        duration: Duration indicator (used in filename)
        width: Frame width
        height: Frame height
        style: Visual style (gradient, solid, pattern)

    Returns:
        Path to generated fallback image
    """
    _ensure_dirs()
    h = hashlib.md5(text.encode()).hexdigest()[:10]
    img_path = os.path.join(CACHE_DIR, f"fallback_{h}.png")

    if os.path.exists(img_path):
        return img_path

    # Create gradient background
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    if style == "gradient":
        # Dark gradient background
        colors = [
            ((20, 20, 40), (40, 20, 60)),    # Deep purple
            ((10, 30, 50), (20, 50, 80)),     # Deep blue
            ((30, 20, 20), (60, 30, 30)),     # Deep red
            ((20, 30, 20), (30, 60, 40)),     # Deep green
        ]
        import random
        c_top, c_bot = random.choice(colors)

        for y in range(height):
            ratio = y / height
            r = int(c_top[0] + (c_bot[0] - c_top[0]) * ratio)
            g = int(c_top[1] + (c_bot[1] - c_top[1]) * ratio)
            b = int(c_top[2] + (c_bot[2] - c_top[2]) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
    else:
        draw.rectangle([0, 0, width, height], fill=(10, 10, 10))

    # Add text overlay
    try:
        font_path = os.path.join(BASE_DIR, "assets", "fonts", "Montserrat-Bold.ttf")
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, 52)
        else:
            font = ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    # Word wrap
    max_chars = 25
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line + " " + word) <= max_chars:
            current_line = (current_line + " " + word).strip()
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    # Draw text centered
    line_height = 65
    total_height = len(lines) * line_height
    y_start = (height - total_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (width - tw) // 2
        y = y_start + i * line_height

        # Shadow
        draw.text((x + 2, y + 2), line, fill=(0, 0, 0), font=font)
        # Main text
        draw.text((x, y), line, fill=(255, 255, 255), font=font)

    img.save(img_path, "PNG")
    print(f"   [Visuals] Created fallback image: {img_path}")
    return img_path


def download_free_music(mood="calm", output_dir=None):
    """
    Placeholder for free music download.
    Users should place .mp3 files in assets/music/ manually,
    or use Pixabay Music API if available.

    Args:
        mood: Music mood (calm, upbeat, dramatic, inspiring, funny)
        output_dir: Output directory

    Returns:
        Path to music file or None
    """
    if output_dir is None:
        output_dir = os.path.join(BASE_DIR, "assets", "music")

    os.makedirs(output_dir, exist_ok=True)

    # Check if any music files exist
    music_files = [
        f for f in os.listdir(output_dir)
        if f.endswith((".mp3", ".wav", ".ogg"))
    ]

    if music_files:
        # Return a random track
        import random
        return os.path.join(output_dir, random.choice(music_files))

    return None


if __name__ == "__main__":
    # Test fallback
    path = create_fallback_clip("Test fallback visual", duration=5)
    print(f"Fallback image: {path}")

    # Test Pexels search (only if API key is set)
    key = get_pexels_api_key()
    if key:
        results = search_and_download("nature peaceful", count=1)
        print(f"Downloaded: {results}")
    else:
        print("No Pexels API key set. Set in config.yaml or PEXELS_API_KEY env var.")
