"""
AI Image Generation module — placeholder for Stable Diffusion API integration.
Can be used as alternative/supplement to stock footage.

Free options:
- Stable Diffusion via local install (requires GPU)
- Pollinations.ai (free, no API key)
- Craiyon (free, slow)
"""

import os
import hashlib
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "cache", "images")


def _ensure_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)


def generate_image_pollinations(prompt, width=1080, height=1920):
    """
    Generate an image using Pollinations.ai (free, no API key needed).

    Args:
        prompt: Text description of the image
        width: Image width
        height: Image height

    Returns:
        Path to saved image or None
    """
    _ensure_cache()

    h = hashlib.md5(f"{prompt}_{width}_{height}".encode()).hexdigest()[:12]
    output_path = os.path.join(CACHE_DIR, f"gen_{h}.png")

    if os.path.exists(output_path):
        return output_path

    try:
        # Pollinations.ai — free image generation
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
        params = {"width": width, "height": height}

        print(f"   [ImageGen] Generating image: {prompt[:50]}...")
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(resp.content)

        print(f"   [ImageGen] Saved to {output_path}")
        return output_path

    except Exception as e:
        print(f"   [ImageGen] Error: {e}")
        return None


def generate_image(prompt, width=1080, height=1920, provider="pollinations"):
    """
    Generate an AI image.

    Args:
        prompt: Image description
        width: Width in pixels
        height: Height in pixels
        provider: Which service to use

    Returns:
        Path to image file or None
    """
    if provider == "pollinations":
        return generate_image_pollinations(prompt, width, height)
    else:
        print(f"   [ImageGen] Unknown provider: {provider}")
        return None
