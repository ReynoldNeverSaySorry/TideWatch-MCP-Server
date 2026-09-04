#!/usr/bin/env python3
"""Generate factual Full-HD TideWatch data-card motion assets.

The numbers here mirror FACT-CHECK.md. Run this script again after any factual
change so the PNG review frames and MP4 assets stay in sync.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH, HEIGHT = 1920, 1080
FPS, DURATION = 30, 6
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "charts"

BG = "#06121d"
PANEL = "#0d2232"
PANEL_2 = "#102b3d"
WHITE = "#edf7fb"
MUTED = "#8aa8b8"
CYAN = "#42e8df"
BLUE = "#3c89ff"
AMBER = "#ffb84a"
RED = "#ff5d66"
GREEN = "#48d597"

FONT_REG = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_MONO = "/System/Library/Fonts/SFNSMono.ttf"


def font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_MONO if mono else FONT_BOLD if bold else FONT_REG
    return ImageFont.truetype(path, size)


def ease(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return 1 - (1 - value) ** 3


def phase(t: float, start: float, end: float) -> float:
    return ease((t - start) / (end - start))


def mix_color(first: str, second: str, amount: float) -> tuple[int, int, int]:
    """Interpolate two #RRGGBB colors for restrained fade animations."""
    amount = max(0.0, min(1.0, amount))
    a = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
    b = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int = 28,
            fill: str = PANEL, outline: str | None = None, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def base_frame(lesson: str, title: str, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    for x in range(0, WIDTH, 80):
        draw.line((x, 0, x, HEIGHT), fill="#092033", width=1)
    for y in range(0, HEIGHT, 80):
        draw.line((0, y, WIDTH, y), fill="#092033", width=1)
    draw.text((110, 72), f"TIDEWATCH  //  {lesson}", font=font(28, mono=True), fill=CYAN)
    draw.text((110, 130), title, font=font(74, bold=True), fill=WHITE)
    draw.text((112, 222), subtitle, font=font(31), fill=MUTED)
    draw.line((110, 290, 1810, 290), fill="#17405a", width=2)
    return image, draw


def disclaimer(draw: ImageDraw.ImageDraw) -> None:
    text = "Historical 5-day outcomes · Specific historical samples · Not investment advice"
    draw.text((110, 1018), text, font=font(22), fill="#6f8e9e")
    draw.text((1750, 1018), "tidewatch", font=font(22, mono=True), fill=CYAN)


def draw_case(draw: ImageDraw.ImageDraw, x: int, score: str, result: str, label: str,
              accent: str, alpha: float) -> None:
    y = int(355 + 28 * (1 - alpha))
    rounded(draw, (x, y, x + 750, y + 360), fill=PANEL, outline=accent, width=3)
    draw.text((x + 42, y + 34), label, font=font(25, mono=True), fill=MUTED)
    draw.text((x + 42, y + 94), score, font=font(86, bold=True), fill=WHITE)
    draw.text((x + 42, y + 208), "CONFLICT DETECTED", font=font(25, mono=True), fill=AMBER)
    draw.text((x + 42, y + 265), result, font=font(48, bold=True), fill=accent)


def card_v1(t: float) -> Image.Image:
    image, draw = base_frame("LESSON 01", "Conflict needs conviction", "A weak signal became a behavioral guardrail")
    p1, p2, p3 = phase(t, .45, 1.25), phase(t, 1.35, 2.15), phase(t, 3.0, 4.2)
    if p1:
        draw_case(draw, 110, "+40  /  +45", "5D  -9.3%", "SAME STOCK · TWO CALLS", RED, p1)
    if p2:
        draw_case(draw, 1060, "SCORE  +92", "5D  +15.8%", "ONE STRONG CALL", GREEN, p2)
    if p3:
        y = int(825 + 20 * (1 - p3))
        rounded(draw, (310, y, 1610, y + 125), fill="#152d37", outline=AMBER, width=3)
        draw.text((390, y + 34), "CONFLICT + |SCORE| < 50", font=font(38, bold=True, mono=True), fill=WHITE)
        draw.text((1250, y + 34), "→  WAIT ADVISED", font=font(38, bold=True, mono=True), fill=AMBER)
    disclaimer(draw)
    return image


def card_v2(t: float) -> Image.Image:
    image, draw = base_frame("LESSON 02", "Remove the unreliable answer", "The slightly bullish band failed four times out of four")
    p1, p2, p3 = phase(t, .35, 1.1), phase(t, 1.1, 2.9), phase(t, 3.2, 4.5)
    rounded(draw, (110, 350, 600, 760), fill=PANEL)
    draw.text((155, 400), "OBSERVATIONS", font=font(25, mono=True), fill=MUTED)
    draw.text((155, 485), str(round(82 * p1)), font=font(112, bold=True), fill=WHITE)
    draw.text((155, 620), f"{round(52 * p1)} BACKFILLED", font=font(31, mono=True), fill=CYAN)
    rounded(draw, (655, 350, 1810, 760), fill=PANEL)
    draw.text((710, 402), "SCORE BAND  [+25, +50)", font=font(32, mono=True), fill=MUTED)
    draw.text((710, 492), f"{round(4 * p2)}/4 FAILED", font=font(86, bold=True), fill=RED)
    draw.text((710, 620), f"AVG  {-6.58 * p2:.2f}%", font=font(48, bold=True, mono=True), fill=AMBER)
    if p3:
        rounded(draw, (330, 820, 1590, 945), fill=PANEL_2, outline=CYAN, width=3)
        old_color = "#506878"
        draw.text((400, 852), "BULLISH ≥ +25", font=font(42, bold=True, mono=True), fill=old_color)
        draw.line((395, 882, 815, 882), fill=RED, width=5)
        draw.text((920, 852), "BULLISH ≥ +50", font=font(42, bold=True, mono=True), fill=CYAN)
    disclaimer(draw)
    return image


def bar(draw: ImageDraw.ImageDraw, x: int, value: float, label: str, count: str,
        accent: str, progress: float) -> None:
    y_bottom, max_height, width = 815, 390, 330
    height = int(max_height * value / 100 * progress)
    rounded(draw, (x, y_bottom - height, x + width, y_bottom), radius=24, fill=accent)
    shown = value * progress
    draw.text((x + width / 2, y_bottom - height - 90), f"{shown:.1f}%", anchor="mm",
              font=font(58, bold=True), fill=WHITE)
    draw.text((x + width / 2, 865), label, anchor="mm", font=font(30, bold=True), fill=WHITE)
    draw.text((x + width / 2, 915), count, anchor="mm", font=font(24, mono=True), fill=MUTED)


def card_v3(t: float) -> Image.Image:
    image, draw = base_frame("LESSON 03", "Confidence can lie", "Near-perfect scores underperformed the lower band")
    p1, p2, p3 = phase(t, .5, 2.3), phase(t, 1.25, 3.05), phase(t, 3.4, 4.7)
    draw.line((380, 815, 1540, 815), fill="#31566a", width=3)
    bar(draw, 510, 89.5, "SCORE [70,85)", "17 / 19", CYAN, p1)
    bar(draw, 1080, 56.3, "SCORE [85,95)", "9 / 16", RED, p2)
    if p3:
        rounded(draw, (1220, 335, 1810, 420), fill="#291c22", outline=RED, width=3)
        draw.text((1515, 377), "OVERCONFIDENCE  ×0.7", anchor="mm", font=font(34, bold=True, mono=True), fill=AMBER)
    disclaimer(draw)
    return image


def card_v3_reversal(t: float) -> Image.Image:
    image, draw = base_frame(
        "LESSON 03A", "A changed answer deserves less trust",
        "Direction reversals underperformed stable calls in the historical sample",
    )
    p1, p2, p3 = phase(t, .45, 2.0), phase(t, 1.2, 2.9), phase(t, 3.2, 4.6)
    draw.line((380, 815, 1540, 815), fill="#31566a", width=3)
    bar(draw, 510, 30.0, "REVERSAL", "3 / 10", RED, p1)
    bar(draw, 1080, 71.6, "NON-REVERSAL", "48 / 67", GREEN, p2)
    if p3:
        rounded(draw, (1180, 315, 1810, 395), fill="#291c22", outline=RED, width=3)
        draw.text((1495, 355), "REVERSAL CONFIDENCE  ×0.6", anchor="mm",
                  font=font(31, bold=True, mono=True), fill=AMBER)
    disclaimer(draw)
    return image


def weight_row(draw: ImageDraw.ImageDraw, y: int, label: str, before: str, after: str,
               accent: str, progress: float) -> None:
    rounded(draw, (180, y, 1740, y + 205), fill=PANEL)
    draw.text((240, y + 34), label, font=font(29, mono=True), fill=MUTED)
    draw.text((680, y + 118), before, anchor="mm", font=font(64, bold=True), fill="#66808e")
    draw.line((810, y + 118, 1080, y + 118), fill=mix_color("#31566a", accent, progress), width=7)
    arrow_x = int(810 + 270 * progress)
    draw.polygon(((arrow_x, y + 102), (arrow_x + 30, y + 118), (arrow_x, y + 134)), fill=accent)
    draw.text((1270, y + 118), after, anchor="mm", font=font(64, bold=True), fill=accent)


def card_v3_weights(t: float) -> Image.Image:
    image, draw = base_frame(
        "LESSON 03B", "Evidence earns its weight",
        "Noisy factors weakened. Stronger downside evidence gained influence.",
    )
    p1, p2, p3 = phase(t, .45, 1.8), phase(t, 1.5, 3.0), phase(t, 3.35, 4.7)
    weight_row(draw, 365, "MA5 RISING", "+8", "+4", CYAN, p1)
    weight_row(draw, 620, "THREE BEARISH CANDLES", "−8", "−12", RED, p2)
    if p3:
        rounded(draw, (520, 875, 1400, 960), fill=PANEL_2, outline=AMBER, width=3)
        draw.text((960, 918), "RULE CHANGE · REVIEWED BEFORE DEPLOYMENT", anchor="mm",
                  font=font(27, bold=True, mono=True), fill=AMBER)
    disclaimer(draw)
    return image


def card_wait(t: float) -> Image.Image:
    image, draw = base_frame(
        "THE DECISION", "The hardest answer is no answer",
        "When confidence is below 40, direction gives way to restraint",
    )
    withdraw = phase(t, .7, 3.2)
    reveal = phase(t, 2.5, 4.5)
    side_color = mix_color(RED, PANEL_2, withdraw)
    other_color = mix_color(GREEN, PANEL_2, withdraw)
    side_shift = int(120 * withdraw)
    rounded(draw, (180 - side_shift, 430, 700 - side_shift, 725), fill=PANEL, outline=side_color, width=4)
    rounded(draw, (1220 + side_shift, 430, 1740 + side_shift, 725), fill=PANEL, outline=other_color, width=4)
    draw.text((440 - side_shift, 555), "BUY", anchor="mm", font=font(78, bold=True), fill=side_color)
    draw.text((1480 + side_shift, 555), "SELL", anchor="mm", font=font(78, bold=True), fill=other_color)
    draw.text((440 - side_shift, 650), "LOW CONFIDENCE", anchor="mm", font=font(25, mono=True), fill=MUTED)
    draw.text((1480 + side_shift, 650), "LOW CONFIDENCE", anchor="mm", font=font(25, mono=True), fill=MUTED)
    if withdraw:
        draw.line((245 - side_shift, 575, 635 - side_shift, 505), fill=RED, width=10)
        draw.line((1285 + side_shift, 575, 1675 + side_shift, 505), fill=RED, width=10)
    if reveal:
        top = int(420 + 30 * (1 - reveal))
        rounded(draw, (620, top, 1300, top + 330), fill="#102f38", outline=CYAN, width=5)
        draw.text((960, top + 115), "WAIT", anchor="mm", font=font(96, bold=True), fill=CYAN)
        draw.text((960, top + 220), "CONFIDENCE < 40", anchor="mm",
                  font=font(32, bold=True, mono=True), fill=WHITE)
    disclaimer(draw)
    return image


def card_v4(t: float) -> Image.Image:
    image, draw = base_frame("LESSON 04", "Maturity means knowing when to wait", "Confidence revealed the hidden variable")
    p1, p2, p3 = phase(t, .35, 1.1), phase(t, .9, 2.8), phase(t, 3.25, 4.55)
    draw.text((110, 330), f"{round(135 * p1)} SIGNALS  /  {round(129 * p1)} WITH 5D OUTCOMES",
              font=font(29, mono=True), fill=MUTED)
    draw.line((380, 815, 1540, 815), fill="#31566a", width=3)
    bar(draw, 510, 72.1, "HIGH CONF 70+", "49 / 68", GREEN, p2)
    bar(draw, 1080, 47.8, "LOW CONF <40", "11 / 23", RED, p2)
    if p3:
        rounded(draw, (1160, 360, 1810, 455), fill="#112f38", outline=CYAN, width=3)
        draw.text((1485, 407), "CONFIDENCE < 40  →  WAIT", anchor="mm",
                  font=font(38, bold=True, mono=True), fill=CYAN)
    disclaimer(draw)
    return image


LOOP_NODES = ["PREDICT", "REMEMBER", "VERIFY", "REFLECT", "REFINE", "REPEAT"]


def card_loop(t: float) -> Image.Image:
    image, draw = base_frame("THE LOOP", "Every signal becomes a promise", "The story begins after the prediction")
    center = (960, 630)
    radius = 300
    active = min(len(LOOP_NODES) - 1, int(max(0, t - .5) / .72))
    points: list[tuple[int, int]] = []
    for index in range(len(LOOP_NODES)):
        angle = -math.pi / 2 + index * math.tau / len(LOOP_NODES)
        points.append((int(center[0] + radius * math.cos(angle)), int(center[1] + radius * math.sin(angle))))
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        draw.line((*point, *next_point), fill="#1a586c" if index >= active else CYAN, width=5)
    for index, (label, point) in enumerate(zip(LOOP_NODES, points)):
        is_active = index <= active
        fill = CYAN if is_active else PANEL_2
        outline = CYAN if is_active else "#2f6071"
        draw.ellipse((point[0] - 88, point[1] - 88, point[0] + 88, point[1] + 88), fill=fill, outline=outline, width=4)
        draw.text(point, label, anchor="mm", font=font(22, bold=True, mono=True), fill=BG if is_active else MUTED)
    draw.text(center, "LEARN", anchor="mm", font=font(58, bold=True), fill=WHITE)
    draw.text((960, 695), "FROM REAL OUTCOMES", anchor="mm", font=font(22, mono=True), fill=MUTED)
    disclaimer(draw)
    return image


ASSETS = {
    "v1-conflict-guardrail": card_v1,
    "v2-death-zone": card_v2,
    "v3-overconfidence": card_v3,
    "v3-reversal-penalty": card_v3_reversal,
    "v3-factor-weights": card_v3_weights,
    "v4-confidence-gate": card_v4,
    "choosing-wait": card_wait,
    "learning-loop": card_loop,
}


def encode(name: str, renderer) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    output = OUT / f"{name}.mp4"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", f"{WIDTH}x{HEIGHT}",
        "-framerate", str(FPS), "-i", "-", "-an", "-c:v", "libx264",
        "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    for frame_index in range(FPS * DURATION):
        timestamp = frame_index / FPS
        process.stdin.write(renderer(timestamp).tobytes())
    process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError(f"ffmpeg failed for {output}")
    renderer(DURATION).save(OUT / f"{name}.png")
    print(output.relative_to(ROOT))


def main() -> None:
    for name, renderer in ASSETS.items():
        encode(name, renderer)


if __name__ == "__main__":
    main()
