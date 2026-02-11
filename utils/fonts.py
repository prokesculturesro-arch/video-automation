"""
Font loading utilities — shared across all renderers.
Extracted from chat_renderer.py, podcast_renderer.py, story_renderer.py.
"""

import os

from PIL import ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(BASE_DIR, "assets", "fonts")

# Cache loaded fonts to avoid repeated disk reads
_font_cache = {}


def get_font(size, bold=True, font_name=None):
    """
    Load a font at the given size with caching.

    Args:
        size: Font size in points
        bold: If True, use bold variant (default)
        font_name: Specific font filename (e.g. "Montserrat-Bold.ttf").
                   If None, auto-selects based on bold flag.

    Returns:
        PIL ImageFont instance
    """
    if font_name is None:
        font_name = "Montserrat-Bold.ttf" if bold else "Montserrat-Bold.ttf"

    cache_key = (font_name, size)
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    font_path = os.path.join(FONTS_DIR, font_name)
    try:
        if os.path.exists(font_path):
            font = ImageFont.truetype(font_path, size)
            _font_cache[cache_key] = font
            return font
    except Exception:
        pass

    font = ImageFont.load_default()
    _font_cache[cache_key] = font
    return font


def get_font_path(font_name="Montserrat-Bold"):
    """
    Get the full path to a font file.

    Args:
        font_name: Font name without extension

    Returns:
        Full path string, or None if not found
    """
    font_path = os.path.join(FONTS_DIR, f"{font_name}.ttf")
    if os.path.exists(font_path):
        return font_path
    return None
