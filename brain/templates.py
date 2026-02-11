"""
Template-based storyboard generator.
Wraps modules/script_generator.py — uses same TOPIC_FACTS, hooks, templates
but outputs Storyboard objects instead of raw dicts.

This is the "free" brain mode — no API calls needed.
"""

import json
import os
import random

from brain.storyboard import Scene, Storyboard, VisualType, TransitionType

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


def _load_json(filename):
    """Load a JSON file from templates directory."""
    path = os.path.join(TEMPLATES_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_storyboard_patterns():
    """Load storyboard scene composition patterns."""
    data = _load_json("storyboard_patterns.json")
    return data.get("patterns", {})


# Visual type mapping from pattern strings
VISUAL_TYPE_MAP = {
    "stock_footage": VisualType.STOCK_FOOTAGE,
    "ai_image": VisualType.AI_GENERATED_IMAGE,
    "ai_video": VisualType.AI_GENERATED_VIDEO,
    "infographic": VisualType.INFOGRAPHIC,
    "text_animation": VisualType.TEXT_ANIMATION,
    "motion_graphic": VisualType.MOTION_GRAPHIC,
    "color_background": VisualType.COLOR_BACKGROUND,
}

TRANSITION_MAP = {
    "cut": TransitionType.CUT,
    "crossfade": TransitionType.CROSSFADE,
    "fade_black": TransitionType.FADE_BLACK,
    "slide_left": TransitionType.SLIDE_LEFT,
    "zoom_in": TransitionType.ZOOM_IN,
}


def generate_storyboard(
    topic,
    duration=30,
    language="en",
    style="education",
    visual_mode="stock",
    max_scenes=6,
):
    """
    Generate a Storyboard from templates (no API calls).

    Args:
        topic: Video topic string
        duration: Target duration in seconds
        language: Language code
        style: Content style (education, lifestyle, product, humor, bait)
        visual_mode: What visuals to use:
            "stock" — all stock footage (default)
            "ai_image" — prefer AI images
            "ai_video" — prefer AI video
            "mixed" — mix of visual types from patterns
        max_scenes: Maximum number of scenes

    Returns:
        Storyboard object
    """
    # Import from existing script generator for backward compat
    from modules.script_generator import (
        randomize_hook, get_facts_for_topic, load_script_templates,
    )

    categories = load_script_templates()
    category = categories.get(style, categories.get("education"))
    structure = random.choice(category["structures"])

    # Determine number of segments
    if duration <= 20:
        num_segments = 2
    elif duration <= 40:
        num_segments = 3
    else:
        num_segments = min(4, max_scenes)

    # Generate hook
    hook_style = structure.get("hook_style", "curiosity")
    hook = randomize_hook(topic, hook_style)

    # Generate segments/facts
    facts = get_facts_for_topic(topic, num_segments)
    segment_duration = max(5, (duration - 6) // num_segments)

    # CTA
    cta_text = structure.get("cta", "Follow for more!").replace("{topic}", topic)

    # Hashtags
    topic_words = topic.lower().replace(",", "").split()
    hashtags = [f"#{w}" for w in topic_words[:3]]
    hashtags.extend(["#shorts", "#viral", f"#{style}"])

    # Music mood
    mood_map = {
        "education": "inspiring",
        "lifestyle": "chill",
        "product": "upbeat",
        "humor": "funny",
        "bait": "dramatic",
    }

    # Determine visual type per scene based on visual_mode
    visual_types = _get_visual_sequence(visual_mode, num_segments, style)

    # Transitions sequence
    transitions = [
        TransitionType.CROSSFADE,
        TransitionType.CUT,
        TransitionType.FADE_BLACK,
        TransitionType.CROSSFADE,
        TransitionType.ZOOM_IN,
        TransitionType.SLIDE_LEFT,
    ]

    # Build storyboard
    sb = Storyboard(
        topic=topic,
        language=language,
        style=style,
        target_duration=duration,
        hook=hook,
        cta=cta_text,
        hashtags=hashtags,
        music_mood=mood_map.get(style, "neutral"),
        title=topic,
    )

    for i, (fact_text, explanation, visual_query) in enumerate(facts):
        text = fact_text.replace("{topic}", topic)
        detail = explanation

        vtype = visual_types[i % len(visual_types)]
        transition = transitions[i % len(transitions)]

        # Build visual prompt based on type
        if vtype == VisualType.STOCK_FOOTAGE:
            visual_prompt = visual_query
        elif vtype in (VisualType.AI_GENERATED_IMAGE, VisualType.AI_GENERATED_VIDEO):
            visual_prompt = f"cinematic, {visual_query}, high quality, 4k"
        elif vtype == VisualType.INFOGRAPHIC:
            visual_prompt = visual_query
        elif vtype == VisualType.TEXT_ANIMATION:
            visual_prompt = text[:50]
        elif vtype == VisualType.MOTION_GRAPHIC:
            visual_prompt = visual_query
        else:
            visual_prompt = visual_query

        # Visual params
        visual_params = {}
        if vtype == VisualType.TEXT_ANIMATION:
            effects = ["typewriter", "fade_words", "slide_in", "kinetic_typography"]
            visual_params["effect"] = random.choice(effects)
            visual_params["text"] = text[:50] + ("..." if len(text) > 50 else "")
        elif vtype == VisualType.MOTION_GRAPHIC:
            visual_params["effect"] = random.choice(["lower_third", "title_card", "counter"])
            visual_params["text"] = text[:50] + ("..." if len(text) > 50 else "")
        elif vtype == VisualType.INFOGRAPHIC:
            visual_params["chart_type"] = random.choice(["bar_chart", "statistics", "comparison"])
            visual_params["title"] = topic
            visual_params["data_label"] = text[:40]

        scene = Scene(
            text=f"{text}. {detail}",
            duration=segment_duration,
            visual_type=vtype,
            visual_prompt=visual_prompt,
            visual_params=visual_params,
            transition_in=transition,
            text_overlay=text[:50] + ("..." if len(text) > 50 else ""),
        )
        sb.add_scene(scene)

    return sb


def _get_visual_sequence(visual_mode, count, style):
    """Get sequence of visual types based on mode."""
    if visual_mode == "stock":
        return [VisualType.STOCK_FOOTAGE] * count
    elif visual_mode == "ai_image":
        return [VisualType.AI_GENERATED_IMAGE] * count
    elif visual_mode == "ai_video":
        return [VisualType.AI_GENERATED_VIDEO] * count
    elif visual_mode == "mixed":
        # Load patterns if available, otherwise use defaults
        patterns = _load_storyboard_patterns()
        style_pattern = patterns.get(style, patterns.get("default", None))

        if style_pattern and "visual_sequence" in style_pattern:
            seq = style_pattern["visual_sequence"][:count]
            return [VISUAL_TYPE_MAP.get(v, VisualType.STOCK_FOOTAGE) for v in seq]

        # Default mixed pattern
        mixed = [
            VisualType.STOCK_FOOTAGE,
            VisualType.TEXT_ANIMATION,
            VisualType.STOCK_FOOTAGE,
            VisualType.MOTION_GRAPHIC,
            VisualType.INFOGRAPHIC,
            VisualType.STOCK_FOOTAGE,
        ]
        return mixed[:count]
    else:
        return [VisualType.STOCK_FOOTAGE] * count
