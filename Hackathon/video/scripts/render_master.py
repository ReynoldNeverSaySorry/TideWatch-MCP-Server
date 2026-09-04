#!/usr/bin/env python3
"""Burn the reviewed Chinese SRT into the privacy-safe picture master."""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "exports" / "TideWatch-Hackathon-previs-v2.mp4"
SRT = ROOT / "assets" / "audio" / "subtitles-zh.srt"
OUTPUT = ROOT / "exports" / "TideWatch-Hackathon-v1.mp4"
SRT_OUTPUT = ROOT / "exports" / "TideWatch-Hackathon-v1.srt"
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
WIDTH, HEIGHT = 1920, 1080


def seconds(stamp: str) -> float:
    hours, minutes, rest = stamp.split(":")
    whole, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(whole) + int(millis) / 1000


def parse_srt(path: Path) -> list[tuple[float, float, str]]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    cues = []
    for block in blocks:
        lines = block.splitlines()
        start, end = [part.strip() for part in lines[1].split("-->")]
        cues.append((seconds(start), seconds(end), "\n".join(lines[2:])))
    return cues


def render_cue(text: str, output: Path) -> None:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(FONT, 50)
    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=9, stroke_width=4)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = round((WIDTH - text_width) / 2)
    y = 980 - text_height
    draw.multiline_text(
        (x, y), text, font=font, fill="white", spacing=9, align="center",
        stroke_width=4, stroke_fill=(0, 0, 0, 230),
    )
    image.save(output)


def main() -> None:
    cues = parse_srt(SRT)
    with tempfile.TemporaryDirectory(prefix="tidewatch-subtitles-") as temporary:
        temp = Path(temporary)
        blank = temp / "blank.png"
        Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)).save(blank)
        cue_paths = []
        for index, (_, _, text) in enumerate(cues):
            path = temp / f"cue-{index:02}.png"
            render_cue(text, path)
            cue_paths.append(path)

        concat_lines = []
        cursor = 0.0
        last_path = blank
        for (start, end, _), cue_path in zip(cues, cue_paths, strict=True):
            if start > cursor:
                concat_lines += [f"file '{blank}'", f"duration {start - cursor:.3f}"]
            concat_lines += [f"file '{cue_path}'", f"duration {end - start:.3f}"]
            cursor = end
            last_path = cue_path
        if cursor < 145:
            concat_lines += [f"file '{blank}'", f"duration {145 - cursor:.3f}"]
            last_path = blank
        concat_lines.append(f"file '{last_path}'")
        concat_file = temp / "subtitles.concat"
        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")

        subtitle_track = temp / "subtitles.mov"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-vf", "fps=30,format=argb", "-c:v", "qtrle", "-t", "145",
            str(subtitle_track),
        ], check=True)

        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(SOURCE),
            "-i", str(subtitle_track), "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1[v]",
            "-map", "[v]", "-map", "0:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "copy", "-movflags", "+faststart", "-t", "145",
            str(OUTPUT),
        ], check=True)

    SRT_OUTPUT.write_text(SRT.read_text(encoding="utf-8"), encoding="utf-8")
    print(OUTPUT.relative_to(ROOT))
    print(SRT_OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
