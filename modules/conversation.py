"""
Conversation Engine — generates multi-character dialogue videos.

Supports multiple render styles:
  - chat:    WhatsApp/iMessage animated chat bubbles
  - podcast: Two avatars side by side, speaker highlighting
  - story:   Animated scenes with speech bubbles and backgrounds

Pipeline:
  1. Parse conversation script (who says what)
  2. Generate TTS per character (different voices)
  3. Build word timestamps per line
  4. Route to appropriate renderer
  5. Compose final video with audio
"""

import hashlib
import json
import os
import random
import sys

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from modules.voiceover import generate_voiceover

# Default character voice presets
CHARACTER_VOICES = {
    "male_1": "en-US-GuyNeural",
    "male_2": "en-US-BrianNeural",
    "male_3": "en-US-ChristopherNeural",
    "female_1": "en-US-JennyNeural",
    "female_2": "en-US-AriaNeural",
    "female_3": "en-US-EmmaNeural",
    "male_sk": "sk-SK-LukasNeural",
    "female_sk": "sk-SK-ViktoriaNeural",
    "male_cz": "cs-CZ-AntoninNeural",
    "female_cz": "cs-CZ-VlastaNeural",
    "narrator": "en-US-EricNeural",
}

# Default character colors
CHARACTER_COLORS = [
    {"bubble": "#DCF8C6", "text": "#000000", "name": "#25D366"},  # WhatsApp green
    {"bubble": "#E3F2FD", "text": "#000000", "name": "#1976D2"},  # Blue
    {"bubble": "#FFF3E0", "text": "#000000", "name": "#FF9800"},  # Orange
    {"bubble": "#F3E5F5", "text": "#000000", "name": "#9C27B0"},  # Purple
]

# Default avatar colors (solid color circles with initial)
AVATAR_COLORS = [
    (37, 211, 102),   # Green
    (25, 118, 210),   # Blue
    (255, 152, 0),    # Orange
    (156, 39, 176),   # Purple
    (244, 67, 54),    # Red
    (0, 150, 136),    # Teal
]


def parse_conversation(script_text, language="en"):
    """
    Parse a conversation script into structured lines.

    Format:
        Character1: Hello, how are you?
        Character2: I'm great, thanks!
        [narrator]: And then something happened.
        Character1: Wow, really?

    Returns:
        {
            "characters": {"Character1": {...}, "Character2": {...}},
            "lines": [
                {"character": "Character1", "text": "Hello, how are you?", "index": 0},
                ...
            ]
        }
    """
    # Voice mapping per language
    LANG_VOICES = {
        "en": ["male_1", "female_1", "male_2", "female_2", "male_3", "female_3"],
        "sk": ["male_sk", "female_sk", "male_sk", "female_sk"],
        "cz": ["male_cz", "female_cz", "male_cz", "female_cz"],
    }
    LANG_NARRATOR = {
        "en": "narrator",
        "sk": "male_sk",
        "cz": "male_cz",
    }

    voice_list = LANG_VOICES.get(language, LANG_VOICES["en"])
    narrator_voice = LANG_NARRATOR.get(language, "narrator")

    lines = []
    characters = {}
    char_index = 0

    for raw_line in script_text.strip().split("\n"):
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        # Parse "Character: text" format
        if ":" in raw_line:
            colon_pos = raw_line.index(":")
            char_name = raw_line[:colon_pos].strip().strip("[]")
            text = raw_line[colon_pos + 1:].strip()

            if not text:
                continue

            # Register character if new
            if char_name not in characters:
                color_set = CHARACTER_COLORS[char_index % len(CHARACTER_COLORS)]
                avatar_color = AVATAR_COLORS[char_index % len(AVATAR_COLORS)]

                # Assign voice based on language and index
                if char_name.lower() in ("narrator", "rozprávač"):
                    voice = narrator_voice
                else:
                    voice = voice_list[char_index % len(voice_list)]

                characters[char_name] = {
                    "name": char_name,
                    "voice": voice,
                    "colors": color_set,
                    "avatar_color": avatar_color,
                    "index": char_index,
                    "side": "left" if char_index % 2 == 0 else "right",
                }
                char_index += 1

            lines.append({
                "character": char_name,
                "text": text,
                "index": len(lines),
            })

    return {
        "characters": characters,
        "lines": lines,
    }


