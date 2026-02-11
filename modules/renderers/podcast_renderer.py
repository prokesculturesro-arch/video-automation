"""
Podcast/Debate Renderer — two avatars side by side with speaker highlighting.

Visual layout:
- Dark background with gradient
- Two circular avatars in upper third
- Active speaker is highlighted (glow/scale)
- Subtitle text in lower third (word highlight style)
- Sound wave animation under active speaker
"""

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip, ImageClip, CompositeVideoClip,
    CompositeAudioClip, ColorClip, vfx,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import imageio_ffmpeg
    import moviepy.config as mpy_config
    mpy_config.FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    pass

SCREEN_W = 1080
SCREEN_H = 1920
AVATAR_SIZE = 220
AVATAR_Y = 400
AVATAR_GAP = 120


def _get_font(size, bold=False):
    font_path = os.path.join(BASE_DIR, "assets", "fonts", "Montserrat-Bold.ttf")
    try:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _draw_gradient_bg(draw, w, h, color_top=(15, 15, 35), color_bot=(5, 5, 15)):
    """Draw vertical gradient background."""
    for y in range(h):
        r = ratio = y / h
        c = tuple(int(color_top[i] + (color_bot[i] - color_top[i]) * r) for i in range(3))
        draw.line([(0, y), (w, y)], fill=c)


