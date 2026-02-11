"""
Video export — final render and file writing.
Wraps the MoviePy write_videofile call with standard settings.
"""

import os


def export_video(final_clip, output_path, config):
    """
    Export the final composed video to file.

    Args:
        final_clip: CompositeVideoClip ready to render
        output_path: Output MP4 path
        config: Config dict with video settings

    Returns:
        Path to output video
    """
    video_config = config.get("video", {})
    FPS = video_config.get("fps", 30)
    codec = video_config.get("codec", "libx264")
    audio_codec = video_config.get("audio_codec", "aac")
    bitrate = video_config.get("bitrate", "4M")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"   [Export] Rendering to {output_path}...")

    final_clip.write_videofile(
        output_path,
        fps=FPS,
        codec=codec,
        audio_codec=audio_codec,
        bitrate=bitrate,
        preset="medium",
        threads=4,
        logger="bar",
    )

    print(f"   [Export] Done! Output: {output_path}")
    return output_path