def generate_conversation_audio(parsed_conv, language="en", rate="+0%"):
    """
    Generate TTS audio for each line of conversation with different voices.

    Returns list of dicts:
        [
            {
                "character": "Alice",
                "text": "Hello!",
                "audio_path": "...",
                "duration": 1.5,
                "word_timestamps": [...],
            },
            ...
        ]
    """
    results = []

    for line in parsed_conv["lines"]:
        char_info = parsed_conv["characters"][line["character"]]
        voice_key = char_info["voice"]

        # Resolve voice name
        voice_name = CHARACTER_VOICES.get(voice_key, voice_key)

        # Generate unique cache path
        text_hash = hashlib.md5(
            f"{line['text']}|{voice_name}|{line['index']}".encode()
        ).hexdigest()[:12]
        audio_path = os.path.join(BASE_DIR, "cache", "tts", f"conv_{text_hash}.mp3")

        # Try primary voice, fallback to GuyNeural if it fails
        try:
            result = generate_voiceover(
                text=line["text"],
                output_path=audio_path,
                voice=voice_name,
                rate=rate,
            )
        except Exception as e:
            print(f"   [Conversation] Voice {voice_name} failed, using fallback: {e}")
            fallback_voice = "en-US-GuyNeural"
            audio_path_fb = audio_path.replace(".mp3", "_fb.mp3")
            result = generate_voiceover(
                text=line["text"],
                output_path=audio_path_fb,
                voice=fallback_voice,
                rate=rate,
            )

        results.append({
            "character": line["character"],
            "text": line["text"],
            "audio_path": result["audio_path"],
            "duration": result["duration"],
            "word_timestamps": result["word_timestamps"],
            "index": line["index"],
        })

    return results


def generate_conversation_script(topic, style="chat", num_lines=8, language="en"):
    """
    Auto-generate a conversation script from a topic.

    Args:
        topic: What the conversation is about
        style: chat, podcast, or story
        num_lines: Number of dialogue lines
        language: Language code

    Returns:
        Conversation script string
    """
    # Load JSON templates (English only) — skip for other languages
    if language == "en":
        templates_path = os.path.join(BASE_DIR, "templates", "conversations.json")
        if os.path.exists(templates_path):
            with open(templates_path, "r", encoding="utf-8") as f:
                templates = json.load(f)

            style_templates = templates.get("styles", {}).get(style, {})
            conversations = style_templates.get("conversations", [])
            if conversations:
                for conv in conversations:
                    if topic.lower() in conv.get("topic", "").lower():
                        return conv["script"]
                conv = random.choice(conversations)
                return conv["script"]

    # Generate from code templates — route by language
    if language == "sk":
        if style == "chat":
            return _generate_chat_script_sk(topic, num_lines)
        elif style == "podcast":
            return _generate_podcast_script_sk(topic, num_lines)
        elif style == "story":
            return _generate_story_script_sk(topic, num_lines)
        else:
            return _generate_chat_script_sk(topic, num_lines)
    else:
        if style == "chat":
            return _generate_chat_script(topic, num_lines)
        elif style == "podcast":
            return _generate_podcast_script(topic, num_lines)
        elif style == "story":
            return _generate_story_script(topic, num_lines)
        else:
            return _generate_chat_script(topic, num_lines)