def _draw_avatar(draw, cx, cy, size, color, initial, active=False, glow_frame=0):
    """Draw a circular avatar with initial letter."""
    r = size // 2

    # Glow effect for active speaker
    if active:
        glow_r = r + 12 + int(math.sin(glow_frame * 0.15) * 4)
        glow_color = tuple(min(255, c + 60) for c in color)
        # Outer glow rings
        for gr in range(glow_r, r, -2):
            alpha = max(30, 120 - (gr - r) * 8)
            ring_color = tuple(min(255, c + alpha // 3) for c in color)
            draw.ellipse(
                [cx - gr, cy - gr, cx + gr, cy + gr],
                outline=ring_color, width=2,
            )

    # Main circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    # Border
    border_color = (255, 255, 255) if active else (100, 100, 100)
    border_w = 4 if active else 2
    draw.ellipse(
        [cx - r, cy - r, cx + r, cy + r],
        outline=border_color, width=border_w,
    )

    # Initial letter
    font = _get_font(size // 2, bold=True)
    bbox = draw.textbbox((0, 0), initial, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        (cx - tw // 2, cy - th // 2 - 5),
        initial,
        fill=(255, 255, 255),
        font=font,
    )


def _draw_waveform(draw, cx, cy, width, height, frame, active=False):
    """Draw animated sound waveform bars."""
    num_bars = 12
    bar_w = width // (num_bars * 2)
    bar_gap = bar_w

    if not active:
        # Flat line when not speaking
        for i in range(num_bars):
            x = cx - width // 2 + i * (bar_w + bar_gap)
            draw.rectangle(
                [x, cy - 1, x + bar_w, cy + 1],
                fill=(80, 80, 80),
            )
        return

    for i in range(num_bars):
        # Animated bar height
        bar_h = int(
            (math.sin(frame * 0.2 + i * 0.7) * 0.5 + 0.5) * height * 0.8
            + height * 0.2
        )
        x = cx - width // 2 + i * (bar_w + bar_gap)
        y_top = cy - bar_h // 2
        y_bot = cy + bar_h // 2

        # Color gradient on bar
        bar_color = (100, 200, 255) if active else (60, 60, 60)
        draw.rounded_rectangle(
            [x, y_top, x + bar_w, y_bot],
            radius=bar_w // 2,
            fill=bar_color,
        )


def _draw_subtitle_text(draw, text, y, w, active_word_idx=-1, frame=0):
    """Draw subtitle text with optional word highlighting."""
    font = _get_font(44)
    words = text.split()

    # Calculate total width
    space_w = draw.textlength(" ", font=font)
    word_widths = [draw.textlength(word, font=font) for word in words]
    total_w = sum(word_widths) + space_w * (len(words) - 1)

    # Wrap if needed
    if total_w > w * 0.85:
        # Simple wrap: split in half
        mid = len(words) // 2
        lines = [" ".join(words[:mid]), " ".join(words[mid:])]
    else:
        lines = [text]

    line_h = 55
    total_h = len(lines) * line_h
    current_y = y - total_h // 2

    word_count = 0
    for line in lines:
        line_words = line.split()
        lw = [draw.textlength(w, font=font) for w in line_words]
        ltw = sum(lw) + space_w * (len(line_words) - 1)
        x = (w - ltw) / 2

        for i, word in enumerate(line_words):
            is_active = (word_count == active_word_idx)

            if is_active:
                color = (255, 215, 0)  # Gold highlight
                f = _get_font(50, bold=True)
            else:
                color = (255, 255, 255)
                f = font

            # Stroke
            for dx in [-2, 0, 2]:
                for dy in [-2, 0, 2]:
                    if dx or dy:
                        draw.text((x + dx, current_y + dy), word, fill=(0, 0, 0), font=f)

            draw.text((x, current_y), word, fill=color, font=f)
            x += lw[i] + space_w
            word_count += 1

        current_y += line_h


def render_podcast_frame(characters_list, active_speaker, text, active_word_idx,
                          frame_num):
    """Render a single podcast frame."""
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient background
    _draw_gradient_bg(draw, SCREEN_W, SCREEN_H, (20, 20, 45), (8, 8, 20))

    # Title bar
    font_title = _get_font(30)
    draw.text((SCREEN_W // 2 - 80, 60), "PODCAST", fill=(120, 120, 140), font=font_title)

    # Draw avatars (max 2 for layout)
    avatar_positions = []
    num_chars = min(len(characters_list), 2)

    if num_chars == 1:
        positions = [(SCREEN_W // 2, AVATAR_Y)]
    else:
        positions = [
            (SCREEN_W // 2 - AVATAR_SIZE // 2 - AVATAR_GAP // 2, AVATAR_Y),
            (SCREEN_W // 2 + AVATAR_SIZE // 2 + AVATAR_GAP // 2, AVATAR_Y),
        ]

    for i, (cx, cy) in enumerate(positions):
        if i >= len(characters_list):
            break
        char = characters_list[i]
        is_active = (char["name"] == active_speaker)

        _draw_avatar(
            draw, cx, cy, AVATAR_SIZE,
            char.get("avatar_color", (100, 100, 200)),
            char["name"][0].upper(),
            active=is_active,
            glow_frame=frame_num,
        )

        # Name under avatar
        name_font = _get_font(28)
        bbox = draw.textbbox((0, 0), char["name"], font=name_font)
        nw = bbox[2] - bbox[0]
        name_color = (255, 255, 255) if is_active else (150, 150, 150)
        draw.text((cx - nw // 2, cy + AVATAR_SIZE // 2 + 20), char["name"],
                  fill=name_color, font=name_font)

        # Waveform under avatar
        _draw_waveform(
            draw, cx, cy + AVATAR_SIZE // 2 + 70,
            width=160, height=40,
            frame=frame_num, active=is_active,
        )

    # Divider line
    divider_y = AVATAR_Y + AVATAR_SIZE // 2 + 130
    draw.line(
        [(100, divider_y), (SCREEN_W - 100, divider_y)],
        fill=(40, 40, 60), width=2,
    )

    # Subtitle text area
    if text:
        subtitle_y = SCREEN_H * 0.55
        _draw_subtitle_text(draw, text, int(subtitle_y), SCREEN_W, active_word_idx, frame_num)

    return np.array(img)


def render_podcast_video(parsed_conv, audio_lines, output_path, config):
    """
    Render a complete podcast-style conversation video.
    """
    W = config.get("video", {}).get("width", 1080)
    H = config.get("video", {}).get("height", 1920)
    FPS = config.get("video", {}).get("fps", 30)

    characters = parsed_conv["characters"]
    char_list = list(characters.values())[:2]  # Max 2 speakers for podcast

    pause = 0.5
    print("   [Podcast] Building timeline...")

    # Build audio timeline
    audio_clips = []
    line_events = []
    current_time = 0.5

    for i, al in enumerate(audio_lines):
        line_events.append({
            "character": al["character"],
            "text": al["text"],
            "start": current_time,
            "end": current_time + al["duration"],
            "word_timestamps": al["word_timestamps"],
            "audio_index": i,
        })
        clip = AudioFileClip(al["audio_path"]).with_start(current_time)
        audio_clips.append(clip)
        current_time += al["duration"] + pause

    total_duration = current_time + 0.5

    if audio_clips:
        final_audio = CompositeAudioClip(audio_clips)
    else:
        final_audio = None

    # Render keyframes
    print(f"   [Podcast] Rendering {total_duration:.1f}s animation...")

    frame_clips = []
    frame_interval = 1.0 / 8  # 8 keyframes per second for smooth waveform

    for event in line_events:
        duration = event["end"] - event["start"]
        num_frames = max(1, int(duration / frame_interval))
        fd = duration / num_frames

        for f in range(num_frames):
            t = event["start"] + f * fd

            # Find active word
            active_word = -1
            for wi, wt in enumerate(event["word_timestamps"]):
                if wt["start"] <= (t - event["start"]) < wt["end"]:
                    active_word = wi
                    break

            frame = render_podcast_frame(
                char_list, event["character"], event["text"],
                active_word, int(t * 10),
            )

            clip = (
                ImageClip(frame)
                .with_duration(fd)
                .with_start(t)
            )
            frame_clips.append(clip)

    # Pause frames (no active speaker)
    # Add initial and final static frames
    init_frame = render_podcast_frame(char_list, "", "", -1, 0)
    frame_clips.insert(0, ImageClip(init_frame).with_duration(0.5).with_start(0))

    final_frame = render_podcast_frame(char_list, "", "", -1, 0)
    frame_clips.append(
        ImageClip(final_frame)
        .with_duration(0.5)
        .with_start(total_duration - 0.5)
    )

    # Compose
    print("   [Podcast] Composing final video...")
    final_video = CompositeVideoClip(frame_clips, size=(W, H))
    final_video = final_video.with_duration(total_duration)

    if final_audio:
        final_video = final_video.with_audio(final_audio)

    final_video = final_video.with_effects([vfx.FadeIn(0.3), vfx.FadeOut(0.5)])

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"   [Podcast] Exporting to {output_path}...")
    final_video.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        bitrate="4M",
        preset="medium",
        threads=4,
        logger="bar",
    )

    print(f"   [Podcast] Done! {output_path}")
    return output_path
