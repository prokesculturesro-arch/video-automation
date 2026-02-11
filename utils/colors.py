"""
Color utilities — shared across subtitles, renderers, generators.
Extracted from subtitles.py, chat_renderer.py, podcast_renderer.py.
"""


def hex_to_rgb(hex_color):
    """
    Convert hex color string to RGB tuple.

    Args:
        hex_color: Color string like "#FFFFFF" or "FFFFFF"

    Returns:
        Tuple of (r, g, b) integers 0-255
    """
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r, g, b):
    """Convert RGB values to hex string."""
    return f"#{r:02x}{g:02x}{b:02x}"


def lerp_color(color1, color2, t):
    """
    Linear interpolation between two RGB colors.

    Args:
        color1: Start color (r, g, b)
        color2: End color (r, g, b)
        t: Interpolation factor 0.0 to 1.0

    Returns:
        Interpolated (r, g, b) tuple
    """
    t = max(0.0, min(1.0, t))
    return tuple(int(color1[i] + (color2[i] - color1[i]) * t) for i in range(3))


def parse_rgba(rgba_string):
    """
    Parse CSS-style rgba string to (r, g, b, a) tuple.

    Args:
        rgba_string: String like "rgba(0,0,0,0.6)"

    Returns:
        Tuple of (r, g, b, a) where a is 0-255
    """
    try:
        if rgba_string.startswith("rgba"):
            parts = rgba_string.replace("rgba(", "").replace(")", "").split(",")
            return (int(parts[0]), int(parts[1]), int(parts[2]),
                    int(float(parts[3]) * 255))
    except Exception:
        pass
    return (0, 0, 0, 150)


def draw_gradient(draw, width, height, color_top, color_bottom):
    """
    Draw a vertical gradient on a PIL ImageDraw.

    Args:
        draw: PIL ImageDraw instance
        width: Image width
        height: Image height
        color_top: Top color (r, g, b)
        color_bottom: Bottom color (r, g, b)
    """
    for y in range(height):
        c = lerp_color(color_top, color_bottom, y / height)
        draw.line([(0, y), (width, y)], fill=c)
