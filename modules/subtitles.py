"""
Auto-generate animated subtitles from TTS word timestamps.
Supports multiple styles: word_highlight, karaoke, classic.

word_highlight: TikTok viral style — shows 3-5 words, current word pops with color.
karaoke: Full sentence visible, words highlight left-to-right.
classic: Standard subtitle blocks appear/disappear with timing.
"""

import os

from moviepy import ImageClip, TextClip
from PIL import Image, ImageDraw, ImageFont
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_font_path(font_name="Montserrat-Bold"):
    """Get font path, return None if not found (will use default)."""
    font_path = os.path.join(BASE_DIR, "assets", "fonts", f"{font_name}.ttf")
    if os.path.exists(font_path):
        return font_path
    return None


def _group_words(word_timestamps, words_per_group=4):
    """
    Group word timestamps into display groups.

    Args:
        word_timestamps: List of {word, start, end} dicts
        words_per_group: Number of words per subtitle group

    Returns:
        List of groups, each containing words, start, end
    """
    groups = []
    for i in range(0, len(word_timestamps), words_per_group):
        group = word_timestamps[i:i + words_per_group]
        if group:
            groups.append({
                "words": group,
                "start": group[0]["start"],
                "end": group[-1]["end"],
            })
    return groups


def create_word_highlight_frame(words, active_index, width, height,
                                 font_path=None, font_size=48,
                                 color="#FFFFFF", highlight_color="#FFD700",
                                 stroke_color="#000000", stroke_width=3,
                                 bg_color=None):
    """
    Create a single subtitle frame with word highlighting using Pillow.
    Returns numpy array (H, W, 4) RGBA image.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Load font
    try:
        if font_path and os.path.exists(font_path):
            font = ImageFont.truetype(font_path, font_size)
            font_big = ImageFont.truetype(font_path, int(font_size * 1.15))
        else:
            font = ImageFont.load_default()
            font_big = font
    except Exception:
        font = ImageFont.load_default()
        font_big = font

    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    text_color = hex_to_rgb(color)
    hi_color = hex_to_rgb(highlight_color)
    s_color = hex_to_rgb(stroke_color)

    # Calculate total text width for centering
    word_widths = []
    space_width = draw.textlength(" ", font=font)
    for i, word in enumerate(words):
        f = font_big if i == active_index else font
        w = draw.textlength(word, font=f)
        word_widths.append(w)

    total_width = sum(word_widths) + space_width * (len(words) - 1)
    x_start = (width - total_width) / 2
    y_center = height / 2

    # Optional background pill
    if bg_color:
        pad_x, pad_y = 20, 12
        pill_left = x_start - pad_x
        pill_right = x_start + total_width + pad_x
        pill_top = y_center - font_size / 2 - pad_y
        pill_bottom = y_center + font_size / 2 + pad_y
        draw.rounded_rectangle(
            [pill_left, pill_top, pill_right, pill_bottom],
            radius=15,
            fill=bg_color,
        )

    # Draw words
    x = x_start
    for i, word in enumerate(words):
        is_active = (i == active_index)
        f = font_big if is_active else font
        c = hi_color if is_active else text_color

        bbox = f.getbbox(word)
        text_h = bbox[3] - bbox[1]
        y = y_center - text_h / 2

        # Stroke / outline
        if stroke_width > 0:
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), word, fill=(*s_color, 255), font=f)

        # Main text
        draw.text((x, y), word, fill=(*c, 255), font=f)

        x += word_widths[i] + space_width

    return np.array(img)


def create_subtitle_clips_word_highlight(word_timestamps, video_width, video_height,
                                          config=None):
    """
    Create TikTok-style word-by-word highlight subtitle clips.

    Returns list of MoviePy ImageClip overlays.
    """
    if config is None:
        config = {}

    words_per_line = config.get("words_per_line", 4)
    font_size = config.get("font_size", 48)
    color = config.get("color", "#FFFFFF")
    highlight_color = config.get("highlight_color", "#FFD700")
    position = config.get("position", "bottom")
    bg = config.get("background", "rgba(0,0,0,0.6)")

    font_path = _get_font_path()
    subtitle_height = 120

    # Parse background color
    bg_color = None
    if bg and bg != "none":
        try:
            if bg.startswith("rgba"):
                parts = bg.replace("rgba(", "").replace(")", "").split(",")
                bg_color = (int(parts[0]), int(parts[1]), int(parts[2]),
                           int(float(parts[3]) * 255))
            else:
                bg_color = (0, 0, 0, 150)
        except Exception:
            bg_color = (0, 0, 0, 150)

    # Y position
    if position == "center":
        y_pos = video_height // 2 - subtitle_height // 2
    elif position == "top":
        y_pos = int(video_height * 0.15)
    else:  # bottom
        y_pos = int(video_height * 0.75)

    # Group words
    groups = _group_words(word_timestamps, words_per_line)

    clips = []

    for group in groups:
        group_words = [w["word"] for w in group["words"]]

        for word_idx, word_data in enumerate(group["words"]):
            w_start = word_data["start"]
            w_end = word_data["end"]

            # Create frame with this word highlighted
            frame = create_word_highlight_frame(
                words=group_words,
                active_index=word_idx,
                width=video_width,
                height=subtitle_height,
                font_path=font_path,
                font_size=font_size,
                color=color,
                highlight_color=highlight_color,
                bg_color=bg_color,
            )

            # Determine duration
            if word_idx < len(group["words"]) - 1:
                duration = group["words"][word_idx + 1]["start"] - w_start
            else:
                duration = w_end - w_start

            duration = max(duration, 0.05)

            # Create ImageClip from numpy array (MoviePy 2.x)
            clip = (
                ImageClip(frame, is_mask=False)
                .with_duration(duration)
                .with_start(w_start)
                .with_position((0, y_pos))
            )

            clips.append(clip)

    return clips


def create_subtitle_clips_classic(word_timestamps, video_width, video_height, config=None):
    """
    Create classic subtitle style — text blocks that appear and disappear.
    """
    if config is None:
        config = {}

    font_size = config.get("font_size", 44)
    color = config.get("color", "white")
    words_per_line = config.get("words_per_line", 6)
    position = config.get("position", "bottom")

    font_path = _get_font_path()

    groups = _group_words(word_timestamps, words_per_line)

    clips = []
    for group in groups:
        text = " ".join(w["word"] for w in group["words"])
        start = group["start"]
        end = group["end"]
        duration = max(end - start, 0.3)

        try:
            clip = (
                TextClip(
                    text=text,
                    font_size=font_size,
                    color=color,
                    font=font_path or "Arial",
                    stroke_color="black",
                    stroke_width=2,
                    method="caption",
                    size=(int(video_width * 0.85), None),
                )
                .with_duration(duration)
                .with_start(start)
                .with_position(("center", "bottom" if position == "bottom" else "center"))
            )
            clips.append(clip)
        except Exception as e:
            print(f"   [Subtitles] Warning: Could not create text clip: {e}")
            continue

    return clips


def create_subtitles(word_timestamps, video_width, video_height, config=None):
    """
    Main entry point — creates subtitle clips based on configured style.
    """
    if config is None:
        config = {}

    if not word_timestamps:
        return []

    style = config.get("style", "word_highlight")

    if style == "word_highlight":
        return create_subtitle_clips_word_highlight(
            word_timestamps, video_width, video_height, config
        )
    elif style == "karaoke":
        extended_config = {**config, "words_per_line": 8}
        return create_subtitle_clips_word_highlight(
            word_timestamps, video_width, video_height, extended_config
        )
    else:
        return create_subtitle_clips_classic(
            word_timestamps, video_width, video_height, config
        )
