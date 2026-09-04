#!/usr/bin/env python3
"""Generate timing-locked, locally synthesized delivery audio and subtitles."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "audio"
VOICE = "Samantha"
RATE = "155"
TOTAL_SECONDS = 145

SEGMENTS = [
    (4.0, 15.0, "Most AI systems make a prediction, then move on. The answer remains. The lesson disappears.",
     "大多数 AI 做出预测，然后继续向前。\n答案留下，教训却消失了。"),
    (15.0, 25.0, "TideWatch was born to read the market: price, momentum, money, news, and the market regime around them.",
     "TideWatch 生来用于理解市场：价格、动量、资金、消息，\n以及它们所处的市场体制。"),
    (25.0, 35.0, "But it did one thing differently. Every signal became a promise. Five, ten, and twenty trading days later, the market came back to grade it.",
     "但它多做了一件事：每个信号都是一次承诺。\n五、十、二十个交易日后，市场终会回来批改。"),
    (35.0, 48.0, "Its first lesson came from contradiction. Two conflicted calls on the same stock scored plus forty and plus forty-five. Both fell 9.3 percent. Another scored plus ninety-two and rose 15.8.",
     "第一课来自矛盾：同一只股票的两个冲突信号评分 +40 和 +45，\n五日均下跌 9.3%；另一个评分 +92，五日上涨 15.8%。"),
    (48.0, 58.0, "Lesson one: when evidence conflicts and conviction is weak, do nothing. A mistake became a guardrail.",
     "第一课：证据冲突、判断不强时，不交易。\n一次错误，变成一道护栏。"),
    (58.0, 70.0, "More signals returned. A so-called slightly bullish zone had failed four times out of four, losing 6.58 percent on average.",
     "更多信号完成回填。所谓“弱多”区间四次全错，\n平均下跌 6.58%。"),
    (70.0, 77.0, "TideWatch stopped softening bad answers. It removed the answer.",
     "TideWatch 不再美化不可靠的答案。\n它直接删除了这个答案。"),
    (77.0, 91.0, "Then came the most unsettling lesson. Near-perfect scores were right only 56.3 percent of the time, while the lower band reached 89.5 percent.",
     "接着是最反直觉的一课：接近满分的判断只有 56.3% 正确，\n较低区间却达到 89.5%。"),
    (91.0, 104.0, "Confidence was no longer taken at face value. Reversals were penalized. Noisy factors lost weight. Stronger evidence gained it.",
     "系统不再照单全收自己的自信。方向翻转被惩罚，\n噪声因子降权，更可靠的证据得到加强。"),
    (104.0, 116.0, "With 135 signals, the hidden variable finally surfaced. High-confidence calls reached 72.1 percent. Low-confidence calls fell to 47.8.",
     "当信号增长到 135 条，隐藏变量终于浮现：\n高置信度达到 72.1%，低置信度只有 47.8%。"),
    (116.0, 124.0, "So TideWatch learned its hardest lesson: when confidence is low, do not force a direction.",
     "TideWatch 学会了最难的一课：\n没有把握时，不要强行给出方向。"),
    (124.0, 135.0, "Today, every analysis enters the same loop: predict, remember, verify, reflect, and return stronger.",
     "今天，每次分析都进入同一个循环：\n预测、记忆、验证、自省，然后再次出发。"),
    (135.0, 145.0, "It was built to read the market. But only the market could teach it how. TideWatch. Born to predict. Taught by the tide.",
     "它被创造来理解市场，但只有市场能教会它如何成长。\nTideWatch，生于预测，师从市场。"),
]

SUBTITLES = [
    (4.0, 8.5, "大多数 AI 做出预测，\n然后继续向前。"),
    (8.5, 14.75, "答案留下，\n教训却消失了。"),
    (15.0, 19.8, "TideWatch 生来用于理解市场："),
    (19.8, 24.75, "价格、动量、资金、消息，\n以及它们所处的市场体制。"),
    (25.0, 29.4, "但它多做了一件事：\n每个信号都是一次承诺。"),
    (29.4, 34.75, "五、十、二十个交易日后，\n市场终会回来批改。"),
    (35.0, 38.2, "第一课来自矛盾。"),
    (38.2, 43.0, "同一只股票的两个冲突信号\n评分 +40 和 +45，"),
    (43.0, 47.75, "五日均下跌 9.3%；\n另一个 +92，上涨 15.8%。"),
    (48.0, 53.0, "证据冲突、判断不强时，\n不交易。"),
    (53.0, 57.75, "一次错误，\n变成一道护栏。"),
    (58.0, 63.0, "更多信号完成回填。\n所谓“弱多”区间，"),
    (63.0, 69.75, "四次判断，四次全错，\n平均下跌 6.58%。"),
    (70.0, 73.5, "TideWatch 不再美化\n不可靠的答案。"),
    (73.5, 76.75, "它直接删除了这个答案。"),
    (77.0, 80.5, "接着，是最反直觉的一课。"),
    (80.5, 85.5, "接近满分的判断\n只有 56.3% 正确，"),
    (85.5, 90.75, "较低区间却达到 89.5%。"),
    (91.0, 95.0, "系统不再照单全收\n自己的自信。"),
    (95.0, 99.5, "方向翻转被惩罚，\n噪声因子降权，"),
    (99.5, 103.75, "更可靠的证据得到加强。"),
    (104.0, 108.2, "当信号增长到 135 条，\n隐藏变量终于浮现："),
    (108.2, 115.75, "高置信度达到 72.1%，\n低置信度只有 47.8%。"),
    (116.0, 119.5, "TideWatch 学会了\n最难的一课："),
    (119.5, 123.75, "没有把握时，\n不要强行给出方向。"),
    (124.0, 128.0, "今天，每次分析都进入\n同一个循环："),
    (128.0, 134.75, "预测、记忆、验证、自省，\n然后再次出发。"),
    (135.0, 140.0, "它被创造来理解市场，\n但只有市场能教会它成长。"),
    (140.0, 144.75, "TideWatch。\n生于预测，师从市场。"),
]


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def stamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def narration_and_srt() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tidewatch-narration-") as temporary:
        temp = Path(temporary)
        segment_paths: list[Path] = []
        for index, (start, end, english, _) in enumerate(SEGMENTS):
            path = temp / f"segment-{index:02}.aiff"
            run(["say", "-v", VOICE, "-r", RATE, "-o", str(path), english])
            duration = probe_duration(path)
            if duration > end - start:
                raise RuntimeError(
                    f"Narration segment {index + 1} is {duration:.2f}s but its slot is {end - start:.2f}s"
                )
            segment_paths.append(path)

        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        for path in segment_paths:
            command += ["-i", str(path)]
        filters = []
        labels = []
        for index, (start, _, _, _) in enumerate(SEGMENTS):
            label = f"a{index}"
            filters.append(f"[{index}:a]adelay={round(start * 1000)}:all=1[{label}]")
            labels.append(f"[{label}]")
        filters.append(
            f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
            f"apad=pad_dur={TOTAL_SECONDS},atrim=0:{TOTAL_SECONDS},volume=-4.5dB,aresample=48000[aout]"
        )
        command += [
            "-filter_complex", ";".join(filters), "-map", "[aout]", "-ac", "1", "-c:a", "pcm_s16le",
            str(OUT / "narration-en.wav"),
        ]
        run(command)

    srt_lines = []
    for index, (start, end, chinese) in enumerate(SUBTITLES, start=1):
        srt_lines += [str(index), f"{stamp(start)} --> {stamp(end - .25)}", chinese, ""]
    (OUT / "subtitles-zh.srt").write_text("\n".join(srt_lines), encoding="utf-8")


def generated_soundscape() -> None:
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
        f"anoisesrc=color=pink:amplitude=0.07:duration={TOTAL_SECONDS}:sample_rate=48000",
        "-af", f"highpass=f=70,lowpass=f=1300,tremolo=f=0.1:d=0.55,volume=2.0,afade=t=in:d=3,afade=t=out:st={TOTAL_SECONDS - 8}:d=8",
        "-ac", "2", "-c:a", "pcm_s16le", str(OUT / "tide-ambience.wav"),
    ])
    music_inputs = [55.0, 82.41, 110.0]
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    for frequency in music_inputs:
        command += ["-f", "lavfi", "-i", f"sine=frequency={frequency}:duration={TOTAL_SECONDS}:sample_rate=48000"]
    command += [
        "-filter_complex",
        f"[0:a]volume=0.10[a0];[1:a]volume=0.055[a1];[2:a]volume=0.025[a2];"
        f"[a0][a1][a2]amix=inputs=3:normalize=0,lowpass=f=520,tremolo=f=0.1:d=0.18,volume=2.8,"
        f"afade=t=in:d=5,afade=t=out:st={TOTAL_SECONDS - 8}:d=8,aresample=48000[aout]",
        "-map", "[aout]", "-ac", "2", "-c:a", "pcm_s16le", str(OUT / "music.wav"),
    ]
    run(command)


def sound_effect(name: str, first: int, second: int, first_duration: float, second_duration: float) -> None:
    output = OUT / name
    run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency={first}:duration={first_duration}:sample_rate=48000",
        "-f", "lavfi", "-i", f"sine=frequency={second}:duration={second_duration}:sample_rate=48000",
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1,volume=1.0,afade=t=out:st=0.22:d=0.18[aout]",
        "-map", "[aout]", "-ac", "2", "-c:a", "pcm_s16le", str(output),
    ])


def main() -> None:
    narration_and_srt()
    generated_soundscape()
    sound_effect("sfx-signal-write.wav", 620, 880, .12, .28)
    sound_effect("sfx-outcome-backfill.wav", 360, 520, .14, .26)
    sound_effect("sfx-rule-write.wav", 220, 440, .18, .32)
    for path in sorted(OUT.iterdir()):
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
