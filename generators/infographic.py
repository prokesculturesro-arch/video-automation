"""
Infographic Engine — animated charts, statistics, comparisons.

Returns animated CompositeVideoClip objects (frame-by-frame at 10 FPS).
Charts include: bar chart, pie chart, statistics, comparison, process.
"""

import json
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from moviepy import ImageClip, CompositeVideoClip

from utils.fonts import get_font
from utils.colors import hex_to_rgb, lerp_color, draw_gradient
from utils.animation import (
    ease_out_cubic, ease_in_out_cubic, ease_out_quad,
    ease_out_bounce, smooth_step, interpolate,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

SCREEN_W = 1080
SCREEN_H = 1920
ANIM_FPS = 10

# Color palette for charts
CHART_COLORS = [
    (255, 215, 0),    # Gold
    (100, 200, 255),  # Sky blue
    (255, 120, 160),  # Pink
    (120, 255, 160),  # Green
    (200, 140, 255),  # Purple
    (255, 180, 100),  # Orange
]


def _load_layouts():
    """Load infographic layout configs."""
    path = os.path.join(TEMPLATES_DIR, "infographic_layouts.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


class InfographicRenderer:
    """
    Renders animated infographic visuals.

    All chart types return CompositeVideoClip objects with frame-by-frame animation.

    Chart types:
      - bar_chart: Horizontal bars growing from left
      - pie_chart: Pie slices drawn clockwise
      - statistics: Numbers counting up
      - comparison: Items sliding in from sides
      - process: Steps appearing top to bottom
    """

    def __init__(self, width=SCREEN_W, height=SCREEN_H):
        self.width = width
        self.height = height
        self.layouts = _load_layouts()

    def render_for_scene(self, scene):
        """
        Render animated infographic for a scene.

        Returns CompositeVideoClip (not a file path).
        """
        chart_type = scene.visual_params.get("chart_type", "statistics")
        title = scene.visual_params.get("title", scene.text_overlay or "")
        data_label = scene.visual_params.get("data_label", scene.visual_prompt)
        duration = max(2.0, scene.duration)

        render_map = {
            "bar_chart": self.render_bar_chart_animated,
            "pie_chart": self.render_pie_chart_animated,
            "statistics": self.render_statistics_animated,
            "comparison": self.render_comparison_animated,
            "process": self.render_process_animated,
        }

        renderer = render_map.get(chart_type, self.render_statistics_animated)

        try:
            clip = renderer(title, data_label, duration, scene.visual_params)
            print(f"   [Infographic] Animated {chart_type} ({duration:.1f}s)")
            return clip
        except Exception as e:
            print(f"   [Infographic] Error rendering {chart_type}: {e}")
            return None

    # ─── BAR CHART ────────────────────────────────────────────────

    def render_bar_chart_animated(self, title, data_label, duration, params=None):
        """Bar chart — bars grow from left with stagger."""
        params = params or {}
        items = params.get("items", self._generate_chart_items(data_label))
        num_bars = min(len(items), 5)
        items = items[:num_bars]

        title_text = title or "Statistics"
        max_val = max(item["value"] for item in items) if items else 100

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames
        bar_stagger = 0.3  # seconds between bar starts
        bar_anim_dur = 0.6  # seconds per bar animation

        frame_clips = []
        for f in range(total_frames):
            t = f * frame_dur

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, (15, 15, 35), (5, 5, 15))

            # Title
            title_font = get_font(44)
            bbox = draw.textbbox((0, 0), title_text, font=title_font)
            tw = bbox[2] - bbox[0]
            draw.text(((self.width - tw) // 2, 200), title_text,
                      fill=(255, 255, 255), font=title_font)

            bar_area_top = 350
            bar_area_height = 900
            bar_h = bar_area_height // (num_bars * 2)
            bar_gap = bar_h
            max_bar_w = int(self.width * 0.65)

            label_font = get_font(30)
            value_font = get_font(28)

            # Subtle gridlines
            for x_frac in [0.25, 0.5, 0.75]:
                gx = int(60 + max_bar_w * x_frac)
                draw.line([(gx, bar_area_top), (gx, bar_area_top + bar_area_height)],
                          fill=(40, 40, 60), width=1)

            for i, item in enumerate(items):
                bar_start = i * bar_stagger
                bar_progress = (t - bar_start) / bar_anim_dur if t > bar_start else 0.0
                bar_progress = max(0.0, min(1.0, bar_progress))
                anim_progress = ease_out_cubic(bar_progress)

                y = bar_area_top + i * (bar_h + bar_gap)
                target_bar_w = int((item["value"] / max_val) * max_bar_w)
                bar_w = int(target_bar_w * anim_progress)
                color = CHART_COLORS[i % len(CHART_COLORS)]

                # Label
                label_alpha = int(255 * min(1.0, bar_progress * 2))
                label_color = (
                    int(200 * label_alpha / 255),
                    int(200 * label_alpha / 255),
                    int(220 * label_alpha / 255),
                )
                draw.text((60, y - 5), item["label"], fill=label_color, font=label_font)

                # Bar
                if bar_w > 2:
                    bar_y = y + 35
                    draw.rounded_rectangle(
                        [60, bar_y, 60 + bar_w, bar_y + bar_h],
                        radius=bar_h // 3,
                        fill=color,
                    )

                    # Value text
                    shown_val = int(item["value"] * anim_progress)
                    draw.text((70 + bar_w, bar_y + 5), f'{shown_val}%',
                              fill=(255, 255, 255), font=value_font)

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── PIE CHART ────────────────────────────────────────────────

    def render_pie_chart_animated(self, title, data_label, duration, params=None):
        """Pie chart — slices drawn clockwise sequentially."""
        params = params or {}
        items = params.get("items", self._generate_chart_items(data_label))
        total_val = sum(item["value"] for item in items)

        title_text = title or "Distribution"
        cx = self.width // 2
        cy = 650
        outer_r = 220
        inner_r = 120

        # Calculate per-slice timing
        slice_dur = 0.5  # seconds per slice
        total_slice_time = len(items) * slice_dur

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames

        frame_clips = []
        for f in range(total_frames):
            t = f * frame_dur

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, (15, 15, 35), (5, 5, 15))

            # Title
            title_font = get_font(44)
            bbox = draw.textbbox((0, 0), title_text, font=title_font)
            tw = bbox[2] - bbox[0]
            draw.text(((self.width - tw) // 2, 200), title_text,
                      fill=(255, 255, 255), font=title_font)

            # Draw pie slices
            start_angle = -90
            cumulative_time = 0.0
            legend_items = []

            for i, item in enumerate(items):
                target_sweep = (item["value"] / total_val) * 360
                slice_start = cumulative_time
                slice_progress = (t - slice_start) / slice_dur if t > slice_start else 0.0
                slice_progress = max(0.0, min(1.0, slice_progress))

                anim_sweep = target_sweep * ease_out_cubic(slice_progress)
                color = CHART_COLORS[i % len(CHART_COLORS)]

                if anim_sweep > 0.5:
                    draw.pieslice(
                        [cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r],
                        start=start_angle,
                        end=start_angle + anim_sweep,
                        fill=color,
                    )

                if slice_progress > 0:
                    legend_items.append((i, item, slice_progress))

                start_angle += target_sweep
                cumulative_time += slice_dur

            # Donut hole
            draw.ellipse(
                [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
                fill=(15, 15, 35),
            )

            # Center text
            center_font = get_font(48)
            draw.text((cx - 30, cy - 25), "100%", fill=(255, 255, 255), font=center_font)

            # Legend
            legend_y = cy + outer_r + 80
            legend_font = get_font(28)
            for i, item, progress in legend_items:
                color = CHART_COLORS[i % len(CHART_COLORS)]
                lx = 100 + (i % 2) * (self.width // 2 - 50)
                ly = legend_y + (i // 2) * 60
                alpha = int(255 * min(1.0, progress))

                draw.rectangle([lx, ly + 5, lx + 20, ly + 25], fill=color)
                lbl_color = (int(200 * alpha / 255), int(200 * alpha / 255), int(220 * alpha / 255))
                draw.text((lx + 35, ly), f'{item["label"]} ({item["value"]}%)',
                          fill=lbl_color, font=legend_font)

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── STATISTICS ───────────────────────────────────────────────

    def render_statistics_animated(self, title, data_label, duration, params=None):
        """Statistics — numbers count up with stagger, labels fade in after."""
        params = params or {}
        title_text = title or "Key Statistics"

        stats = params.get("stats", [
            {"number": "87", "label": "of people agree", "suffix": "%"},
            {"number": "3", "label": "more effective", "suffix": "x"},
            {"number": "10", "label": "users worldwide", "suffix": "M+"},
        ])

        stat_stagger = 1.0  # seconds between stat starts

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames

        frame_clips = []
        for f in range(total_frames):
            t = f * frame_dur

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, (10, 15, 35), (5, 5, 15))

            # Title
            title_font = get_font(40)
            bbox = draw.textbbox((0, 0), title_text, font=title_font)
            tw = bbox[2] - bbox[0]
            draw.text(((self.width - tw) // 2, 200), title_text,
                      fill=(200, 200, 220), font=title_font)

            num_font = get_font(96)
            label_font = get_font(30)
            stat_gap = 300
            start_y = 400

            for i, stat in enumerate(stats[:4]):
                stat_start = i * stat_stagger
                stat_progress = (t - stat_start) / 1.5 if t > stat_start else 0.0
                stat_progress = max(0.0, min(1.0, stat_progress))

                y = start_y + i * stat_gap

                # Parse number
                try:
                    target_num = int(stat["number"])
                except (ValueError, TypeError):
                    target_num = 0

                suffix = stat.get("suffix", "")
                count_progress = ease_out_cubic(min(1.0, stat_progress / 0.7)) if stat_progress > 0 else 0.0
                current_num = int(target_num * count_progress)

                if target_num > 0:
                    num_text = f"{current_num}{suffix}"
                else:
                    num_text = str(stat["number"]) if stat_progress > 0.1 else ""

                if num_text:
                    bbox = draw.textbbox((0, 0), num_text, font=num_font)
                    tw = bbox[2] - bbox[0]
                    x = (self.width - tw) // 2
                    alpha = int(255 * min(1.0, stat_progress * 2))
                    color = CHART_COLORS[i % len(CHART_COLORS)]
                    c = tuple(int(v * alpha / 255) for v in color)

                    draw.text((x + 3, y + 3), num_text, fill=(0, 0, 0), font=num_font)
                    draw.text((x, y), num_text, fill=c, font=num_font)

                # Label fades in after number
                label_text = stat.get("label", data_label)
                if stat_progress > 0.7:
                    label_progress = (stat_progress - 0.7) / 0.3
                    label_alpha = int(200 * ease_in_out_cubic(min(1.0, label_progress)))
                    bbox = draw.textbbox((0, 0), label_text, font=label_font)
                    tw = bbox[2] - bbox[0]
                    x = (self.width - tw) // 2
                    draw.text((x, y + 110), label_text,
                              fill=(label_alpha, label_alpha, label_alpha), font=label_font)

                # Divider
                if i < len(stats) - 1 and stat_progress > 0.5:
                    div_y = y + 200
                    div_alpha = int(60 * min(1.0, (stat_progress - 0.5) / 0.5))
                    draw.line(
                        [(self.width * 0.2, div_y), (self.width * 0.8, div_y)],
                        fill=(div_alpha, div_alpha, div_alpha + 20), width=1,
                    )

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── COMPARISON ───────────────────────────────────────────────

    def render_comparison_animated(self, title, data_label, duration, params=None):
        """Comparison — items slide in from sides, VS badge pops in center."""
        params = params or {}
        title_text = title or "Comparison"
        left_items = params.get("left_items", ["Easy to use", "Free", "Fast"])
        right_items = params.get("right_items", ["Complex", "Expensive", "Slow"])
        left_title = params.get("left_title", "Option A")
        right_title = params.get("right_title", "Option B")

        item_stagger = 0.25  # seconds between items

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames

        frame_clips = []
        for f in range(total_frames):
            t = f * frame_dur

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, (15, 15, 35), (5, 5, 15))

            # Title
            title_font = get_font(42)
            bbox = draw.textbbox((0, 0), title_text, font=title_font)
            tw = bbox[2] - bbox[0]
            draw.text(((self.width - tw) // 2, 200), title_text,
                      fill=(255, 255, 255), font=title_font)

            mid_x = self.width // 2

            # Divider line
            div_progress = ease_out_cubic(min(1.0, t / 0.5))
            div_height = int(1280 * div_progress)
            if div_height > 5:
                draw.line([(mid_x, 320), (mid_x, 320 + div_height)],
                          fill=(60, 60, 80), width=2)

            # VS badge — pops in with bounce
            vs_start = 0.5
            if t > vs_start:
                vs_progress = min(1.0, (t - vs_start) / 0.4)
                vs_scale = ease_out_bounce(vs_progress)
                vs_font_size = max(8, int(48 * vs_scale))
                vs_font = get_font(vs_font_size)
                vs_alpha = int(255 * min(1.0, vs_progress * 2))
                vs_color = (int(255 * vs_alpha / 255), int(215 * vs_alpha / 255), 0)
                draw.text((mid_x - int(15 * vs_scale), 920), "VS",
                          fill=vs_color, font=vs_font)

            header_font = get_font(36)
            item_font = get_font(28)

            # Left side — slides from left
            for i in range(len(left_items[:5]) + 1):  # +1 for header
                item_start = i * item_stagger
                item_progress = (t - item_start) / 0.5 if t > item_start else 0.0
                item_progress = max(0.0, min(1.0, item_progress))

                if i == 0:
                    # Header
                    bbox = draw.textbbox((0, 0), left_title, font=header_font)
                    tw = bbox[2] - bbox[0]
                    final_x = (mid_x - tw) // 2
                    start_x = -tw - 50
                    x = int(interpolate(start_x, final_x, item_progress, ease_out_cubic))
                    alpha = int(255 * ease_out_cubic(item_progress))
                    c = tuple(int(v * alpha / 255) for v in CHART_COLORS[0])
                    draw.text((x, 340), left_title, fill=c, font=header_font)
                else:
                    idx = i - 1
                    if idx < len(left_items):
                        item = left_items[idx]
                        y = 440 + idx * 80
                        final_x = 80
                        start_x = -self.width // 2
                        x = int(interpolate(start_x, final_x, item_progress, ease_out_cubic))
                        alpha = int(255 * ease_out_cubic(item_progress))

                        check_c = (int(120 * alpha / 255), int(255 * alpha / 255), int(120 * alpha / 255))
                        text_c = (int(200 * alpha / 255), int(200 * alpha / 255), int(220 * alpha / 255))
                        draw.text((x, y), "+", fill=check_c, font=item_font)
                        draw.text((x + 40, y), item, fill=text_c, font=item_font)

            # Right side — slides from right
            for i in range(len(right_items[:5]) + 1):
                item_start = i * item_stagger
                item_progress = (t - item_start) / 0.5 if t > item_start else 0.0
                item_progress = max(0.0, min(1.0, item_progress))

                if i == 0:
                    bbox = draw.textbbox((0, 0), right_title, font=header_font)
                    tw = bbox[2] - bbox[0]
                    final_x = mid_x + (mid_x - tw) // 2
                    start_x = self.width + 50
                    x = int(interpolate(start_x, final_x, item_progress, ease_out_cubic))
                    alpha = int(255 * ease_out_cubic(item_progress))
                    c = tuple(int(v * alpha / 255) for v in CHART_COLORS[1])
                    draw.text((x, 340), right_title, fill=c, font=header_font)
                else:
                    idx = i - 1
                    if idx < len(right_items):
                        item = right_items[idx]
                        y = 440 + idx * 80
                        final_x = mid_x + 60
                        start_x = self.width + 50
                        x = int(interpolate(start_x, final_x, item_progress, ease_out_cubic))
                        alpha = int(255 * ease_out_cubic(item_progress))

                        minus_c = (int(255 * alpha / 255), int(100 * alpha / 255), int(100 * alpha / 255))
                        text_c = (int(200 * alpha / 255), int(200 * alpha / 255), int(220 * alpha / 255))
                        draw.text((x, y), "-", fill=minus_c, font=item_font)
                        draw.text((x + 40, y), item, fill=text_c, font=item_font)

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── PROCESS ──────────────────────────────────────────────────

    def render_process_animated(self, title, data_label, duration, params=None):
        """Process — steps appear top to bottom with connecting lines."""
        params = params or {}
        title_text = title or "How It Works"

        steps = params.get("steps", [
            "Research & Learn",
            "Plan Your Approach",
            "Start Small",
            "Build Consistency",
            "See Results",
        ])

        step_stagger = 0.4  # seconds between step starts

        total_frames = max(2, int(duration * ANIM_FPS))
        frame_dur = duration / total_frames

        frame_clips = []
        for f in range(total_frames):
            t = f * frame_dur

            img = Image.new("RGB", (self.width, self.height))
            draw = ImageDraw.Draw(img)
            draw_gradient(draw, self.width, self.height, (15, 15, 35), (5, 5, 15))

            # Title
            title_font = get_font(42)
            bbox = draw.textbbox((0, 0), title_text, font=title_font)
            tw = bbox[2] - bbox[0]
            draw.text(((self.width - tw) // 2, 200), title_text,
                      fill=(255, 255, 255), font=title_font)

            step_font = get_font(32)
            num_font = get_font(40)
            step_gap = 220
            start_y = 380

            for i, step in enumerate(steps[:5]):
                step_start = i * step_stagger
                step_progress = (t - step_start) / 0.6 if t > step_start else 0.0
                step_progress = max(0.0, min(1.0, step_progress))

                y = start_y + i * step_gap
                cx = 150
                cy_circle = y + 30
                r = 35
                color = CHART_COLORS[i % len(CHART_COLORS)]

                # Circle pop-in (scale 0 -> 1)
                circle_scale = ease_out_bounce(min(1.0, step_progress / 0.5)) if step_progress > 0 else 0.0
                if circle_scale > 0.05:
                    cr = max(1, int(r * circle_scale))
                    draw.ellipse(
                        [cx - cr, cy_circle - cr, cx + cr, cy_circle + cr],
                        fill=color,
                    )

                    # Number inside circle
                    num_text = str(i + 1)
                    num_font_size = max(8, int(40 * circle_scale))
                    nf = get_font(num_font_size)
                    bbox = draw.textbbox((0, 0), num_text, font=nf)
                    ntw = bbox[2] - bbox[0]
                    draw.text((cx - ntw // 2, cy_circle - int(20 * circle_scale)),
                              num_text, fill=(0, 0, 0), font=nf)

                # Text fade-in
                if step_progress > 0.3:
                    text_progress = (step_progress - 0.3) / 0.7
                    text_alpha = int(240 * ease_in_out_cubic(min(1.0, text_progress)))
                    draw.text((220, y + 15), step,
                              fill=(text_alpha, text_alpha, text_alpha), font=step_font)

                # Connecting line to next step
                if i < len(steps) - 1 and step_progress > 0.8:
                    line_progress = (step_progress - 0.8) / 0.2
                    line_end = cy_circle + r + 5 + int((y + step_gap - 5 - cy_circle - r - 5) * min(1.0, line_progress))
                    draw.line(
                        [(cx, cy_circle + r + 5), (cx, line_end)],
                        fill=(60, 60, 80), width=2,
                    )

            clip = ImageClip(np.array(img)).with_duration(frame_dur).with_start(f * frame_dur)
            frame_clips.append(clip)

        return CompositeVideoClip(frame_clips, size=(self.width, self.height))

    # ─── HELPERS ──────────────────────────────────────────────────

    def _generate_chart_items(self, data_label):
        """Generate placeholder chart items from text."""
        words = data_label.split() if data_label else ["Category"]
        items = []
        for i, word in enumerate(words[:5]):
            items.append({
                "label": word.capitalize(),
                "value": random.randint(30, 95),
            })
        # Ensure at least 3 items
        while len(items) < 3:
            items.append({
                "label": f"Item {len(items) + 1}",
                "value": random.randint(30, 95),
            })
        return items
