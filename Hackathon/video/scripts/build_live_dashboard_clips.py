#!/usr/bin/env python3
"""Build privacy-safe video clips from browser-captured TideWatch frames.

The review frames contain only public signal history. Market-scan frames are
captured from the signed-in live Dashboard, so their sticky account summary is
covered with an opaque title card before any persistent artifact is written.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
CAPTURES = ROOT / "assets" / "screenshots" / "live"
OUT = ROOT / "assets" / "screen-recordings"
WIDTH, HEIGHT = 1920, 1080

FONT_REGULAR = Path("/System/Library/Fonts/Supplemental/Arial.ttf")
FONT_BOLD = Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def canvas_from_capture(path: Path) -> Image.Image:
    source = Image.open(path).convert("RGB")
    if source.width != WIDTH:
        source = source.resize((WIDTH, round(source.height * WIDTH / source.width)), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (WIDTH, HEIGHT), "white")
    canvas.paste(source.crop((0, 0, WIDTH, min(source.height, HEIGHT))), (0, 0))
    return canvas


def decorate_review(path: Path) -> Image.Image:
    image = canvas_from_capture(path)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 992, WIDTH, HEIGHT), fill="#f7f9fb")
    draw.line((0, 992, WIDTH, 992), fill="#e0e6eb", width=1)
    draw.text(
        (40, 1022),
        "LIVE TIDEWATCH DASHBOARD  ·  PUBLIC SIGNAL HISTORY  ·  NOT INVESTMENT ADVICE",
        font=font(FONT_REGULAR, 22),
        fill="#617181",
    )
    return image


def decorate_market(path: Path) -> Image.Image:
    image = canvas_from_capture(path)
    draw = ImageDraw.Draw(image)
    # Opaque by design: this masks the live account summary and any partial
    # holding card before the asset is persisted outside the temporary folder.
    draw.rectangle((0, 0, WIDTH, 430), fill="#06121d")
    draw.text((72, 92), "LIVE MARKET SCAN", font=font(FONT_BOLD, 56), fill="#42e8df")
    draw.text(
        (74, 178),
        "Real TideWatch Dashboard  ·  account data masked",
        font=font(FONT_REGULAR, 30),
        fill="white",
    )
    draw.text(
        (74, 236),
        "Public strongest / weakest watchlist  ·  Sep 3, 2026",
        font=font(FONT_REGULAR, 24),
        fill="#8aa8b8",
    )
    return image


def encode_sequence(pattern: Path, output: Path, framerate: int, start_pad: float, stop_pad: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-framerate", str(framerate), "-i", str(pattern),
            "-vf", (
                "fps=30,"
                f"tpad=start_mode=clone:start_duration={start_pad}:"
                f"stop_mode=clone:stop_duration={stop_pad}"
            ),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", "30", "-an", "-movflags", "+faststart",
            str(output),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--market-raw-dir",
        type=Path,
        default=Path("/tmp/tidewatch-live-raw-20260903"),
        help="Temporary folder containing frame-00.png, frame-01.png, ...",
    )
    args = parser.parse_args()

    review_frames = sorted(CAPTURES.glob("real-review-scroll-*.png"))
    market_frames = sorted(args.market_raw_dir.glob("frame-*.png"))
    if not review_frames:
        raise SystemExit("No live review frames found")
    if not market_frames:
        raise SystemExit(f"No live market frames found in {args.market_raw_dir}")

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tidewatch-safe-live-") as temporary:
        temp = Path(temporary)
        review_dir = temp / "review"
        market_dir = temp / "market"
        review_dir.mkdir()
        market_dir.mkdir()

        for index, path in enumerate(review_frames):
            decorate_review(path).save(review_dir / f"frame-{index:02}.png")
        for index, path in enumerate(market_frames):
            decorate_market(path).save(market_dir / f"frame-{index:02}.png")

        safe_review = CAPTURES / "real-review-safe.png"
        safe_market = CAPTURES / "real-market-scan-safe.png"
        decorate_review(review_frames[0]).save(safe_review)
        decorate_market(market_frames[0]).save(safe_market)

        encode_sequence(
            review_dir / "frame-%02d.png",
            OUT / "real-signal-review.mp4",
            framerate=4,
            start_pad=0.5,
            stop_pad=2.0,
        )
        encode_sequence(
            market_dir / "frame-%02d.png",
            OUT / "real-market-scan-safe.mp4",
            framerate=3,
            start_pad=0.5,
            stop_pad=1.2,
        )

    print((OUT / "real-signal-review.mp4").relative_to(ROOT))
    print((OUT / "real-market-scan-safe.mp4").relative_to(ROOT))


if __name__ == "__main__":
    main()
