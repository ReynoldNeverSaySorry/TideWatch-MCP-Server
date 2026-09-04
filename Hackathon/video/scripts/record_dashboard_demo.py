#!/usr/bin/env python3
"""Record public-safe TideWatch Dashboard demo clips with real frontend code.

The browser loads src/tidewatch/web from a local static server. Every /api/
request is intercepted and fulfilled from the verified, non-personal fixture
below. The script never connects to the production Dashboard or signals.db.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from playwright.sync_api import Browser, BrowserContext, Page, Route, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "screen-recordings"
SCREENSHOTS = ROOT / "assets" / "screenshots"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH, HEIGHT = 1920, 1080
NOW = datetime.now().astimezone().replace(microsecond=0)


def stock(code: str, name: str, score: int, signal: str, price: float,
          sparkline: list[float], context: str, *, conflict: str = "") -> dict:
    conflicts = [{"description": conflict}] if conflict else []
    return {
        "code": code,
        "name": name,
        "score": score,
        "signal": signal,
        "price": price,
        "sparkline": sparkline,
        "context": context,
        "conflicts": conflicts,
        "reasons_bull": ["趋势改善", "动量回升"] if score > 0 else [],
        "reasons_bear": ["资金偏弱", "波动放大"] if score < 0 else ["资金证据仍偏弱"],
    }


OVERVIEW = {
    "meta": {
        "status": "fresh",
        "source": ["SANITIZED DEMO FIXTURE"],
        "market_data_date": NOW.date().isoformat(),
        "age_seconds": 12,
    },
    "timestamp": NOW.isoformat(),
    "holdings": [],
    "watchlist": [
        stock(
            "002111", "威海广泰", 45, "中性观望", 11.20,
            [12.12, 11.96, 11.80, 11.62, 11.48, 11.31, 11.20],
            "冲突证据且判断不强，护栏建议等待",
            conflict="技术动量回升，但资金证据仍偏弱",
        ),
        stock(
            "300763", "锦浪科技", 92, "看多", 58.60,
            [50.60, 51.40, 52.80, 54.10, 55.70, 57.20, 58.60],
            "强信号案例，仅用于历史回填演示",
        ),
    ],
    "hot_strongest": [
        stock("600900", "长江电力", 62, "看多", 29.14,
              [28.20, 28.35, 28.41, 28.66, 28.80, 29.00, 29.14], "公开演示股票"),
    ],
    "hot_weakest": [
        stock("600585", "海螺水泥", -38, "看空", 24.30,
              [25.70, 25.50, 25.20, 24.90, 24.76, 24.52, 24.30], "公开演示股票"),
    ],
    "pool_size": {"scanned": 4, "total": 4},
    "account": {},
}

REGIME = {
    "regime": {
        "regime": "sideways_volatile",
        "emoji": "🌊",
        "description": "震荡 · 高波动",
    }
}

DETAIL = {
    "meta": {"status": "fresh", "warnings": []},
    "stock": {"code": "002111", "name": "威海广泰", "price": 11.20, "pct_change": -1.80},
    "signal": {
        "direction": "中性观望",
        "raw_score": 45,
        "adjusted_score": 45,
        "confidence": 36,
        "regime_adjustment": 0,
    },
    "technical": {
        "trend": {"score": 45},
        "momentum": {"rsi_14": 58.2, "macd_cross": "金叉"},
        "volume": {"volume_ratio": 0.82, "shrinking": True, "expanding": False},
        "volatility": {"boll_position": 64.0, "atr_14": 0.38},
        "ma": {"bullish_aligned": False, "bearish_aligned": False},
        "price_position": {"pct_5d": -9.3, "pct_20d": -4.8},
        "patterns": ["短期动量回升", "成交量尚未确认"],
    },
    "money_flow": {"main_net_inflow": -1680000, "main_net_inflow_pct": -4.6},
    "regime": {"regime": "sideways_volatile", "emoji": "🌊", "description": "震荡 · 高波动"},
    "news": [{"title": "演示数据：消息面保持中性"}],
    "conflicts": [{
        "type": "技术与资金冲突",
        "description": "技术动量回升，但资金证据仍偏弱",
        "advice": "冲突存在时，降低确信度并等待更多证据。",
    }],
    "guardrails": [{
        "message": "冲突信号且 |score| < 50",
        "advice": "WAIT ADVISED",
    }],
    "advice": {},
    "narrative": (
        "**证据并不一致。** 技术指标开始修复，但资金尚未确认。\n"
        "历史案例显示，弱冲突信号不值得强行给出方向，因此当前保持中性观望。"
    ),
    "portfolio_context": "SANITIZED DEMO · NO ACCOUNT DATA",
}

REVIEW = {
    "stats": {
        "total_signals": 2,
        "win_stats": {
            "5d": {"total_filled": 2, "correct": 1, "win_rate": 50.0},
            "10d": {"total_filled": 0, "correct": 0, "win_rate": None},
            "20d": {"total_filled": 0, "correct": 0, "win_rate": None},
        },
    },
    "signals": [
        {
            "id": 1, "date": "2026-03-23", "time": "15:30", "symbol": "002111",
            "name": "威海广泰", "direction": "看多", "score": 45, "price": 12.35,
            "5d": "-9.3% (wrong)",
        },
        {
            "id": 2, "date": "2026-03-22", "time": "15:30", "symbol": "300763",
            "name": "锦浪科技", "direction": "看多", "score": 92, "price": 50.60,
            "5d": "+15.8% (correct)",
        },
    ],
    "timestamp": "2026-03-30T15:30:00+08:00",
}


def fulfill_json(route: Route, body: dict, status: int = 200) -> None:
    route.fulfill(
        status=status,
        content_type="application/json; charset=utf-8",
        body=json.dumps(body, ensure_ascii=False),
    )


def api_route(route: Route) -> None:
    url = route.request.url
    if "/api/auth/session" in url:
        fulfill_json(route, {"authenticated": True})
    elif "/api/dashboard/overview" in url or "/api/dashboard/refresh" in url:
        fulfill_json(route, OVERVIEW)
    elif "/api/dashboard/regime" in url:
        fulfill_json(route, REGIME)
    elif "/api/dashboard/stocks/" in url:
        fulfill_json(route, DETAIL)
    elif "/api/dashboard/signals" in url:
        fulfill_json(route, REVIEW)
    elif "/api/dashboard/narrative" in url:
        fulfill_json(route, {"narrative": DETAIL["narrative"]})
    elif "/api/dashboard/backfill" in url:
        fulfill_json(route, {"updated": {"5d": 0, "10d": 0, "20d": 0}})
    else:
        fulfill_json(route, {"error": "Blocked outside sanitized demo fixture"}, status=404)


def install_demo_badge(page: Page) -> None:
    page.add_style_tag(content="""
      #hackathonDemoBadge {
        position: fixed; right: 24px; bottom: 22px; z-index: 20000;
        padding: 10px 16px; border: 1px solid #42e8df; border-radius: 8px;
        background: rgba(6,18,29,.92); color: #42e8df;
        font: 600 16px/1.2 'JetBrains Mono', monospace; letter-spacing: .04em;
        box-shadow: 0 8px 30px rgba(0,0,0,.25);
      }
    """)
    page.evaluate("""
      () => {
        const badge = document.createElement('div');
        badge.id = 'hackathonDemoBadge';
        badge.textContent = 'SANITIZED LOCAL DEMO · NO LIVE ACCOUNT';
        document.body.appendChild(badge);
      }
    """)


def prepare_page(context: BrowserContext, base_url: str) -> Page:
    context.route("**/api/**", api_route)
    context.route("https://fonts.googleapis.com/**", lambda route: route.abort())
    context.route("https://fonts.gstatic.com/**", lambda route: route.abort())
    page = context.new_page()
    page.goto(base_url, wait_until="networkidle")
    page.wait_for_selector("#loading.hidden")
    page.wait_for_selector('[data-code="002111"]')
    install_demo_badge(page)
    return page


def transcode(source: Path, target: Path) -> None:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", "30", "-an", "-movflags", "+faststart", str(target),
    ], check=True)


def record_clip(browser: Browser, base_url: str, name: str,
                action: Callable[[Page], None]) -> None:
    with tempfile.TemporaryDirectory(prefix=f"tidewatch-{name}-") as temporary:
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            record_video_dir=temporary,
            record_video_size={"width": WIDTH, "height": HEIGHT},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = prepare_page(context, base_url)
        page.wait_for_timeout(1200)
        action(page)
        page.screenshot(path=str(SCREENSHOTS / f"{name}.png"), full_page=False)
        video = page.video
        page.close()
        context.close()
        assert video is not None
        webm = Path(video.path())
        transcode(webm, OUT / f"{name}.mp4")


def overview_action(page: Page) -> None:
    page.locator('#refreshBtn').click()
    page.wait_for_timeout(3200)


def detail_action(page: Page) -> None:
    page.locator('[data-code="002111"]').click()
    page.wait_for_selector("#detailOverlay.show")
    page.wait_for_selector(".guardrail-alert")
    page.wait_for_timeout(4300)


def review_action(page: Page) -> None:
    page.locator('.tab-btn[data-tab="review"]').click()
    page.wait_for_selector(".signal-review-card")
    page.wait_for_timeout(4300)


def mcp_action(page: Page) -> None:
    page.set_content("""
    <!doctype html><meta charset="utf-8"><style>
      *{box-sizing:border-box}body{margin:0;background:#06121d;color:#edf7fb;font-family:Arial,sans-serif}
      body:before{content:'';position:fixed;inset:0;background-image:linear-gradient(#092033 1px,transparent 1px),linear-gradient(90deg,#092033 1px,transparent 1px);background-size:80px 80px;opacity:.8}
      main{position:relative;padding:70px 100px}.eyebrow{color:#42e8df;font:26px monospace}.title{font-size:64px;font-weight:700;margin:24px 0 40px}
      .terminal{background:#0d2232;border:1px solid #23506a;border-radius:18px;overflow:hidden;box-shadow:0 30px 80px #0008}
      .bar{height:58px;padding:18px 24px;background:#102b3d;color:#8aa8b8;font:18px monospace}.body{padding:34px 42px;font:26px/1.6 monospace;min-height:600px}
      .prompt{color:#42e8df}.muted{color:#8aa8b8}.amber{color:#ffb84a}.ok{color:#48d597}.line{opacity:0;transform:translateY(8px);transition:.35s}.show{opacity:1;transform:none}
      .badge{position:fixed;right:24px;bottom:22px;padding:10px 16px;border:1px solid #42e8df;border-radius:8px;background:#06121deb;color:#42e8df;font:600 16px monospace}
    </style><main><div class="eyebrow">TIDEWATCH // MCP DEMO</div><div class="title">One question. A traceable answer.</div>
    <div class="terminal"><div class="bar">MCP client · sanitized local run · no account context</div><div class="body">
      <div class="line" id="l1"><span class="prompt">›</span> analyze_stock(symbol="002111", skip_llm=true)</div>
      <div class="line muted" id="l2">↳ 8-dimensional analysis · market regime · conflict detection</div>
      <div class="line" id="l3">score <b>+45</b> · confidence <b>36</b> · direction <span class="amber">WAIT</span></div>
      <div class="line amber" id="l4">⚠ technical momentum improved, but capital evidence stayed weak</div>
      <div class="line ok" id="l5">🛡 CONFLICT + |SCORE| &lt; 50 → WAIT ADVISED</div>
      <div class="line muted" id="l6">Historical fixture · verified case · not investment advice</div>
    </div></div></main><div class="badge">SANITIZED LOCAL DEMO · REAL TOOL SCHEMA</div>
    """)
    for index in range(1, 7):
        page.locator(f"#l{index}").evaluate("el => el.classList.add('show')")
        page.wait_for_timeout(650 if index < 3 else 850)
    page.wait_for_timeout(2200)


def digest_action(page: Page) -> None:
    page.set_content("""
    <!doctype html><meta charset="utf-8"><style>
      *{box-sizing:border-box}body{margin:0;background:#eef3f6;color:#152530;font-family:Arial,sans-serif}
      .scene{height:1080px;display:grid;grid-template-columns:1fr 760px 1fr;align-items:center;background:radial-gradient(circle at 50% 50%,#fff 0,#eef3f6 62%,#dce8ed 100%)}
      .phone{grid-column:2;background:#f4f4f4;border:14px solid #10212b;border-radius:54px;box-shadow:0 35px 90px #243b4770;overflow:hidden;height:980px}
      .top{height:94px;background:#f7f7f7;border-bottom:1px solid #d6d6d6;padding:26px 34px;text-align:center;font-size:25px;font-weight:600}
      .sub{font-size:13px;color:#87939a;font-weight:400;margin-top:4px}.chat{padding:40px 30px}.row{display:flex;align-items:flex-start;gap:16px;margin-bottom:28px}
      .avatar{width:62px;height:62px;border-radius:16px;background:#0d2232;color:#42e8df;display:grid;place-items:center;font-size:30px}
      .bubble{max-width:575px;background:white;border-radius:8px;padding:22px 25px;font-size:21px;line-height:1.55;box-shadow:0 2px 8px #00000012}
      .bubble b{display:block;font-size:23px;margin-bottom:10px}.rule{margin-top:14px;padding:12px 14px;border-left:4px solid #ffb84a;background:#fff8ea;font:18px monospace;color:#8b5b0b}
      .fine{font-size:15px;color:#74848d;margin-top:14px}.badge{position:fixed;right:24px;bottom:22px;padding:10px 16px;border:1px solid #0d6b70;border-radius:8px;background:#06121ded;color:#42e8df;font:600 16px monospace}
      .fade{opacity:0;transform:translateY(12px);transition:.45s}.show{opacity:1;transform:none}
    </style><div class="scene"><div class="phone"><div class="top">TideWatch 盘后简报<div class="sub">SANITIZED PREVIEW · NO CONTACTS · NO ACCOUNT DATA</div></div><div class="chat">
      <div class="row fade" id="d1"><div class="avatar">🌊</div><div class="bubble"><b>9/3 盘后 · 演示</b>今天的重点不是多给一个方向，而是确认哪些答案值得保留。</div></div>
      <div class="row fade" id="d2"><div class="avatar">🌊</div><div class="bubble"><b>历史回填</b>威海广泰弱冲突信号：5 日 −9.3%<br>锦浪科技强冲突信号：5 日 +15.8%<div class="rule">CONFLICT + |SCORE| &lt; 50 → WAIT ADVISED</div><div class="fine">Specific historical cases · Not investment advice</div></div></div>
      <div class="row fade" id="d3"><div class="avatar">🌊</div><div class="bubble"><b>今天学到的</b>低置信度时不强行给出 BUY 或 SELL；让 WAIT 成为一个正式答案。</div></div>
    </div></div></div><div class="badge">SANITIZED LOCAL DEMO · MESSAGE PREVIEW</div>
    """)
    for index in range(1, 4):
        page.locator(f"#d{index}").evaluate("el => el.classList.add('show')")
        page.wait_for_timeout(950)
    page.wait_for_timeout(2800)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    if not Path(CHROME).exists():
        raise SystemExit(f"Chrome executable not found: {CHROME}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=CHROME)
        record_clip(browser, args.url, "dashboard-overview", overview_action)
        record_clip(browser, args.url, "stock-conflict-detail", detail_action)
        record_clip(browser, args.url, "signal-review", review_action)
        record_clip(browser, args.url, "mcp-analysis", mcp_action)
        record_clip(browser, args.url, "wechat-digest-demo", digest_action)
        browser.close()

    for path in sorted(OUT.glob("*.mp4")):
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
