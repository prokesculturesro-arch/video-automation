"""
Story/Drama Renderer — cinematic scenes with characters and speech bubbles.

Visual layout:
- Full-screen background (gradient scenes that change per speaker)
- Character avatar on speaking side
- Speech bubble with animated text
- Narrator text appears centered with dramatic styling
- Scene transitions between speakers
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

# Scene color themes
SCENE_THEMES = [
    {"bg_top": (25, 25, 50), "bg_bot": (10, 10, 25), "accent": (100, 180, 255)},
    {"bg_top": (40, 20, 30), "bg_bot": (15, 8, 12), "accent": (255, 120, 160)},
    {"bg_top": (20, 35, 25), "bg_bot": (8, 15, 10), "accent": (120, 255, 160)},
    {"bg_top": (35, 30, 20), "bg_bot": (12, 10, 5), "accent": (255, 200, 100)},
    {"bg_top": (30, 20, 40), "bg_bot": (10, 8, 15), "accent": (200, 140, 255)},
]


def _get_font(size, bold=False):
    font_path = os.path.join(BASE_DIR, "assets", "fonts", "Montserrat-Bold.ttf")
    try:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def _draw_gradient(draw, w, h, c_top, c_bot):
    for y in range(h):
        r = y / h
        c = tuple(int(c_top[i] + (c_bot[i] - c_top[i]) * r) for i in range(3))
        draw.line([(0, y), (w, y)], fill=c)


def _draw_character_avatar(draw, cx, cy, size, color, initial, glow=False, frame=0):
    """Draw character avatar with optional glow."""
    r = size // 2

    if glow:
        # Animated glow
        for gr in range(r + 20, r, -3):
            alpha_frac = 1 - (gr - r) / 20
            glow_c = tuple(min(255, int(c * alpha_frac * 0.5)) for c in color)
            draw.ellipse([cx - gr, cy - gr, cx + gr, cy + gr], fill=glow_c)

    # Main circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(255, 255, 255), width=3)

    # Initial
    font = _get_font(size // 2)
    bbox = draw.textbbox((0, 0), initial, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2 - 3), initial, fill=(255, 255, 255), font=font)


def _draw_speech_bubble(draw, x, y, text, max_w, side="left", accent=(255, 255, 255)):
    """Draw a cinematic speech bubble."""
    font = _get_font(38)

    # Word wrap
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_w - 40:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    line_h = 48
    text_h = len(lines) * line_h
    bubble_h = text_h + 36
    bubble_w = max_w

    # Semi-transparent bubble background
    bubble_color = (20, 20, 30, 200)
    draw.rounded_rectangle(
        [x, y, x + bubble_w, y + bubble_h],
        radius=18,
        fill=(20, 20, 30),
    )

    # Accent border on left/right
    if side == "left":
        draw.rounded_rectangle(
            [x, y, x + 5, y + bubble_h],
            radius=3,
            fill=accent,
        )
    else:
        draw.rounded_rectangle(
            [x + bubble_w - 5, y, x + bubble_w, y + bubble_h],
            radius=3,
            fill=accent,
        )

    # Draw text
    text_y = y + 18
    for line in lines:
        draw.text((x + 20, text_y), line, fill=(240, 240, 240), font=font)
        text_y += line_h

    return bubble_h


def _draw_narrator_text(draw, text, y, w, frame=0):
    """Draw cinematic narrator text — centered, italic feel."""
    font = _get_font(44, bold=True)

    # Word wrap
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= w * 0.8:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    line_h = 56
    total_h = len(lines) * line_h

    # Background bar
    bar_y = y - 20
    bar_h = total_h + 40
    draw.rectangle(
        [0, bar_y, w, bar_y + bar_h],
        fill=(0, 0, 0),
    )
    # Gradient edges
    for i in range(20):
        alpha = int(255 * (1 - i / 20))
        c = (0, 0, 0)
        draw.line([(0, bar_y - i), (w, bar_y - i)], fill=c)
        draw.line([(0, bar_y + bar_h + i), (w, bar_y + bar_h + i)], fill=c)

    current_y = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2

        # Shadow
        draw.text((x + 2, current_y + 2), line, fill=(0, 0, 0), font=font)
        # Gold/white text
        draw.text((x, current_y), line, fill=(255, 215, 100), font=font)
        current_y += line_h


def render_story_frame(characters, active_char, text, scene_idx, frame_num,
                        is_narrator=False):
    """Render a single story frame."""
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Scene background
    theme = SCENE_THEMES[scene_idx % len(SCENE_THEMES)]
    _draw_gradient(draw, SCREEN_W, SCREEN_H, theme["bg_top"], theme["bg_bot"])

    # Decorative particles/stars
    import random
    random.seed(scene_idx * 100 + frame_num // 30)
    for _ in range(30):
        sx = random.randint(0, SCREEN_W)
        sy = random.randint(0, SCREEN_H)
        sr = random.randint(1, 3)
        brightness = random.randint(40, 120)
        draw.ellipse(
            [sx - sr, sy - sr, sx + sr, sy + sr],
            fill=(brightness, brightness, brightness + 20),
        )

    if is_narrator:
        # Narrator: centered dramatic text
        _draw_narrator_text(draw, text, SCREEN_H // 2 - 50, SCREEN_W, frame_num)
    else:
        # Character scene
        char_info = characters.get(active_char, {})
        avatar_color = char_info.get("avatar_color", (100, 100, 200))
        side = char_info.get("side", "left")

        # Avatar position
        if side == "left":
            avatar_cx = 180
            bubble_x = 60
        else:
            avatar_cx = SCREEN_W - 180
            bubble_x = SCREEN_W // 2 - 200

        avatar_cy = 500

        # Draw avatar
        _draw_character_avatar(
            draw, avatar_cx, avatar_cy, 200,
            avatar_color, active_char[0].upper(),
            glow=True, frame=frame_num,
        )

        # Character name
        name_font = _get_font(32, bold=True)
        bbox = draw.textbbox((0, 0), active_char, font=name_font)
        nw = bbox[2] - bbox[0]
        draw.text(
            (avatar_cx - nw // 2, avatar_cy + 120),
            active_char,
            fill=theme["accent"],
            font=name_font,
        )

        # Speech bubble
        bubble_y = 700
        bubble_max_w = SCREEN_W - 120
        _draw_speech_bubble(
            draw, 60, bubble_y, text, bubble_max_w,
            side=side, accent=theme["accent"],
        )

    # Scene number indicator (subtle)
    scene_font = _get_font(20)
    draw.text(
        (SCREEN_W - 80, SCREEN_H - 60),
        f"Scene {scene_idx + 1}",
        fill=(60, 60, 60),
        font=scene_font,
    )

    return np.array(img)


def render_story_video(parsed_conv, audio_lines, output_path, config):
    """
    Render a complete story-style conversation video.
    """
    W = config.get("video", {}).get("width", 1080)
    H = config.get("video", {}).get("height", 1920)
    FPS = config.get("video", {}).get("fps", 30)

    characters = parsed_conv["characters"]
    pause = 0.8  # Longer pauses for dramatic effect

    print("   [Story] Building timeline...")

    audio_clips = []
    line_events = []
    current_time = 1.0  # Dramatic pause at start

    for i, al in enumerate(audio_lines):
        is_narrator = al["character"].lower() in ("narrator",)
        line_events.append({
            "character": al["character"],
            "text": al["text"],
            "start": current_time,
            "end": current_time + al["duration"],
            "is_narrator": is_narrator,
            "scene_idx": i,
        })
        clip = AudioFileClip(al["audio_path"]).with_start(current_time)
        audio_clips.append(clip)
        current_time += al["duration"] + pause

    total_duration = current_time + 1.0

    if audio_clips:
        final_audio = CompositeAudioClip(audio_clips)
    else:
        final_audio = None

    # Render
    print(f"   [Story] Rendering {total_duration:.1f}s of scenes...")

    frame_clips = []

    # Initial black frame
    init_frame = render_story_frame(characters, "", "", 0, 0, is_narrator=True)
    # Make it mostly black
    init_img = Image.new("RGB", (W, H), (5, 5, 10))
    frame_clips.append(
        ImageClip(np.array(init_img)).with_duration(1.0).with_start(0)
    )

    for event in line_events:
        duration = event["end"] - event["start"]
        # Render a few frames for subtle animation
        num_frames = max(1, int(duration / 0.15))
        fd = duration / num_frames

        for f in range(num_frames):
            t = event["start"] + f * fd
            frame = render_story_frame(
                characters, event["character"], event["text"],
                event["scene_idx"], int(t * 10),
                is_narrator=event["is_narrator"],
            )
            clip = ImageClip(frame).with_duration(fd).with_start(t)
            frame_clips.append(clip)

    # Final frame
    end_img = Image.new("RGB", (W, H), (5, 5, 10))
    draw = ImageDraw.Draw(end_img)
    font = _get_font(48, bold=True)
    draw.text((W // 2 - 180, H // 2), "The End", fill=(200, 200, 200), font=font)
    frame_clips.append(
        ImageClip(np.array(end_img))
        .with_duration(1.0)
        .with_start(total_duration - 1.0)
    )

    # Compose
    print("   [Story] Composing final video...")
    final_video = CompositeVideoClip(frame_clips, size=(W, H))
    final_video = final_video.with_duration(total_duration)

    if final_audio:
        final_video = final_video.with_audio(final_audio)

    final_video = final_video.with_effects([vfx.FadeIn(0.5), vfx.FadeOut(1.0)])

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"   [Story] Exporting to {output_path}...")
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

    print(f"   [Story] Done! {output_path}")
    return output_path
