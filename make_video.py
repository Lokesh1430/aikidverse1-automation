
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

WIDTH, HEIGHT = 720, 1280
FPS = 24
SCENE_SECONDS = 4
OUT = Path("output")
SCENES = OUT / "scenes"
OUT.mkdir(exist_ok=True)
SCENES.mkdir(exist_ok=True)


def draw_scene(index, title):
    im = Image.new("RGB", (WIDTH, HEIGHT), (133, 206, 245))
    d = ImageDraw.Draw(im)

    # Sky, clouds, hills and grass
    d.ellipse((-100, 750, 380, 1170), fill=(91, 190, 113))
    d.ellipse((300, 730, 850, 1200), fill=(61, 165, 91))
    d.rectangle((0, 1000, WIDTH, HEIGHT), fill=(76, 177, 93))

    for x, y in [(100, 170), (460, 240), (320, 110)]:
        d.ellipse((x, y, x + 115, y + 50), fill="white")
        d.ellipse((x + 25, y - 25, x + 80, y + 40), fill="white")

    # Watermelon moves across the three scenes
    wx = [130, 330, 500][index]
    wy = [930, 900, 940][index]
    d.ellipse((wx - 85, wy - 55, wx + 85, wy + 55),
              fill=(28, 143, 67), outline=(16, 91, 43), width=6)
    d.arc((wx - 70, wy - 45, wx + 70, wy + 45),
          40, 320, fill=(245, 65, 74), width=9)

    # Cute original cartoon hippo
    hx = [220, 300, 405][index]
    hy = 850
    d.ellipse((hx - 125, hy - 150, hx + 125, hy + 130),
              fill=(164, 151, 205), outline=(87, 75, 129), width=7)
    d.ellipse((hx - 110, hy - 35, hx + 110, hy + 90),
              fill=(202, 184, 219), outline=(87, 75, 129), width=5)
    d.ellipse((hx - 78, hy - 112, hx - 20, hy - 48), fill="white")
    d.ellipse((hx + 20, hy - 112, hx + 78, hy - 48), fill="white")
    d.ellipse((hx - 57, hy - 90, hx - 32, hy - 60), fill=(30, 30, 50))
    d.ellipse((hx + 37, hy - 90, hx + 62, hy - 60), fill=(30, 30, 50))
    d.ellipse((hx - 48, hy + 4, hx + 48, hy + 55), fill=(135, 105, 157))
    d.ellipse((hx - 25, hy + 13, hx - 9, hy + 28), fill=(35, 35, 45))
    d.ellipse((hx + 9, hy + 13, hx + 25, hy + 28), fill=(35, 35, 45))

    if index == 0:
        caption = "OH! MY WATERMELON!"
    elif index == 1:
        caption = "COME BACK HERE!"
    else:
        caption = "WHAT A BOUNCE!"

    d.rounded_rectangle((35, 60, WIDTH - 35, 155), radius=28,
                        fill=(255, 247, 218), outline=(45, 66, 80), width=4)
    d.text((WIDTH // 2, 108), caption, fill=(40, 48, 65), anchor="mm")

    path = SCENES / f"scene{index + 1}.png"
    im.save(path)
    return path


def main():
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed.")

    scenes = [draw_scene(i, "") for i in range(3)]
    inputs = []
    for scene in scenes:
        inputs += ["-loop", "1", "-framerate", str(FPS),
                   "-t", str(SCENE_SECONDS), "-i", str(scene)]

    filters = []
    for i in range(3):
        filters.append(
            f"[{i}:v]scale=800:1422,"
            f"crop=720:1280,"
            f"zoompan=z='min(zoom+0.0008,1.04)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={SCENE_SECONDS * FPS}:s=720x1280:fps={FPS},"
            f"setsar=1,format=yuv420p[v{i}]"
        )

    filters.append("[v0][v1][v2]concat=n=3:v=1:a=0[outv]")
    output = OUT / "aikidverse1_test_short.mp4"

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[outv]",
        "-t", str(SCENE_SECONDS * 3),
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(output)
    ]
    subprocess.run(cmd, check=True)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration", "-of", "json", str(output)],
        check=True, capture_output=True, text=True
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    if not 10 <= duration <= 15:
        raise RuntimeError(f"Unexpected video duration: {duration}")

    print(f"VIDEO_OK: {output}, duration={duration:.2f}s")
    print("Note: this is an illustrated animation prototype, not AI-generated 3D footage.")


if __name__ == "__main__":
    main()