def _generate_chat_script(topic, num_lines=8):
    """Generate a chat-style conversation script."""
    # Templates for back-and-forth chat
    openers = [
        ("Alex", f"Hey, have you heard about {topic}?"),
        ("Alex", f"Dude, I just learned something crazy about {topic}"),
        ("Alex", f"You need to hear this about {topic}"),
        ("Alex", f"Can we talk about {topic} for a second?"),
    ]

    responses = [
        ("Sam", "No, tell me more!"),
        ("Sam", "Wait what? Spill the tea"),
        ("Sam", "Go on, I'm listening"),
        ("Sam", "I've been curious about that actually"),
    ]

    facts = [
        f"So apparently {topic} is way more important than people think",
        f"Research shows that {topic} can change your whole routine",
        f"The thing about {topic} is that most people get it completely wrong",
        f"I read that {topic} affects way more than just the obvious stuff",
        f"The best part about {topic} is how simple it actually is",
        f"What blew my mind is that {topic} has been proven scientifically",
    ]

    reactions = [
        "No way, seriously?",
        "That's actually insane",
        "Wait, I didn't know that",
        "Why doesn't anyone talk about this?",
        "Okay I need to try this",
        "You're telling me this is real?",
        "Mind blown honestly",
    ]

    follow_ups = [
        f"Yeah, and the crazy thing is it only takes like 5 minutes a day",
        f"Right? And it's completely free to start",
        f"Exactly. I wish I knew about {topic} sooner",
        f"For real. Everyone should know about this",
    ]

    closers = [
        ("Sam", "Okay I'm definitely looking into this. Thanks!"),
        ("Sam", "I'm starting tomorrow. No excuses."),
        ("Alex", f"Trust me, once you try {topic}, you won't go back."),
        ("Sam", "Send me more info about this later!"),
    ]

    # Build script
    lines = []
    opener = random.choice(openers)
    lines.append(f"{opener[0]}: {opener[1]}")

    response = random.choice(responses)
    lines.append(f"{response[0]}: {response[1]}")

    # Add facts and reactions alternating
    used_facts = random.sample(facts, min(3, len(facts)))
    used_reactions = random.sample(reactions, min(3, len(reactions)))

    for i in range(min(len(used_facts), num_lines // 2 - 1)):
        lines.append(f"Alex: {used_facts[i]}")
        if i < len(used_reactions):
            lines.append(f"Sam: {used_reactions[i]}")

    follow = random.choice(follow_ups)
    lines.append(f"Alex: {follow}")

    closer = random.choice(closers)
    lines.append(f"{closer[0]}: {closer[1]}")

    return "\n".join(lines[:num_lines])


def _generate_podcast_script(topic, num_lines=10):
    """Generate a podcast/debate style conversation."""
    intros = [
        f"Welcome back everyone. Today we're diving into {topic}.",
        f"Alright, let's talk about something important today. {topic}.",
        f"So today's topic is one I've been wanting to cover for a while. {topic}.",
    ]

    host_questions = [
        f"So what's the deal with {topic}? Why is everyone talking about it?",
        f"Let's start with the basics. What should people know about {topic}?",
        f"Now a lot of people have misconceptions about {topic}. What's the truth?",
        f"What's your personal experience with {topic}?",
        f"If someone wanted to start with {topic} today, what would you tell them?",
    ]

    expert_answers = [
        f"Great question. The thing about {topic} is that it's actually backed by solid research.",
        f"So there's a lot of misinformation out there. The real science says {topic} works by affecting multiple systems in your body.",
        f"From my experience, {topic} is one of the most underrated things people can do for themselves.",
        f"I'd say start small. You don't need to go all in on {topic} right away. Just start with the basics.",
        f"The evidence is clear. People who incorporate {topic} into their routine see measurable improvements.",
    ]

    closers_podcast = [
        f"That's incredibly valuable insight. Thank you for sharing.",
        f"Amazing. I think our listeners got a lot of value from this.",
        f"Well there you have it folks. {topic} is the real deal.",
    ]

    lines = []
    lines.append(f"Host: {random.choice(intros)}")

    questions = random.sample(host_questions, min(3, len(host_questions)))
    answers = random.sample(expert_answers, min(3, len(expert_answers)))

    for i in range(min(len(questions), num_lines // 2 - 1)):
        lines.append(f"Host: {questions[i]}")
        if i < len(answers):
            lines.append(f"Expert: {answers[i]}")

    lines.append(f"Host: {random.choice(closers_podcast)}")

    return "\n".join(lines[:num_lines])


def _generate_story_script(topic, num_lines=8):
    """Generate a story/drama style conversation."""
    stories = [
        [
            f"[Narrator]: This is the story of how {topic} changed everything.",
            f"[Narrator]: It all started on a random Tuesday morning.",
            f"Main: I never thought {topic} would matter to me.",
            f"Main: But then I saw the research. And it changed my perspective.",
            f"Friend: Are you seriously into {topic} now?",
            f"Main: Just listen. This is what I found out.",
            f"Main: {topic} isn't just a trend. It's backed by real science.",
            f"Friend: Okay, I'm convinced. Tell me more.",
            f"[Narrator]: And from that day forward, nothing was the same.",
        ],
        [
            f"[Narrator]: Everyone ignored {topic}. Until now.",
            f"Doctor: Your results would improve significantly with {topic}.",
            f"Patient: Really? I always thought that was just a myth.",
            f"Doctor: Not at all. The research is very clear on this.",
            f"Patient: So what exactly should I do?",
            f"Doctor: Start simple. Incorporate {topic} into your daily routine.",
            f"Doctor: Within weeks, you'll notice the difference.",
            f"Patient: I wish someone told me this years ago.",
            f"[Narrator]: Sometimes the best solutions are the simplest ones.",
        ],
    ]

    story = random.choice(stories)
    return "\n".join(story[:num_lines])


def _generate_chat_script_sk(topic, num_lines=8):
    """Generate a Slovak chat-style conversation script."""
    openers = [
        ("Marek", f"Hej, pocul si uz o {topic}?"),
        ("Marek", f"Musim ti nieco povedat o {topic}"),
        ("Marek", f"Ty, mam nieco zaujimave o {topic}"),
        ("Marek", f"Vies co som zistil o {topic}?"),
    ]

    responses = [
        ("Jana", "Nie, povedz viac!"),
        ("Jana", "Co to je? Povedz"),
        ("Jana", "Zaujimave, hovor dalej"),
        ("Jana", "Naozaj? Tak povedz"),
    ]

    facts = [
        f"Tak predstav si ze {topic} je ovela dolezitejsie nez si ludia myslia",
        f"Vyskumy ukazuju ze {topic} moze zmenit tvoj cely den",
        f"Vacsina ludi robi {topic} uplne zle a ani o tom nevedia",
        f"Najlepsie na {topic} je ze je to uplne jednoduche",
        f"Vedci potvrdili ze {topic} ma realne vysledky",
    ]

    reactions = [
        "To si robis srandu?",
        "Vazne? To som nevedela",
        "Preco o tom nikto nehovori?",
        "Dobre, to musim vyskusat",
        "To je neuveritelne",
    ]

    follow_ups = [
        f"A najlepsie je ze to zabere len par minut denne",
        f"Presne tak. A je to uplne zadarmo",
        f"Skoda ze som o {topic} nevedel skor",
    ]

    closers = [
        ("Jana", "Dobre, zacinam s tym zajtra. Diky!"),
        ("Jana", "Posli mi o tom viac info"),
        ("Marek", f"Ver mi, ked vyskusas {topic}, uz sa nevratís spat"),
    ]

    lines = []
    opener = random.choice(openers)
    lines.append(f"{opener[0]}: {opener[1]}")
    response = random.choice(responses)
    lines.append(f"{response[0]}: {response[1]}")

    used_facts = random.sample(facts, min(3, len(facts)))
    used_reactions = random.sample(reactions, min(3, len(reactions)))

    for i in range(min(len(used_facts), num_lines // 2 - 1)):
        lines.append(f"Marek: {used_facts[i]}")
        if i < len(used_reactions):
            lines.append(f"Jana: {used_reactions[i]}")

    follow = random.choice(follow_ups)
    lines.append(f"Marek: {follow}")
    closer = random.choice(closers)
    lines.append(f"{closer[0]}: {closer[1]}")

    return "\n".join(lines[:num_lines])


def _generate_podcast_script_sk(topic, num_lines=10):
    """Generate a Slovak podcast script."""
    lines = [
        f"Moderator: Vitajte pri dalsom dieli. Dnes sa bavime o {topic}",
        f"Expert: Dakujem za pozvanie. {topic} je podla mna jedna z najdolezitejsich tem dnesnej doby",
        f"Moderator: Tak povedzte nam, co by mali ludia vediet o {topic}?",
        f"Expert: Zakladna vec je ze vacsina ludi {topic} podcenuje. Pritom vyskumy jasne ukazuju vysledky",
        f"Moderator: A co by ste poradili niekomu kto s tym chce zacat?",
        f"Expert: Zacat pomaly. Netreba sa hnat. Male kroky kazdy den su kluc k uspechu",
        f"Moderator: Existuju nejake myty o {topic} ktore by ste chceli vyvratit?",
        f"Expert: Najvacsi mytus je ze {topic} je zlozite. V skutocnosti je to jednoduche ked viete ako",
        f"Moderator: Dakujeme za uzasne rady. To bolo velmi poucne",
    ]
    return "\n".join(lines[:num_lines])


def _generate_story_script_sk(topic, num_lines=8):
    """Generate a Slovak story script."""
    stories = [
        [
            f"[Narrator]: Toto je pribeh o tom ako {topic} zmenilo vsetko",
            f"Peter: Nikdy som si nemyslel ze {topic} bude pre mna dolezite",
            f"Peter: Ale potom som si precital vyskumy. A zmenil som nazor",
            f"Kamoska: Ty sa teraz zaujimas o {topic}?",
            f"Peter: Len pocuvaj. Toto som zistil",
            f"Peter: {topic} nie je len trend. Je za tym realna veda",
            f"Kamoska: Dobre, presvedcil si ma. Povedz viac",
            f"[Narrator]: A od toho dna uz nic nebolo ako predtym",
        ],
        [
            f"[Narrator]: Vsetci mu hovorili ze to nema zmysel. On sa rozhodol dokazat opak",
            f"Tomas: Idem zacat s {topic} naplno",
            f"Priatel: V dnesnej dobe? To je riskanntne",
            f"Tomas: Riskantnejsie je nerobit nic a cakat",
            f"[Narrator]: Tomas zacal od nuly. Len s napadom a odhodlanim",
            f"Tomas: Prvy mesiac bol brutalny. Ziadne vysledky",
            f"Priatel: Mozno je cas to vzdať?",
            f"Tomas: Neprisiel som tak daleko aby som to teraz vzdal",
            f"[Narrator]: O pol roka neskor sa vsetko zmenilo. Poucenie? Vsad na seba",
        ],
    ]
    story = random.choice(stories)
    return "\n".join(story[:num_lines])


def build_conversation_video(
    script_text,
    render_style="chat",
    output_path=None,
    language="en",
    config=None,
):
    """
    Main entry point — build a conversation video from script text.

    Args:
        script_text: Multi-line conversation script
        render_style: "chat", "podcast", or "story"
        output_path: Output MP4 path
        language: Language code
        config: Config dict from config.yaml

    Returns:
        Path to output video file
    """
    if config is None:
        config_path = os.path.join(BASE_DIR, "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

    if output_path is None:
        h = hashlib.md5(script_text.encode()).hexdigest()[:8]
        output_path = os.path.join(
            BASE_DIR, "output", "drafts", f"conv_{render_style}_{h}.mp4"
        )

    print(f"\n   [Conversation] Parsing script...")
    parsed = parse_conversation(script_text, language=language)
    print(f"   [Conversation] Characters: {list(parsed['characters'].keys())}")
    print(f"   [Conversation] Lines: {len(parsed['lines'])}")

    print(f"\n   [Conversation] Generating audio per character...")
    audio_lines = generate_conversation_audio(parsed, language=language)
    total_duration = sum(a["duration"] for a in audio_lines)
    # Add pauses between lines
    pause_duration = 0.4
    total_duration += pause_duration * (len(audio_lines) - 1)
    print(f"   [Conversation] Total audio duration: {total_duration:.1f}s")

    print(f"\n   [Conversation] Rendering {render_style} style...")

    if render_style == "chat":
        from modules.renderers.chat_renderer import render_chat_video
        return render_chat_video(parsed, audio_lines, output_path, config)
    elif render_style == "podcast":
        from modules.renderers.podcast_renderer import render_podcast_video
        return render_podcast_video(parsed, audio_lines, output_path, config)
    elif render_style == "story":
        from modules.renderers.story_renderer import render_story_video
        return render_story_video(parsed, audio_lines, output_path, config)
    else:
        from modules.renderers.chat_renderer import render_chat_video
        return render_chat_video(parsed, audio_lines, output_path, config)
