"""
Script Generator — creates video scripts from templates.
NO AI API needed — uses template system + random variation.
"""

import json
import random
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


def load_json(filename):
    """Load a JSON file from templates directory."""
    path = os.path.join(TEMPLATES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_hooks():
    """Load all hook templates."""
    return load_json("hooks.json")["hooks"]


def load_script_templates():
    """Load script structure templates."""
    return load_json("scripts.json")["categories"]


def randomize_hook(topic, style=None):
    """
    Generate a random hook for a given topic.

    Args:
        topic: The video topic
        style: Hook style (curiosity, direct, pov, controversial, list, story, challenge)
               If None, picks randomly.

    Returns:
        Formatted hook string
    """
    hooks = load_hooks()

    if style and style in hooks:
        pool = hooks[style]
    else:
        pool = []
        for category_hooks in hooks.values():
            pool.extend(category_hooks)

    template = random.choice(pool)
    return template.replace("{topic}", topic).replace("{target_action}", f"learn about {topic}")


# Content databases for different topics
TOPIC_FACTS = {
    "default": [
        ("Research shows that {topic} can significantly impact your daily life",
         "Studies have found measurable improvements in people who practice this regularly.",
         "science research study"),
        ("Most people don't realize the connection between {topic} and overall well-being",
         "Understanding this link can help you make better decisions.",
         "wellness health connection"),
        ("Experts recommend starting with {topic} gradually",
         "Small consistent steps lead to the biggest long-term results.",
         "growth progress journey"),
        ("The history of {topic} goes back further than you think",
         "Ancient cultures already knew about these benefits centuries ago.",
         "history ancient wisdom"),
        ("One surprising benefit of {topic} is improved mental clarity",
         "Your brain functions better when you incorporate this into your routine.",
         "brain mind clarity"),
        ("The biggest mistake people make with {topic} is doing too much too fast",
         "Patience and consistency are the real keys to success here.",
         "patience consistency calm"),
        ("New studies in 2025 revealed even more about {topic}",
         "Science keeps uncovering new reasons why this matters.",
         "modern science discovery"),
        ("The number one myth about {topic} is that it's complicated",
         "In reality, anyone can start benefiting from this today.",
         "simple easy beginner"),
        ("{topic} doesn't just help you — it affects everyone around you",
         "When you improve yourself, your relationships improve too.",
         "relationships community people"),
        ("The best time to start with {topic} was yesterday — the second best is now",
         "Don't wait for the perfect moment. Just begin.",
         "motivation start action"),
    ],
    "sleep": [
        ("Quality sleep is more important than quantity",
         "7 hours of deep sleep beats 9 hours of restless tossing.",
         "peaceful sleep bedroom night"),
        ("Blue light from screens suppresses melatonin production",
         "Try putting your phone away 1 hour before bed.",
         "phone screen night dark"),
        ("Your bedroom temperature affects sleep quality dramatically",
         "The ideal sleeping temperature is between 60-67 degrees Fahrenheit.",
         "bedroom cozy temperature"),
    ],
    "wellness": [
        ("Morning sunlight exposure sets your circadian rhythm",
         "Just 10 minutes of morning sun can improve your entire day.",
         "sunrise morning light nature"),
        ("Hydration affects your energy more than caffeine",
         "Most fatigue is actually mild dehydration in disguise.",
         "water hydration health glass"),
        ("Deep breathing activates your parasympathetic nervous system",
         "Three deep breaths can reduce your stress in under 30 seconds.",
         "breathing meditation calm peace"),
    ],
    "cbd": [
        ("CBD interacts with your body's endocannabinoid system",
         "This system helps regulate sleep, mood, and pain responses.",
         "nature plant science wellness"),
        ("Studies show CBD may help reduce anxiety symptoms",
         "Research from major universities confirms its calming effects.",
         "calm relaxation peace nature"),
        ("CBD is non-psychoactive — it won't get you high",
         "It provides the wellness benefits without any mind-altering effects.",
         "natural wellness healthy plant"),
    ],
}


def get_facts_for_topic(topic, count=3):
    """Get relevant facts/content for a topic."""
    topic_lower = topic.lower()

    # Check if we have specific content for this topic
    matched_facts = None
    for key in TOPIC_FACTS:
        if key != "default" and key in topic_lower:
            matched_facts = TOPIC_FACTS[key]
            break

    if not matched_facts:
        matched_facts = TOPIC_FACTS["default"]

    # Pick random facts, fill with defaults if not enough
    selected = random.sample(matched_facts, min(count, len(matched_facts)))
    while len(selected) < count:
        extra = random.choice(TOPIC_FACTS["default"])
        if extra not in selected:
            selected.append(extra)

    return selected


def generate_script(topic, duration=30, language="en", style="education"):
    """
    Generate a complete video script.

    Args:
        topic: Video topic string
        duration: Target duration in seconds
        language: Language code (en, sk, cz)
        style: Style/category (education, lifestyle, product, humor, bait)

    Returns:
        dict with hook, segments, cta, total_duration, hashtags, music_mood
    """
    categories = load_script_templates()
    category = categories.get(style, categories.get("education"))
    structure = random.choice(category["structures"])

    # Determine number of segments based on duration
    if duration <= 20:
        num_segments = 2
    elif duration <= 40:
        num_segments = 3
    else:
        num_segments = 4

    # Generate hook
    hook_style = structure.get("hook_style", "curiosity")
    hook = randomize_hook(topic, hook_style)

    # Generate segments
    facts = get_facts_for_topic(topic, num_segments)
    segment_duration = max(5, (duration - 6) // num_segments)  # 3s hook + 3s CTA

    segments = []
    for i, (fact_text, explanation, visual_query) in enumerate(facts):
        text = fact_text.replace("{topic}", topic)
        detail = explanation

        segments.append({
            "text": f"{text}. {detail}",
            "duration": segment_duration,
            "visual_query": visual_query,
            "text_overlay": text[:50] + ("..." if len(text) > 50 else ""),
        })

    # CTA
    cta_text = structure.get("cta", "Follow for more!").replace("{topic}", topic)

    # Generate hashtags
    topic_words = topic.lower().replace(",", "").split()
    hashtags = [f"#{w}" for w in topic_words[:3]]
    hashtags.extend(["#shorts", "#viral", f"#{style}"])

    # Music mood mapping
    mood_map = {
        "education": "inspiring",
        "lifestyle": "chill",
        "product": "upbeat",
        "humor": "funny",
        "bait": "dramatic",
    }

    script = {
        "hook": hook,
        "segments": segments,
        "cta": cta_text,
        "total_duration": duration,
        "hashtags": hashtags,
        "music_mood": mood_map.get(style, "neutral"),
        "style": style,
        "language": language,
        "topic": topic,
    }

    return script


def generate_batch(topics, style="education", language="en", duration=30):
    """
    Generate scripts for multiple topics.

    Args:
        topics: List of topic strings
        style: Default style
        language: Language code
        duration: Default duration

    Returns:
        List of script dicts
    """
    scripts = []
    for topic in topics:
        script = generate_script(
            topic=topic.strip(),
            duration=duration,
            language=language,
            style=style,
        )
        scripts.append(script)
    return scripts


if __name__ == "__main__":
    # Quick test
    script = generate_script("Benefits of good sleep", duration=30, style="education")
    print(json.dumps(script, indent=2))
