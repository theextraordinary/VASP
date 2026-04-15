import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from vasp.pipeline.edit_pipeline import run_edit_pipeline

run_edit_pipeline(
    instruction=(
        "Create a 60-second creative vertical reel (9:16) using all provided media. "
        "Make it energetic and cinematic with cool animations: subtle zooms, pops, layered transitions, "
        "dynamic visual rhythm, and smooth timing changes. Use vibrant color styling, thoughtful composition, "
        "and strong object positioning. Add high-quality captions that are readable and stylish, aligned with "
        "beats and moments in the audio. Keep music in the background and synchronize visual/caption pacing to it. "
        "Mix video, image, gif, and sticker overlays creatively, with clear focal points and clean visual hierarchy. "
        "Ensure the final output feels polished, modern, and social-ready."
    ),
    media_paths=[
        "assets/inputs/video.mp4",
        "assets/inputs/image.jpg",
        "assets/inputs/gif.gif",
        "assets/inputs/sticker.png",
        "assets/inputs/music.mp3",
        "assets/inputs/sfx.wav",
    ],
    output_path="output/final_creative_reel.mp4",
    video_length_s=60,
    extra_options={"fps": 30},
)
