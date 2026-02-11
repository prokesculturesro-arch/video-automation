"""
Chat/Message Renderer — WhatsApp/iMessage style animated conversation.

Creates frame-by-frame animation using Pillow:
- Chat bubbles appear one by one
- Typing indicator animation before each message
- Different sides for different speakers
- Smooth scroll as conversation grows
"""

import math
import os
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import (
    AudioFileClip, ImageClip, CompositeVideoClip,
    CompositeAudioClip, ColorClip, concatenate_audioclips, vfx,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Ensure FFmpeg is available
try:
    import imageio_ffmpeg
    import moviepy.config as mpy_config
    mpy_config.FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    pass

# ===== STYLE CONSTANTS =====
SCREEN_W = 1080
SCREEN_H = 1920
BG_COLOR = (17, 27, 33)        # Dark WhatsApp background
HEADER_H = 140                  # Top header height
HEADER_COLOR = (32, 44, 51)     # Header bg
BUBBLE_RADIUS = 20
BUBBLE_PADDING = 16
BUBBLE_MAX_W = 700              # Max bubble width
BUBBLE_MARGIN = 12              # Space between bubbles
NAME_FONT_SIZE = 28
MSG_FONT_SIZE = 36
TIME_FONT_SIZE = 22
TYPING_DOT_R = 8


def _get_font(size, bold=False):
    """Get font, fallback to default if custom not available."""
    font_name = "Montserrat-Bold.ttf" if bold else "Montserrat-Bold.ttf"
    font_path = os.path.join(BASE_DIR, "assets", "fonts", font_name)
    try:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except Exception:
        pass
    return ImageFont.load_default()


def _hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def _wrap_text(text, font, max_width, draw):
    """Word-wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    return lines if lines else [text]


def _calc_bubble_height(text, font, max_text_w, draw):
    """Calculate bubble height needed for wrapped text."""
    lines = _wrap_text(text, font, max_text_w, draw)
    line_h = font.size + 6
    text_h = len(lines) * line_h
    return text_h + BUBBLE_PADDING * 2 + NAME_FONT_SIZE + 12, lines


def _draw_header(draw, characters):
    """Draw the chat header bar."""
    # Header background
    draw.rectangle([0, 0, SCREEN_W, HEADER_H], fill=HEADER_COLOR)

    # Chat name
    names = [c for c in characters if c.lower() != "narrator"]
    title = " & ".join(names[:2])
    font = _get_font(34, bold=True)
    draw.text((80, 40), title, fill=(255, 255, 255), font=font)

    # Status
    font_small = _get_font(24)
    draw.text((80, 82), "online", fill=(128, 200, 128), font=font_small)

    # Back arrow
    draw.text((20, 45), "<", fill=(255, 255, 255), font=_get_font(36))

    # Separator line
    draw.line([(0, HEADER_H), (SCREEN_W, HEADER_H)], fill=(50, 60, 70), width=1)


def _draw_bubble(draw, x, y, width, height, color, side="left", radius=BUBBLE_RADIUS):
    """Draw a rounded rectangle chat bubble with tail."""
    r = radius
    color_rgb = _hex_to_rgb(color) if isinstance(color, str) else color

    # Rounded rectangle
    draw.rounded_rectangle([x, y, x + width, y + height], radius=r, fill=color_rgb)

    # Bubble tail (small triangle)
    tail_size = 10
    if side == "left":
        # Tail on left
        points = [
            (x, y + 15),
            (x - tail_size, y + 20),
            (x, y + 25),
        ]
    else:
        # Tail on right
        points = [
            (x + width, y + 15),
            (x + width + tail_size, y + 20),
            (x + width, y + 25),
        ]
    draw.polygon(points, fill=color_rgb)


def _draw_typing_indicator(draw, x, y, frame_num, color):
    """Draw animated typing dots."""
    color_rgb = _hex_to_rgb(color) if isinstance(color, str) else color
    bubble_w = 100
    bubble_h = 50

    _draw_bubble(draw, x, y, bubble_w, bubble_h, color_rgb, side="left")

    # Three bouncing dots
    for i in range(3):
        offset = math.sin((frame_num * 0.3) + i * 1.2) * 5
        dot_x = x + 25 + i * 22
        dot_y = y + 25 + int(offset)
        dot_alpha = 180 + int(offset * 15)
        draw.ellipse(
            [dot_x - TYPING_DOT_R, dot_y - TYPING_DOT_R,
             dot_x + TYPING_DOT_R, dot_y + TYPING_DOT_R],
            fill=(200, 200, 200),
        )


def render_single_frame(messages_to_show, characters, typing_char=None,
                         typing_frame=0, scroll_y=0):
    """
    Render a single frame of the chat conversation.

    Args:
        messages_to_show: List of message dicts to display
        characters: Character info dict
        typing_char: If set, show typing indicator for this character
        typing_frame: Animation frame for typing dots
        scroll_y: Vertical scroll offset

    Returns:
        numpy array (H, W, 3) RGB image
    """
    img = Image.new("RGB", (SCREEN_W, SCREEN_H), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Draw header
    _draw_header(draw, list(characters.keys()))

    msg_font = _get_font(MSG_FONT_SIZE)
    name_font = _get_font(NAME_FONT_SIZE, bold=True)
    time_font = _get_font(TIME_FONT_SIZE)

    max_text_w = BUBBLE_MAX_W - BUBBLE_PADDING * 2

    # Calculate all bubble positions
    current_y = HEADER_H + 30 - scroll_y

    for msg in messages_to_show:
        char_name = msg["character"]
        text = msg["text"]
        char_info = characters.get(char_name, {})
        colors = char_info.get("colors", CHARACTER_COLORS_DEFAULT)
        side = char_info.get("side", "left")

        # Calculate bubble size
        bubble_h, wrapped_lines = _calc_bubble_height(text, msg_font, max_text_w, draw)
        bubble_w = min(BUBBLE_MAX_W, max(
            max(draw.textbbox((0, 0), line, font=msg_font)[2] for line in wrapped_lines)
            + BUBBLE_PADDING * 2 + 20,
            200,
        ))

        # Position based on side
        if side == "left":
            bx = 30
        else:
            bx = SCREEN_W - bubble_w - 30

        # Only draw if visible
        if current_y + bubble_h > HEADER_H and current_y < SCREEN_H:
            # Draw bubble
            _draw_bubble(draw, bx, current_y, bubble_w, bubble_h,
                        colors.get("bubble", "#DCF8C6"), side)

            # Character name (first message or after other character)
            name_color = _hex_to_rgb(colors.get("name", "#25D366"))
            draw.text(
                (bx + BUBBLE_PADDING, current_y + 8),
                char_name,
                fill=name_color,
                font=name_font,
            )

            # Message text
            text_color = _hex_to_rgb(colors.get("text", "#000000"))
            text_y = current_y + NAME_FONT_SIZE + 16
            for line in wrapped_lines:
                draw.text(
                    (bx + BUBBLE_PADDING, text_y),
                    line,
                    fill=text_color,
                    font=msg_font,
                )
                text_y += msg_font.size + 6

        current_y += bubble_h + BUBBLE_MARGIN

    # Typing indicator
    if typing_char and typing_char in characters:
        char_info = characters[typing_char]
        side = char_info.get("side", "left")
        colors = char_info.get("colors", CHARACTER_COLORS_DEFAULT)
        tx = 30 if side == "left" else SCREEN_W - 130
        if current_y < SCREEN_H - 80:
            _draw_typing_indicator(draw, tx, current_y, typing_frame, colors["bubble"])

    return np.array(img)


# Default colors fallback
CHARACTER_COLORS_DEFAULT = {"bubble": "#DCF8C6", "text": "#000000", "name": "#25D366"}


def render_chat_video(parsed_conv, audio_lines, output_path, config):
    """
    Render a complete chat-style conversation video.

    Args:
        parsed_conv: Parsed conversation dict (characters, lines)
        audio_lines: List of audio results per line
        output_path: Output MP4 path
        config: Config dict

    Returns:
        Path to output video
    """
    W = config.get("video", {}).get("width", 1080)
    H = config.get("video", {}).get("height", 1920)
    FPS = config.get("video", {}).get("fps", 30)

    characters = parsed_conv["characters"]
    pause = 0.4  # Pause between messages
    typing_duration = 0.6  # Typing indicator duration

    # ===== Build timeline =====
    # For each line: typing indicator → message appears → audio plays → pause
    print("   [Chat] Building animation timeline...")

    timeline = []
    current_time = 0.5  # Start with small delay

    for i, audio_line in enumerate(audio_lines):
        char = audio_line["character"]

        # Typing indicator phase
        timeline.append({
            "type": "typing",
            "character": char,
            "start": current_time,
            "end": current_time + typing_duration,
            "messages_visible": i,  # Show messages 0..i-1
        })
        current_time += typing_duration

        # Message visible + audio playing
        timeline.append({
            "type": "message",
            "character": char,
            "text": audio_line["text"],
            "start": current_time,
            "end": current_time + audio_line["duration"],
            "messages_visible": i + 1,  # Show messages 0..i
            "audio_index": i,
        })
        current_time += audio_line["duration"] + pause

    total_duration = current_time + 1.0  # Extra second at end

    # ===== Build audio track =====
    print("   [Chat] Building audio track...")
    from moviepy import AudioClip

    # Create silence
    silence_path = os.path.join(BASE_DIR, "cache", "tts", "_silence.mp3")
    if not os.path.exists(silence_path):
        # Create a short silence using numpy
        import subprocess
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run(
            [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", "0.1", "-q:a", "9", silence_path],
            capture_output=True,
        )

    # Build audio timeline
    audio_clips = []
    for event in timeline:
        if event["type"] == "message" and "audio_index" in event:
            idx = event["audio_index"]
            clip = AudioFileClip(audio_lines[idx]["audio_path"])
            clip = clip.with_start(event["start"])
            audio_clips.append(clip)

    if audio_clips:
        final_audio = CompositeAudioClip(audio_clips)
    else:
        final_audio = None

    # ===== Render frames =====
    print(f"   [Chat] Rendering {total_duration:.1f}s of animation at {FPS} fps...")

    messages_data = []
    for line in audio_lines:
        messages_data.append({
            "character": line["character"],
            "text": line["text"],
        })

    def make_frame(t):
        """Generate frame at time t."""
        # Find current timeline event
        messages_visible = 0
        typing_char = None
        typing_frame = int(t * 10)

        for event in timeline:
            if event["start"] <= t < event["end"]:
                messages_visible = event["messages_visible"]
                if event["type"] == "typing":
                    typing_char = event["character"]
                break
            elif t >= event["end"]:
                messages_visible = max(messages_visible, event.get("messages_visible", 0))

        # Calculate scroll
        # If messages extend past screen, scroll down
        visible_msgs = messages_data[:messages_visible]
        total_msg_height = sum(100 for _ in visible_msgs)  # Approximate
        scroll_y = max(0, total_msg_height - (H - HEADER_H - 200))

        frame = render_single_frame(
            visible_msgs, characters,
            typing_char=typing_char,
            typing_frame=typing_frame,
            scroll_y=scroll_y,
        )

        return frame

    # Create video clip from frame function
    video_clip = ColorClip(size=(W, H), color=BG_COLOR).with_duration(total_duration)

    # Generate frames as ImageClips
    # We'll generate keyframes and hold them to optimize
    print("   [Chat] Generating keyframes...")
    frame_clips = []

    for event in timeline:
        # Render frame for this event
        if event["type"] == "typing":
            # Typing: generate several frames for dot animation
            num_typing_frames = max(1, int((event["end"] - event["start"]) * 8))
            frame_dur = (event["end"] - event["start"]) / num_typing_frames
            for f in range(num_typing_frames):
                visible = messages_data[:event["messages_visible"]]
                total_h = sum(100 for _ in visible)
                scroll = max(0, total_h - (H - HEADER_H - 200))
                frame = render_single_frame(
                    visible, characters,
                    typing_char=event["character"],
                    typing_frame=f * 3,
                    scroll_y=scroll,
                )
                clip = (
                    ImageClip(frame)
                    .with_duration(frame_dur)
                    .with_start(event["start"] + f * frame_dur)
                )
                frame_clips.append(clip)
        else:
            # Message: static frame for duration
            visible = messages_data[:event["messages_visible"]]
            total_h = sum(100 for _ in visible)
            scroll = max(0, total_h - (H - HEADER_H - 200))
            frame = render_single_frame(
                visible, characters,
                scroll_y=scroll,
            )
            clip = (
                ImageClip(frame)
                .with_duration(event["end"] - event["start"])
                .with_start(event["start"])
            )
            frame_clips.append(clip)

    # Add initial empty frame
    init_frame = render_single_frame([], characters)
    init_clip = ImageClip(init_frame).with_duration(0.5).with_start(0)
    frame_clips.insert(0, init_clip)

    # Add final frame (all messages visible)
    final_frame = render_single_frame(messages_data, characters)
    final_clip = (
        ImageClip(final_frame)
        .with_duration(1.0)
        .with_start(total_duration - 1.0)
    )
    frame_clips.append(final_clip)

    # Compose
    print("   [Chat] Composing final video...")
    final_video = CompositeVideoClip(frame_clips, size=(W, H))
    final_video = final_video.with_duration(total_duration)

    if final_audio:
        final_video = final_video.with_audio(final_audio)

    # Fade
    final_video = final_video.with_effects([vfx.FadeIn(0.3), vfx.FadeOut(0.5)])

    # Export
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"   [Chat] Exporting to {output_path}...")
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

    print(f"   [Chat] Done! {output_path}")
    return output_path
