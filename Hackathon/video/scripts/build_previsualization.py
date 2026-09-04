#!/usr/bin/env python3
"""Build the 2:25 privacy-safe picture and audio master."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONCEPT = ROOT / "assets" / "generated" / "market-fusion" / "16x9"
CHARTS = ROOT / "assets" / "charts"
SCREEN_RECORDINGS = ROOT / "assets" / "screen-recordings"
AUDIO = ROOT / "assets" / "audio"
EXPORTS = ROOT / "exports"
FPS = 30

SEGMENTS = [
    ("black", None, 4),
    ("still", CONCEPT / "01-born-to-predict.png", 11),
    ("still", CONCEPT / "01-born-to-predict.png", 10),
    ("video", CHARTS / "learning-loop.mp4", 10),
    ("still", CONCEPT / "02-bull-bear-conflict.png", 7),
    ("video", CHARTS / "v1-conflict-guardrail.mp4", 6),
    ("still", CHARTS / "v1-conflict-guardrail.png", 10),
    ("still", CONCEPT / "02-bull-bear-conflict.png", 6),
    ("video", CHARTS / "v2-death-zone.mp4", 6),
    ("still", CHARTS / "v2-death-zone.png", 7),
    ("still", CONCEPT / "03-overconfidence-crash.png", 8),
    ("video", CHARTS / "v3-overconfidence.mp4", 6),
    ("video", CHARTS / "v3-reversal-penalty.mp4", 6),
    ("video", CHARTS / "v3-factor-weights.mp4", 7),
    ("still", CONCEPT / "04-choosing-wait.png", 6),
    ("video", CHARTS / "v4-confidence-gate.mp4", 6),
    ("video", CHARTS / "choosing-wait.mp4", 8),
    ("video", SCREEN_RECORDINGS / "real-signal-review.mp4", 6),
    ("video", SCREEN_RECORDINGS / "real-market-scan-safe.mp4", 5),
    ("still", CONCEPT / "05-taught-by-the-market.png", 10),
]


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def encode_segment(kind: str, source: Path | None, duration: int, output: Path, index: int) -> None:
    common = [
        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-g", str(FPS), "-video_track_timescale", "90000", str(output),
    ]
    if kind == "black":
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
            f"color=c=#06121d:s=1920x1080:r={FPS}:d={duration}", *common,
        ])
    elif kind == "still":
        assert source is not None
        direction = 1 if index % 2 == 0 else -1
        zoom = "min(zoom+0.00028,1.045)" if direction > 0 else "if(eq(on,1),1.045,max(1.0,zoom-0.00028))"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1", "-i", str(source),
            "-t", str(duration), "-vf", f"zoompan=z='{zoom}':d={duration * FPS}:s=1920x1080:fps={FPS}", *common,
        ])
    elif kind == "video":
        assert source is not None
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-stream_loop", "-1", "-i", str(source),
            "-t", str(duration), "-vf", "scale=1920:1080,fps=30", *common,
        ])
    else:
        raise ValueError(kind)


def main() -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    output = EXPORTS / "TideWatch-Hackathon-previs-v2.mp4"
    with tempfile.TemporaryDirectory(prefix="tidewatch-previs-") as temporary:
        temp = Path(temporary)
        files = []
        for index, (kind, source, duration) in enumerate(SEGMENTS):
            path = temp / f"segment-{index:02}.mp4"
            encode_segment(kind, source, duration, path, index)
            files.append(path)
        concat_file = temp / "concat.txt"
        concat_file.write_text("\n".join(f"file '{path}'" for path in files), encoding="utf-8")
        picture = temp / "picture.mp4"
        run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-c", "copy", str(picture),
        ])

        sfx = [
            (AUDIO / "sfx-signal-write.wav", 25_000),
            (AUDIO / "sfx-outcome-backfill.wav", 34_000),
            (AUDIO / "sfx-rule-write.wav", 48_000),
            (AUDIO / "sfx-outcome-backfill.wav", 58_000),
            (AUDIO / "sfx-rule-write.wav", 70_000),
            (AUDIO / "sfx-outcome-backfill.wav", 77_000),
            (AUDIO / "sfx-rule-write.wav", 91_000),
            (AUDIO / "sfx-outcome-backfill.wav", 104_000),
            (AUDIO / "sfx-rule-write.wav", 116_000),
        ]
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(picture),
            "-i", str(AUDIO / "narration-en.wav"),
            "-i", str(AUDIO / "music.wav"),
            "-i", str(AUDIO / "tide-ambience.wav"),
        ]
        for path, _ in sfx:
            command += ["-i", str(path)]
        filters = ["[1:a]aformat=sample_rates=48000:channel_layouts=stereo[n]", "[2:a]volume=1[m]", "[3:a]volume=1[t]"]
        mix_labels = ["[n]", "[m]", "[t]"]
        for index, (_, delay) in enumerate(sfx, start=4):
            label = f"s{index}"
            filters.append(f"[{index}:a]adelay={delay}:all=1[{label}]")
            mix_labels.append(f"[{label}]")
        filters.append(
            f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=longest:normalize=0,"
            "alimiter=limit=0.501:attack=5:release=50,volume=-4dB[aout]"
        )
        command += [
            "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-shortest", str(output),
        ]
        run(command)
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
