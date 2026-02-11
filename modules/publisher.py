"""
Publisher module — upload videos to platforms.
Currently a placeholder. Requires platform credentials to be configured.

Supported platforms (when configured):
- YouTube (via YouTube Data API v3)
- TikTok (via cookies/selenium)
- Instagram (via instagrapi)
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def publish_to_youtube(video_path, title, description, tags, config):
    """Upload video to YouTube using Data API v3."""
    if not config.get("enabled"):
        print("   [Publisher] YouTube publishing not enabled")
        return None

    creds_file = config.get("credentials_file", "")
    if not creds_file or not os.path.exists(creds_file):
        print("   [Publisher] YouTube credentials file not found")
        return None

    print("   [Publisher] YouTube upload not yet implemented — save credentials first")
    return None


def publish_to_tiktok(video_path, description, tags, config):
    """Upload video to TikTok."""
    if not config.get("enabled"):
        print("   [Publisher] TikTok publishing not enabled")
        return None

    print("   [Publisher] TikTok upload not yet implemented")
    return None


def publish_to_instagram(video_path, caption, config):
    """Upload video to Instagram Reels."""
    if not config.get("enabled"):
        print("   [Publisher] Instagram publishing not enabled")
        return None

    print("   [Publisher] Instagram upload not yet implemented")
    return None


def publish(video_path, metadata, config):
    """
    Publish video to all enabled platforms.

    Args:
        video_path: Path to the video file
        metadata: Dict with title, description, tags, hashtags
        config: Publishing config from config.yaml

    Returns:
        Dict of platform → result
    """
    results = {}
    pub_config = config.get("publishing", {})

    title = metadata.get("title", "")
    description = metadata.get("description", "")
    tags = metadata.get("tags", [])
    hashtags = metadata.get("hashtags", [])

    caption = f"{description}\n\n{' '.join(hashtags)}"

    # YouTube
    if pub_config.get("youtube", {}).get("enabled"):
        results["youtube"] = publish_to_youtube(
            video_path, title, description, tags, pub_config["youtube"]
        )

    # TikTok
    if pub_config.get("tiktok", {}).get("enabled"):
        results["tiktok"] = publish_to_tiktok(
            video_path, caption, tags, pub_config["tiktok"]
        )

    # Instagram
    if pub_config.get("instagram", {}).get("enabled"):
        results["instagram"] = publish_to_instagram(
            video_path, caption, pub_config["instagram"]
        )

    if not results:
        print("   [Publisher] No publishing platforms enabled")

    return results
