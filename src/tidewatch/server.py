"""
观潮 (TideWatch) — MCP Server
AI 投研搭档，多维融合股票分析引擎

Supports two transport modes:
  - stdio:  For local Claude Desktop / Cursor integration (default)
  - http:   For remote HTTP access (Streamable HTTP)

Usage:
    # stdio mode (default, for local use)
    poetry run tidewatch

    # HTTP mode (for remote access behind Nginx)
    poetry run tidewatch --http --port 8889

    # Or with uvicorn directly
    uvicorn tidewatch.server:http_app --host 0.0.0.0 --port 8889

Client Configuration:
    {
        "url": "https://tidewatch.polly.wang/mcp",
        "headers": {"X-API-Key": "your-api-key"}
    }

MCP Tools:
  - analyze_stock     个股综合分析（技术面+资金面+消息面）
  - get_regime        市场体制识别（牛/熊/横盘/高波动）
  - scan_signals      全市场扫描强势/弱势信号
  - compare_stocks    多股横向对比
  - get_money_flow    资金流向分析
  - get_stock_news    个股相关新闻
"""

import asyncio
import argparse
import base64
import concurrent.futures
import hashlib
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time as _time
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 北京时间 UTC+8
_BJ_TZ = timezone(timedelta(hours=8))

def _now_bj():
    return datetime.now(_BJ_TZ)

# analyze_stock 盘后缓存：{"symbol:YYYY-MM-DD": report}，同一股票同一交易日盘后只算一次
_analyze_cache: dict = {}
_analyze_cache_date: str = ""  # 当前缓存的交易日，新交易日自动清空
from typing import Any

import pandas as pd
import numpy as np
from dotenv import load_dotenv
from fastmcp import FastMCP

from .data import MarketData, is_us_stock
from .guardrails import check_guardrails
from .llm import polish_narrative
from .narrative import NarrativeGenerator
from .portfolio import (
    add_holding, remove_holding, get_holdings,
    add_watchlist, remove_watchlist, get_watchlist,
    set_account_info, get_account_info,
    get_scan_pool, HOT_POOL, HOT_NAMES,
    register_change_callback,
)
from .regime import RegimeDetector
from .strategy import (
    OFFICIAL_STRATEGY_VERSION,
    SHADOW_POLICY_VERSION,
    should_record_shadow_scan,
    v4_official_decision,
    v5_shadow_decision,
)
from .technical import TechnicalAnalyzer
from .tracker import (
    get_recent_signals,
    get_signal_stats,
    record_shadow_scan,
    record_signal,
    update_outcomes,
    update_shadow_outcomes,
)

# ============================================================================
# 配置加载
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent.parent

config_path = PROJECT_ROOT / "config.env"
if config_path.exists():
    load_dotenv(config_path)
# 也加载 .env（优先级更高，可覆盖 config.env 的值）
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

# AKShare 通过东方财富 API 获取数据，代理会导致连接超时
# VS Code 可能注入代理变量，macOS 还有系统级代理
# NO_PROXY=* 告诉 requests 库对所有主机绕过代理
for proxy_var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(proxy_var, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

# 日志配置 — MCP 使用 stdout 通信，日志必须输出到 stderr
log_path = PROJECT_ROOT / "data" / "tidewatch.log"
log_path.parent.mkdir(exist_ok=True)
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        RotatingFileHandler(log_path, maxBytes=20 * 1024 * 1024, backupCount=7),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger(__name__)

# ============================================================================
# MCP 服务器初始化
# ============================================================================

mcp = FastMCP("TideWatch-观潮")

# 核心组件（全局单例）
market_data = MarketData()
technical = TechnicalAnalyzer()
regime_detector = RegimeDetector()
narrator = NarrativeGenerator()
_data_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8, thread_name_prefix="tidewatch-data")
_analysis_slots = asyncio.Semaphore(3)

# HTTP 远程部署配置
MCP_API_KEY = os.getenv("MCP_API_KEY", "")
MCP_API_KEY_ENABLED = bool(MCP_API_KEY)
DASHBOARD_CODE_HASH = os.getenv("TIDEWATCH_DASHBOARD_CODE_HASH", "")
DASHBOARD_SESSION_SECRET = os.getenv("TIDEWATCH_SESSION_SECRET", "")
DASHBOARD_AUTH_DISABLED = os.getenv("TIDEWATCH_AUTH_DISABLED", "").lower() == "true"
DASHBOARD_COOKIE = "tidewatch_session"
DASHBOARD_SESSION_SECONDS = 30 * 24 * 60 * 60
DASHBOARD_SESSION_VERSION = 1

VERSION = "0.3.0"

# 服务器统计
server_stats = {
    "start_time": _now_bj().isoformat(),
    "analyses_completed": 0,
    "scans_completed": 0,
}

# scan_market 缓存（5分钟内复用上次结果，避免频繁请求被封）
_scan_cache = {"result": None, "time": 0}
_SCAN_CACHE_TTL = 300  # 5分钟
_warmup_done = threading.Event()  # 预热完成标志
_scan_bg_refreshing = False  # 后台刷新中标志，防止并发刷新
_scan_run_lock = threading.Lock()  # 所有扫描入口共用 singleflight


# ─── 后台预热 & 定时刷新 ─────────────────────────────────

def _is_market_hours():
    """判断是否在 A 股交易时段（工作日 9:15-15:05，北京时间）"""
    now = _now_bj()
    if now.weekday() >= 5:  # 周末
        return False
    hhmm = now.hour * 100 + now.minute
    return 915 <= hhmm <= 1505


def _expected_market_data_date(now: datetime | None = None) -> str:
    """Expected latest A-share session date, excluding exchange holidays."""
    now = now or _now_bj()
    date = now.date()
    hhmm = now.hour * 100 + now.minute
    if now.weekday() >= 5 or hhmm < 915:
        date -= timedelta(days=1)
        while date.weekday() >= 5:
            date -= timedelta(days=1)
    return date.isoformat()

def _warmup_loop():
    """后台线程：启动预热 + 盘中定时刷新 scan_market 缓存"""
    _time.sleep(3)  # 等服务就绪

    # 只在凌晨 0-7 点（东方财富维护窗口）跳过预热，其他时间都执行
    bj_hour = _now_bj().hour
    if bj_hour >= 7:  # 北京时间 7:00 后都可以预热（包括周末）
        logger.info("🔥 后台预热: 首次 scan_market 开始...")
        try:
            _run_scan_warmup()
            logger.info("🔥 后台预热: 首次 scan_market 完成，缓存已就绪")
        except Exception as e:
            logger.error(f"🔥 后台预热失败: {e}")
    else:
        logger.info(f"🔥 凌晨 {bj_hour}:xx，跳过首次预热（AKShare 维护窗口）")
    _warmup_done.set()  # 无论成功失败都标记完成

    # 定时刷新循环
    while True:
        _time.sleep(_SCAN_CACHE_TTL)  # 每 5 分钟检查一次

        # 💓 baostock 心跳检测（每轮都做，不限盘中）
        try:
            from .data import bs_heartbeat
            if not bs_heartbeat():
                logger.debug("💓 baostock 心跳未就绪")
        except Exception as e:
            logger.error(f"💓 baostock 心跳检测异常: {e}")

        if _is_market_hours():
            try:
                logger.info("🔄 定时刷新: scan_market 缓存更新中...")
                _run_scan_warmup()
                logger.info("🔄 定时刷新: scan_market 缓存已更新")
            except Exception as e:
                logger.error(f"🔄 定时刷新失败: {e}")

def _run_scan_warmup_impl():
    """扫描核心逻辑（唯一实现）— 填充 _scan_cache + 持久化到磁盘"""
    pool = get_scan_pool()
    holdings_info = {h["symbol"]: h for h in get_holdings()}
    watchlist_info = {w["symbol"]: w for w in get_watchlist()}

    # A股/美股分别拉一次体制，各自共用（避免重复拉指数）
    _regime_biases = {}  # {"A": bias, "US": bias}
    _regime_names = {}   # {"A": "mild_bear", "US": "bull"}
    _regime_results = {}
    _benchmark_snapshots = {}
    scan_sources = set()
    market_dates = set()
    for market_key, idx_code in [("A", "000001"), ("US", "SPY")]:
        try:
            idx_df = market_data.get_index_daily(idx_code, days=120)
            if idx_df.attrs.get("source"):
                scan_sources.add(idx_df.attrs["source"])
            r = regime_detector.detect(idx_df)
            _regime_biases[market_key] = regime_detector.get_regime_adjustment(r["regime"])["signal_bias"]
            _regime_names[market_key] = r["regime"]
            _regime_results[market_key] = r
            if not idx_df.empty:
                _benchmark_snapshots[market_key] = {
                    "symbol": idx_code,
                    "price": float(idx_df.iloc[-1]["close"]),
                    "date": pd.Timestamp(idx_df.iloc[-1]["date"]).date().isoformat(),
                }
        except Exception:
            _regime_biases[market_key] = 0
            _regime_names[market_key] = ""
            _regime_results[market_key] = {}

    def _score_one(code):
        is_us = is_us_stock(str(code))
        market_key = "US" if is_us else "A"
        regime_bias = _regime_biases[market_key]
        regime_name = _regime_names[market_key]
        try:
            daily = market_data.get_stock_daily(str(code), days=60)
            if daily.empty or len(daily) < 20:
                return None
            if daily.attrs.get("source"):
                scan_sources.add(daily.attrs["source"])
            if "date" in daily.columns:
                market_dates.add(pd.Timestamp(daily.iloc[-1]["date"]).date().isoformat())
            tech_result = technical.analyze(daily)
            if "error" in tech_result:
                return None
            close_col = "close" if "close" in daily.columns else "收盘"
            latest_price = float(daily.iloc[-1].get(close_col, 0))
            pct_col = "pct_change" if "pct_change" in daily.columns else "涨跌幅"
            pct_today = float(daily.iloc[-1].get(pct_col, 0))
            stored_name = holdings_info.get(code, {}).get("name", "")
            watchlist_name = watchlist_info.get(code, {}).get("name", "")
            if stored_name and stored_name != code:
                name = stored_name
            elif watchlist_name and watchlist_name != code:
                name = watchlist_name
            elif code in HOT_NAMES:
                name = HOT_NAMES[code]
            else:
                name = market_data.get_stock_name(str(code))
            raw_score = tech_result["trend"]["score"]
            adjusted = max(-100, min(100, raw_score + regime_bias))
            confidence = _calc_confidence(adjusted, str(code))
            sig, decision_tags = v4_official_decision(adjusted, confidence, regime_name)
            shadow_direction, shadow_tags = v5_shadow_decision(
                sig, adjusted, confidence, regime_name
            )
            benchmark = _benchmark_snapshots.get(market_key, {})
            benchmark_pct_20d = _regime_results.get(market_key, {}).get("metrics", {}).get("pct_20d")
            stock_pct_20d = tech_result.get("price_position", {}).get("pct_20d")
            relative_strength_20d = None
            if stock_pct_20d is not None and benchmark_pct_20d is not None:
                relative_strength_20d = round(float(stock_pct_20d) - float(benchmark_pct_20d), 2)

            # 轻量冲突检测（用 OBV 斜率代替资金流向，零额外网络请求）
            scan_conflicts = []
            trend_score = tech_result["trend"]["score"]
            vol = tech_result.get("volume", {})
            obv_slope = vol.get("obv_slope", 0)
            pct_5d = tech_result.get("price_position", {}).get("pct_5d", 0)
            if trend_score > 10 and obv_slope < -0.02:
                scan_conflicts.append({
                    "type": "tech_vs_money",
                    "description": "⚠️ 技术面偏多但主力资金在流出，可能是诱多",
                })
            if trend_score < -10 and obv_slope > 0.02:
                scan_conflicts.append({
                    "type": "tech_vs_money",
                    "description": "📋 技术面偏空但主力在吸筹，可能是洗盘",
                })
            if trend_score > 20 and regime_name in ("bear", "mild_bear"):
                scan_conflicts.append({
                    "type": "stock_vs_market",
                    "description": "📉 个股技术面强但大盘偏弱，逆势走强需关注持续性",
                })
            if vol.get("expanding") and pct_5d < -3:
                scan_conflicts.append({
                    "type": "volume_price",
                    "description": "🚨 放量下跌，可能是主力出逃信号",
                })
            if vol.get("shrinking") and pct_5d > 3:
                scan_conflicts.append({
                    "type": "volume_price",
                    "description": "📊 缩量上涨，上行动能不足",
                })

            result = {
                "code": str(code), "name": name,
                "price": latest_price, "pct_today": pct_today,
                "score": adjusted,
                "signal": sig,
                "rsi": tech_result["momentum"]["rsi_14"],
                "reasons_bull": tech_result["trend"]["reasons_bull"][:3],
                "reasons_bear": tech_result["trend"]["reasons_bear"][:3],
                "data_source": daily.attrs.get("source", "unknown"),
                "_shadow_record": {
                    "symbol": str(code), "name": name,
                    "signal_source": "holding" if code in holdings_info else "watchlist" if code in watchlist_info else "hot",
                    "policy_version": SHADOW_POLICY_VERSION,
                    "raw_score": raw_score, "adjusted_score": adjusted,
                    "confidence": confidence, "official_direction": sig,
                    "shadow_direction": shadow_direction, "regime": regime_name,
                    "decision_tags": decision_tags + shadow_tags,
                    "price_at_signal": latest_price,
                    "benchmark_symbol": benchmark.get("symbol"),
                    "benchmark_price_at_signal": benchmark.get("price"),
                    "benchmark_date_at_signal": benchmark.get("date"),
                    "relative_strength_20d": relative_strength_20d,
                },
            }
            if scan_conflicts:
                result["conflicts"] = scan_conflicts
            result["sparkline"] = [round(float(x), 2) for x in daily[close_col].tail(7).tolist()]
            if code in holdings_info:
                h = holdings_info[code]
                result["added_at"] = h.get("added_at", "")
                if h.get("cost") and h["cost"] > 0:
                    result["cost"] = h["cost"]
                    result["shares"] = h.get("shares", 0)
                    result["pnl_pct"] = round((latest_price - h["cost"]) / h["cost"] * 100, 2)
                    result["pnl_amount"] = round((latest_price - h["cost"]) * h.get("shares", 0), 2)
            return result
        except Exception as e:
            logger.debug(f"扫描 {code} 失败: {e}")
            return None

    all_symbols = pool["holdings"] + pool["watchlist"] + pool["hot"]
    results = {}
    consecutive_failures = 0
    a_provider_unavailable = False

    # baostock 是单连接串行，不用 ThreadPoolExecutor（更快更稳）
    for sym in all_symbols:
        if a_provider_unavailable and not is_us_stock(str(sym)):
            continue
        try:
            r = _score_one(sym)
            if r:
                results[sym] = r
                consecutive_failures = 0
            else:
                if not is_us_stock(str(sym)):
                    consecutive_failures += 1
        except Exception:
            if not is_us_stock(str(sym)):
                consecutive_failures += 1

        # 级联失败检测：连续 3+ A 股失败 → 暂停重连 baostock
        if consecutive_failures >= 3:
            logger.warning(f"⚠️ 扫描级联失败: 连续 {consecutive_failures} 只 A 股失败，探测 baostock 一次")
            try:
                from .data import _force_close_bs_socket, _bs_login, _bs_lock
                if _bs_lock.acquire(timeout=10):
                    try:
                        _force_close_bs_socket()
                        _time.sleep(1)
                        _bs_login()
                        logger.info("⚠️ baostock 探测成功，继续扫描")
                    finally:
                        _bs_lock.release()
            except Exception as e:
                logger.warning(f"⚠️ baostock 探测失败，本轮不再重试: {e}")
                a_provider_unavailable = True
            consecutive_failures = 0

        _time.sleep(0.05)  # 让出锁给 analyze_stock 请求

    # 持仓/自选末尾重试：只要有任一关键 A 股缺失就重连后补一轮
    critical_symbols = pool["holdings"] + pool["watchlist"]
    missing_critical = [s for s in critical_symbols if s not in results and not is_us_stock(str(s))]
    if missing_critical and not a_provider_unavailable:
        logger.warning(f"🔄 {len(missing_critical)} 只关键 A 股缺失({missing_critical})，末尾重试")
        try:
            from .data import _force_close_bs_socket, _bs_login, _bs_lock
            if _bs_lock.acquire(timeout=10):
                try:
                    _force_close_bs_socket()
                    _time.sleep(2)
                    _bs_login()
                finally:
                    _bs_lock.release()
            for sym in missing_critical:
                try:
                    r = _score_one(sym)
                    if r:
                        results[sym] = r
                        logger.info(f"🔄 重试成功: {sym}")
                except Exception:
                    pass
                _time.sleep(0.05)
        except Exception as e:
            logger.error(f"🔄 末尾重试失败: {e}")

    # 重试后仍有缺失则告警
    still_missing = [s for s in critical_symbols if s not in results]
    if still_missing:
        logger.error(f"❌ 扫描完成但仍有 {len(still_missing)} 只关键股票缺失: {still_missing}")

    scan_ratio = len(results) / len(all_symbols) if all_symbols else 0
    shadow_records = []
    for result in results.values():
        shadow_record = result.pop("_shadow_record", None)
        if shadow_record:
            shadow_records.append(shadow_record)
    shadow_signal_date = next(iter(market_dates)) if len(market_dates) == 1 else None
    benchmark_dates = {
        record.get("benchmark_date_at_signal") for record in shadow_records
    }
    if (
        shadow_records
        and benchmark_dates == {shadow_signal_date}
        and should_record_shadow_scan(
            scan_ratio, shadow_signal_date, _expected_market_data_date(_now_bj())
        )
    ):
        try:
            recorded = record_shadow_scan(shadow_records, shadow_signal_date)
            shadow_updated = update_shadow_outcomes()
            logger.info(
                "🧪 Shadow 扫描: 日期=%s 记录=%d 回填=%s",
                shadow_signal_date, recorded, shadow_updated,
            )
        except Exception as e:
            logger.error(f"🧪 Shadow 扫描记录失败: {e}")

    holding_results = sorted([results[s] for s in pool["holdings"] if s in results], key=lambda x: x["score"], reverse=True)
    watchlist_results = sorted([results[s] for s in pool["watchlist"] if s in results], key=lambda x: x["score"], reverse=True)
    hot_results = sorted([results[s] for s in pool["hot"] if s in results], key=lambda x: x["score"], reverse=True)

    # 持仓额外上下文：技术面弱但仍在盈利区时提示
    for h in holding_results:
        if h.get("pnl_pct") is not None and h["pnl_pct"] > 0 and h["score"] < -10:
            h["context"] = "技术面弱但仍在盈利区，可考虑设置移动止盈"
        elif h.get("pnl_pct") is not None and h["pnl_pct"] < -5 and h["score"] < -20:
            h["context"] = "技术面+亏损双重压力，关注止损位"

    # 自选为空时加引导提示
    watchlist_hint = ""
    if not watchlist_results and not pool["watchlist"]:
        watchlist_hint = "自选池为空，用 manage_watchlist(action='add', symbol='xxx') 添加关注股票"

    scan_result = {
        "holdings": holding_results,
        "watchlist": watchlist_results,
        "watchlist_hint": watchlist_hint,
        "_hot_sorted": hot_results,
        "hot_strongest": hot_results[:10],
        "hot_weakest": sorted(hot_results[-10:], key=lambda x: x["score"]) if len(hot_results) > 10 else [],
        "account": get_account_info(),
        "pool_size": {
            "holdings": len(pool["holdings"]),
            "watchlist": len(pool["watchlist"]),
            "hot": len(pool["hot"]),
            "total": len(all_symbols),
            "scanned": len(results),
        },
        "timestamp": _now_bj().isoformat(),
        "market_data_date": max(market_dates) if market_dates else None,
        "sources": sorted(scan_sources),
    }
    # 残缺缓存覆盖保护：成功率过低时不覆盖旧缓存
    # TODO: 0.5 阈值基于当前 ~32 只池子，若池子缩至 <10 只需调高
    if scan_ratio < 0.5 and _scan_cache["result"]:
        logger.warning(f"⚠️ 扫描成功率过低 ({len(results)}/{len(all_symbols)} = {scan_ratio:.0%})，保留旧缓存")
        return

    _scan_cache["result"] = scan_result
    _scan_cache["time"] = _time.monotonic()

    # 持久化到磁盘（重启后可恢复）
    if len(results) > 0:
        try:
            import json
            cache_path = Path(__file__).parent.parent.parent / "data" / "scan_cache.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(scan_result, ensure_ascii=False, default=str))
            logger.info(f"💾 扫描缓存已持久化: {len(results)} 只股票")
        except Exception as e:
            logger.debug(f"缓存持久化失败: {e}")


def _load_disk_cache():
    """启动时从磁盘恢复上次扫描缓存"""
    try:
        import json
        cache_path = Path(__file__).parent.parent.parent / "data" / "scan_cache.json"
        if cache_path.exists():
            data = json.loads(cache_path.read_text())
            _scan_cache["result"] = data
            _scan_cache["time"] = 0  # 磁盘缓存必须按内容时间判断，不能伪装成刚生成
            logger.info(f"💾 从磁盘恢复扫描缓存: {data.get('pool_size', {}).get('scanned', '?')} 只股票")
            return True
    except Exception as e:
        logger.debug(f"磁盘缓存恢复失败: {e}")
    return False


def _run_scan_warmup():
    """Run at most one full scan; concurrent callers reuse the active snapshot."""
    if not _scan_run_lock.acquire(blocking=False):
        if not _scan_cache["result"]:
            logger.info("♻️ 首次扫描已在进行，等待当前 in-flight")
            with _scan_run_lock:
                return bool(_scan_cache["result"])
        logger.info("♻️ 扫描已在进行，复用当前 in-flight")
        return False
    try:
        _run_scan_warmup_impl()
        return True
    finally:
        _scan_run_lock.release()

# 启动时先尝试从磁盘恢复缓存
_load_disk_cache()


def _invalidate_scan_cache():
    """持仓/账户变更时清除 scan_cache，确保下次 scan_market 重建

    清除两层：
    1. 内存 _scan_cache（MCP 进程内）
    2. 磁盘 scan_cache.json（重启后也不会读到旧数据）
    """
    _scan_cache["result"] = None
    _scan_cache["time"] = 0
    try:
        cache_path = Path(__file__).parent.parent.parent / "data" / "scan_cache.json"
        if cache_path.exists():
            cache_path.unlink()
            logger.info("🗑️ scan_cache.json 已清除（持仓/账户变更）")
    except Exception as e:
        logger.debug(f"清除磁盘缓存失败: {e}")
    logger.info("🔄 scan_cache 已 invalidate（持仓/账户变更）")


# 注册回调：portfolio.py 写 DB 后自动 invalidate scan_cache
register_change_callback(_invalidate_scan_cache)

# 启动后台预热线程（daemon=True 跟随主进程退出）
_warmup_thread = threading.Thread(target=_warmup_loop, daemon=True)
_warmup_thread.start()


# ============================================================================
# MCP Tools
# ============================================================================


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint (no auth required)"""
    from starlette.responses import JSONResponse
    return JSONResponse({
        "status": "healthy",
        "server": "TideWatch-观潮",
        "version": VERSION,
    })


@mcp.custom_route("/", methods=["GET"])
async def dashboard_index(request):
    from starlette.responses import FileResponse
    return FileResponse(PROJECT_ROOT / "src" / "tidewatch" / "web" / "index.html")


@mcp.custom_route("/styles.css", methods=["GET"])
async def dashboard_styles(request):
    from starlette.responses import FileResponse
    return FileResponse(PROJECT_ROOT / "src" / "tidewatch" / "web" / "styles.css", media_type="text/css")


@mcp.custom_route("/app.js", methods=["GET"])
async def dashboard_script(request):
    from starlette.responses import FileResponse
    return FileResponse(PROJECT_ROOT / "src" / "tidewatch" / "web" / "app.js", media_type="text/javascript")


@mcp.custom_route("/api/auth/login", methods=["POST"])
async def dashboard_login(request):
    from starlette.responses import JSONResponse
    if not _dashboard_auth_configured():
        return JSONResponse({"error": "Dashboard auth is not configured"}, status_code=503)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    if not _verify_dashboard_code(str(body.get("code", ""))):
        return JSONResponse({"error": "验证码不正确"}, status_code=401)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        DASHBOARD_COOKIE,
        _create_dashboard_session(),
        max_age=DASHBOARD_SESSION_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        samesite="strict",
        path="/",
    )
    return response


@mcp.custom_route("/api/auth/session", methods=["GET"])
async def dashboard_session(request):
    from starlette.responses import JSONResponse
    valid = _dashboard_auth_configured() and _verify_dashboard_session(request.cookies.get(DASHBOARD_COOKIE, ""))
    return JSONResponse({"authenticated": valid})


@mcp.custom_route("/api/auth/logout", methods=["POST"])
async def dashboard_logout(request):
    from starlette.responses import JSONResponse
    response = JSONResponse({"ok": True})
    response.delete_cookie(DASHBOARD_COOKIE, path="/")
    return response


@mcp.custom_route("/api/dashboard/overview", methods=["GET"])
async def dashboard_overview(request):
    from starlette.responses import JSONResponse
    data = await scan_market(top_n=5)
    return JSONResponse(data)


@mcp.custom_route("/api/dashboard/stocks/{symbol}", methods=["GET"])
async def dashboard_stock(request):
    from starlette.responses import JSONResponse
    symbol = request.path_params["symbol"]
    data = await analyze_stock(
        symbol=symbol, skip_llm=True, include_news=False, include_money_flow=False
    )
    cached_items = []
    cached_scan = _scan_cache.get("result") or {}
    for key in ("holdings", "watchlist", "_hot_sorted", "hot_strongest", "hot_weakest"):
        cached_items.extend(cached_scan.get(key) or [])
    cached_stock = next((item for item in cached_items if str(item.get("code")) == symbol), None)
    if cached_stock and cached_stock.get("conflicts"):
        conflicts = list(data.get("conflicts") or [])
        seen = {(item.get("type"), item.get("description")) for item in conflicts}
        for conflict in cached_stock["conflicts"]:
            key = (conflict.get("type"), conflict.get("description"))
            if key not in seen:
                conflicts.append(conflict)
                seen.add(key)
        data["conflicts"] = conflicts
    if not data.get("degraded"):
        data["meta"] = {
            "status": "partial",
            "warnings": ["资金面与新闻未阻塞快速详情，可通过 MCP 完整分析获取"],
        }
    return JSONResponse(_json_safe(data))


@mcp.custom_route("/api/dashboard/narrative", methods=["POST"])
async def dashboard_narrative(request):
    from starlette.responses import JSONResponse
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    template = str(body.get("template_narrative", ""))[:8000]
    if not template:
        return JSONResponse({"error": "缺少分析模板"}, status_code=400)
    result = await polish_narrative_llm(
        template_narrative=template,
        stock_name=str(body.get("stock_name", ""))[:100],
        score=int(body.get("score", 0)),
        portfolio_context=str(body.get("portfolio_context", ""))[:2000],
        news_headlines=str(body.get("news_headlines", ""))[:4000],
    )
    return JSONResponse(result)


@mcp.custom_route("/api/dashboard/signals", methods=["GET"])
async def dashboard_signals(request):
    from starlette.responses import JSONResponse
    days = min(max(int(request.query_params.get("days", "3650")), 1), 3650)
    limit = min(max(int(request.query_params.get("limit", "5000")), 1), 5000)
    data = await review_signals(days=days, limit=limit)
    return JSONResponse(data)


@mcp.custom_route("/api/dashboard/regime", methods=["GET"])
async def dashboard_regime(request):
    from starlette.responses import JSONResponse
    return JSONResponse(_json_safe(await get_regime()))


@mcp.custom_route("/api/dashboard/backfill", methods=["POST"])
async def dashboard_backfill(request):
    from starlette.responses import JSONResponse
    return JSONResponse(_json_safe(await update_signal_outcomes()))


@mcp.custom_route("/api/dashboard/refresh", methods=["POST"])
async def dashboard_refresh(request):
    from starlette.responses import JSONResponse
    data = await scan_market(top_n=5)
    return JSONResponse(data)


@mcp.tool()
async def analyze_stock(
    symbol: str,
    include_news: bool = True,
    include_money_flow: bool = True,
    days: int = 120,
    skip_llm: bool = False,
):
    """
    个股综合分析 — 技术面 + 资金面 + 消息面 + 市场体制

    这是观潮的核心分析工具，对一只股票进行多维度交叉分析。
    不只看技术指标，还会结合当前大盘体制、资金流向、新闻消息，
    输出带有冲突检测的综合研判。

    Args:
        symbol: 股票代码（A股纯数字如 "002111"，美股字母如 "AAPL"）
        include_news: 是否包含新闻消息面分析（美股暂不支持）
        include_money_flow: 是否包含资金流向（美股暂不支持）
        days: K线天数（默认120个交易日）
        skip_llm: 跳过 LLM 叙事润色（Dashboard 快速模式用，先返回模板叙事）

    Returns:
        综合分析报告，包含技术面、资金面、消息面、市场体制、冲突检测
    """
    # 防御校验：A股6位纯数字 / 美股1-5位字母（拦截误传的时间戳微秒等垃圾输入）
    symbol = symbol.strip()
    if is_us_stock(symbol):
        if not symbol.isalpha() or len(symbol) > 5:
            return {"error": f"无效的美股代码: {symbol}"}
    else:
        if not symbol.isdigit() or len(symbol) != 6:
            return {"error": f"无效的A股代码: {symbol}（应为6位数字）"}

    logger.info(f"📊 开始分析: {symbol}")
    async with _analysis_slots:
        return await asyncio.to_thread(_analyze_stock_sync, symbol, include_news, include_money_flow, days, skip_llm)


def _build_scan_cache_fallback(symbol: str):
    """行情源不可用时，用最近一次完整扫描结果构造透明的降级报告。"""
    cached = _scan_cache.get("result") or {}
    cache_time = cached.get("timestamp")
    try:
        parsed_cache_time = datetime.fromisoformat(cache_time) if cache_time else None
        if parsed_cache_time and not parsed_cache_time.tzinfo:
            parsed_cache_time = parsed_cache_time.replace(tzinfo=_BJ_TZ)
        cache_age = (_now_bj() - parsed_cache_time).total_seconds() if parsed_cache_time else float("inf")
    except (TypeError, ValueError):
        cache_age = float("inf")
    if cache_age > 72 * 60 * 60:
        logger.error("📦 %s 扫描缓存超过72小时，拒绝输出方向性降级报告", symbol)
        return None

    candidates = []
    for key in ("holdings", "watchlist", "_hot_sorted", "hot_strongest", "hot_weakest"):
        candidates.extend(cached.get(key) or [])
    stock = next((item for item in candidates if str(item.get("code")) == symbol), None)
    if not stock:
        return None

    score = int(stock.get("score", 0))
    signal = stock.get("signal", "中性观望")
    reasons_bull = stock.get("reasons_bull") or []
    reasons_bear = stock.get("reasons_bear") or []
    cache_time = cache_time or "未知时间"
    reason_lines = []
    if reasons_bull:
        reason_lines.append("偏多依据：" + "；".join(reasons_bull))
    if reasons_bear:
        reason_lines.append("偏空依据：" + "；".join(reasons_bear))
    reason_text = "\n".join(reason_lines) or "缓存中没有更多技术依据。"

    logger.warning("📦 %s 行情获取失败，返回扫描缓存降级报告（%s）", symbol, cache_time)
    return {
        "degraded": True,
        "degraded_reason": "实时行情数据源暂不可用，当前展示最近一次完整扫描缓存。",
        "stock": {
            "code": symbol,
            "name": stock.get("name", symbol),
            "price": stock.get("price", 0),
            "pct_change": stock.get("pct_today", 0),
        },
        "signal": {
            "direction": signal,
            "raw_score": score,
            "adjusted_score": score,
            "regime_adjustment": 0,
        },
        "technical": {
            "trend": {
                "score": score,
                "reasons_bull": reasons_bull,
                "reasons_bear": reasons_bear,
            },
            "momentum": {"rsi_14": stock.get("rsi")},
        },
        "regime": {"regime": "unknown", "description": "实时体制不可用"},
        "money_flow": {"error": "实时资金数据不可用"},
        "news": [],
        "conflicts": stock.get("conflicts") or [],
        "narrative": (
            f"实时行情数据源暂不可用，以下结论来自 {cache_time} 的扫描缓存。\n\n"
            f"{stock.get('name', symbol)}当前缓存评分为 {score:+d}，信号为“{signal}”。\n"
            f"{reason_text}\n\n"
            "这不是实时深度分析，请勿仅凭此缓存结论进行交易决策。"
        ),
        "timestamp": cache_time,
    }


def _analyze_stock_sync(symbol, include_news, include_money_flow, days, skip_llm):
    global _analyze_cache, _analyze_cache_date
    t0 = _time.monotonic()

    # 盘后缓存：A股 15:05+ 或美股非交易时段，同一股票同一交易日复用上次结果
    now = _now_bj()
    today_str = now.strftime("%Y-%m-%d")
    is_market_closed = now.hour >= 15 or now.hour < 9 or now.weekday() >= 5
    cache_key = f"{symbol}:{today_str}"

    # 新交易日清空旧缓存
    if _analyze_cache_date != today_str:
        _analyze_cache.clear()
        _analyze_cache_date = today_str

    # 盘后 + 非 skip_llm + 缓存命中 → 直接返回
    if is_market_closed and not skip_llm and cache_key in _analyze_cache:
        logger.info(f"📦 {symbol} 盘后缓存命中，0 LLM 调用")
        return _analyze_cache[cache_key]
    # baostock 每次查询都 auto-reconnect，无需等预热

    # ETF 检测（纯前缀判断，无网络请求）
    is_etf = market_data._is_etf(symbol)
    _is_us = is_us_stock(symbol)

    # 核心 K 线先取；失败时立即降级，避免继续放大资金/新闻请求。
    index_code = "SPY" if _is_us else "000001"
    _skip_money = _is_us or is_etf or not include_money_flow
    _skip_news = is_etf or not include_news  # 美股也拉新闻（yfinance）
    _skip_lhb = _is_us or is_etf or (not include_news and not include_money_flow)
    df = market_data.get_stock_daily(symbol, days)
    t1 = _time.monotonic()
    logger.info(f"⏱️ {symbol} 数据拉取: {t1-t0:.1f}s")
    if df.empty:
        return _build_scan_cache_fallback(symbol) or {"error": f"无法获取 {symbol} 的行情数据"}

    # 核心数据有效后再并发获取可选维度；全局执行器限制线程总量。
    f_index = _data_executor.submit(market_data.get_index_daily, index_code, days)
    f_money = _data_executor.submit(market_data.get_money_flow, symbol) if not _skip_money else None
    f_news = _data_executor.submit(market_data.get_stock_news, symbol, 5) if not _skip_news else None
    f_lhb = _data_executor.submit(market_data.get_lhb, symbol) if not _skip_lhb else None

    # 2. 技术分析（基于日K线）
    tech = technical.analyze(df)
    if "error" in tech:
        return tech

    # 股票名称（持仓/自选 → HOT_NAMES → get_stock_name）
    _holdings = get_holdings()
    _wl = get_watchlist()
    _h_name = next((h.get("name", "") for h in _holdings if h["symbol"] == symbol), "")
    _w_name = next((w.get("name", "") for w in _wl if w["symbol"] == symbol), "")
    stock_name = _h_name or _w_name or HOT_NAMES.get(symbol) or market_data.get_stock_name(symbol)

    # 实时行情：直接用日K线最后一条（避免 stock_zh_a_spot_em 全市场爬取 60-90s）
    # PE/PB 也从 K 线取（baostock peTTM/pbMRQ，每日更新，零额外请求）
    last = df.iloc[-1]
    pe_val = float(last.get("pe_ttm", 0)) if pd.notna(last.get("pe_ttm")) else 0
    pb_val = float(last.get("pb_mrq", 0)) if pd.notna(last.get("pb_mrq")) else 0
    realtime = {
        "price": float(last["close"]),
        "pct_change": float(last.get("pct_change", 0)),
        "pe": round(pe_val, 2), "pb": round(pb_val, 2), "total_mv": 0,
    }

    # 3. 市场体制（已并发拉取）— baostock ~0.3s
    index_df = f_index.result(timeout=30)
    regime_result = regime_detector.detect(index_df)
    regime_adj = regime_detector.get_regime_adjustment(regime_result["regime"])

    # 4. 资金面（已并发拉取）/ 美股用 SPY 相对强弱替代 — AKShare 15s 超时
    money = {}
    if f_money:
        try:
            money = f_money.result(timeout=15)
        except (concurrent.futures.TimeoutError, Exception) as e:
            logger.warning(f"⏱️ {symbol} 资金流向超时/失败: {e}")
            money = {}
    if _is_us and not money and not index_df.empty and len(index_df) >= 5:
        spy_pct_5d = (float(index_df.iloc[-1]["close"]) / float(index_df.iloc[-5]["close"]) - 1) * 100
        stock_pct_5d = tech.get("price_position", {}).get("pct_5d", 0)
        money["_us_relative"] = {
            "spy_pct_5d": round(spy_pct_5d, 2),
            "stock_pct_5d": round(stock_pct_5d, 2),
            "relative": round(stock_pct_5d - spy_pct_5d, 2),
        }

    # 5. 消息面（已并发拉取）— AKShare/yfinance 15s 超时
    news = []
    if f_news:
        try:
            news = f_news.result(timeout=15)
        except (concurrent.futures.TimeoutError, Exception) as e:
            logger.warning(f"⏱️ {symbol} 新闻超时/失败: {e}")
            news = []

    # 6. 龙虎榜（已并发拉取，仅 A 股非 ETF）— AKShare 15s 超时
    lhb = []
    if f_lhb:
        try:
            lhb = f_lhb.result(timeout=15)
        except (concurrent.futures.TimeoutError, Exception) as e:
            logger.warning(f"⏱️ {symbol} 龙虎榜超时/失败: {e}")
            lhb = []

    t2 = _time.monotonic()
    logger.info(f"⏱️ {symbol} 分析+体制+资金+新闻: {t2-t1:.1f}s (总 {t2-t0:.1f}s)")

    # 6. 冲突检测
    conflicts = _detect_conflicts(tech, money, regime_result)

    # 7. 综合评分（技术面得分 + 体制调整）
    raw_score = tech["trend"]["score"]
    adjusted_score = raw_score + regime_adj["signal_bias"]
    adjusted_score = max(-100, min(100, adjusted_score))

    # 8. 置信度先算（v4 P0 需要用 confidence 门槛过滤弱信号）
    regime_name = regime_result.get("regime", "")
    confidence_val = _calc_confidence(adjusted_score, symbol)

    # 9. 最终信号（v4, 基于 135 条回填数据, 🦞 交叉验证）
    #   P0: confidence < 40 强制中性（低 conf 47.8% ≈ 抛硬币, 高 conf 72.1%）
    #   P1: 偏空消灭 — [-25,-8) 合入中性（40% 胜率 + 反向收益 +2.07%）
    #   P2: mild_bull 下看空阈值收窄到 -35（mild_bull+偏空 33.3%）
    final_signal, decision_tags = v4_official_decision(
        adjusted_score, confidence_val, regime_name
    )
    if "p0_confidence_downgrade" in decision_tags:
        _p0_original = "看多" if adjusted_score >= 50 else "看空"
        tech["trend"]["reasons_bear"].append(
            f"[P0降级] conf={confidence_val}<40, 原始方向={_p0_original}"
        )

    shadow_direction, shadow_tags = v5_shadow_decision(
        final_signal, adjusted_score, confidence_val, regime_name
    )

    benchmark_symbol = index_code
    benchmark_date_at_signal = ""
    benchmark_price_at_signal = None
    if not index_df.empty:
        benchmark_price_at_signal = float(index_df.iloc[-1]["close"])
        if "date" in index_df.columns:
            benchmark_date_at_signal = pd.Timestamp(index_df.iloc[-1]["date"]).date().isoformat()
    benchmark_pct_20d = regime_result.get("metrics", {}).get("pct_20d")
    stock_pct_20d = tech.get("price_position", {}).get("pct_20d")
    relative_strength_20d = None
    if stock_pct_20d is not None and benchmark_pct_20d is not None:
        relative_strength_20d = round(float(stock_pct_20d) - float(benchmark_pct_20d), 2)

    server_stats["analyses_completed"] += 1

    # 构建持仓上下文（供 LLM 个性化分析）
    _holding = next((h for h in _holdings if h["symbol"] == symbol), None)
    _watching = next((w for w in _wl if w["symbol"] == symbol), None)
    portfolio_ctx = ""
    if _holding:
        cost = _holding.get("cost", 0)
        shares = _holding.get("shares", 0)
        price = realtime.get("price", 0)
        if cost and cost > 0 and shares > 0:
            pnl_pct = round((price - cost) / cost * 100, 2)
            pnl_amt = round((price - cost) * shares, 0)
            if _is_us:
                portfolio_ctx = f"用户持仓: {shares}股，成本价${cost:.2f}，当前浮{'\u76c8' if pnl_pct >= 0 else '\u4e8f'}{abs(pnl_pct):.1f}%（{'+'if pnl_amt>=0 else ''}{pnl_amt:.0f}美元）"
            else:
                lots = shares // 100  # A股1手=100股
                lot_note = f"（仅{lots}手，已是最小持仓单位，无法减半）" if lots <= 1 else f"（{lots}手）"
                portfolio_ctx = f"用户持仓: {shares}股{lot_note}，成本价¥{cost:.2f}，当前浮{'\u76c8' if pnl_pct >= 0 else '\u4e8f'}{abs(pnl_pct):.1f}%（{'+'if pnl_amt>=0 else ''}{pnl_amt:.0f}元）"
        else:
            portfolio_ctx = f"用户持仓: {shares}股"
    elif _watching:
        reason = _watching.get("reason", "")
        portfolio_ctx = f"用户已加入自选股" + (f"，关注原因: {reason}" if reason else "")
    else:
        portfolio_ctx = "用户未持仓，仅在浏览"

    # 追加可用资金上下文（仅 A 股，美股账户是人民币无参考价值）
    _acct = get_account_info()
    if _acct["cash"] > 0 and not _is_us:
        portfolio_ctx += f"\n账户可用资金: ¥{_acct['cash']:,.2f}，总资产: ¥{_acct['total_assets']:,.2f}"

    report = {
        "stock": {
            "code": symbol,
            "name": stock_name,
            "price": realtime.get("price", tech["price_position"]["price"]),
            "pct_change": realtime.get("pct_change", 0),
            "pe": realtime.get("pe", 0),
            "pb": realtime.get("pb", 0),
            "total_mv": realtime.get("total_mv", 0),
        },
        "signal": {
            "direction": final_signal,
            "raw_score": raw_score,
            "adjusted_score": adjusted_score,
            "confidence": confidence_val,
            "regime_adjustment": regime_adj["signal_bias"],
            "strategy_version": OFFICIAL_STRATEGY_VERSION,
            "decision_tags": decision_tags,
            "shadow_direction": shadow_direction,
            "shadow_policy": SHADOW_POLICY_VERSION,
            "shadow_tags": shadow_tags,
            "relative_strength_20d": relative_strength_20d,
        },
        "technical": tech,
        "regime": regime_result,
        "money_flow": money,
        "news": news,
        "lhb": lhb,
        "conflicts": conflicts,
        "advice": {
            "position_max": f"{regime_adj['position_max'] * 100:.0f}%",
            "stop_loss_hint": f"ATR止损建议: 价格 - {tech['volatility']['atr_14'] * regime_adj['stop_loss_multiplier']:.2f}",
        },
        "narrative": narrator.generate(stock_name, tech, regime_result, money, conflicts, final_signal),
        "portfolio_context": portfolio_ctx,
        "timestamp": _now_bj().isoformat(),
    }

    # 9. LLM 叙事润色（可选，失败时保留模板叙事）
    if not skip_llm:
        # 构建结构化数据摘要供 LLM 独立判断
        _vol = tech.get("volume", {})
        _mom = tech.get("momentum", {})
        _ma = tech.get("ma", {})
        _pos = tech.get("price_position", {})
        _boll = tech.get("volatility", {})
        summary_lines = [
            f"方向: {final_signal} | 综合评分: {adjusted_score:+d} (原始{raw_score:+d}, 体制调整{regime_adj['signal_bias']:+d})",
            f"价格: {realtime['price']:.2f} | 5日涨跌: {_pos.get('pct_5d', 0):+.1f}% | 20日位置: {_pos.get('position_20d', 50):.0f}%",
            f"均线: {'多头排列' if _ma.get('bullish_aligned') else '空头排列' if _ma.get('bearish_aligned') else '交织'} | MA5偏离: {_ma.get('price_vs_ma5', 0):+.1f}% | MA20偏离: {_ma.get('price_vs_ma20', 0):+.1f}%",
            f"动量: RSI {_mom.get('rsi_14', 50):.0f} | MACD {_mom.get('macd_cross', '无')}",
            f"量能: 量比 {_vol.get('volume_ratio', 1):.1f}x | OBV斜率 {_vol.get('obv_slope', 0):.3f} | 换手率 {_vol.get('turn_rate', 0):.1f}% (5日均 {_vol.get('avg_turn_5d', 0):.1f}%)",
        ]
        if realtime.get("pe", 0) > 0:
            summary_lines.append(f"估值: PE(TTM) {realtime['pe']:.1f} | PB(MRQ) {realtime['pb']:.2f}")
        summary_lines.append(f"布林: 位置 {_boll.get('boll_position', 50):.0f}% | ATR {_boll.get('atr_14', 0):.2f}")
        summary_lines.append(f"体制: {regime_result.get('description', '')} | 建议仓位 ≤{regime_adj['position_max'] * 100:.0f}%")
        if conflicts:
            conflict_descs = [c.get("description", "") for c in conflicts]
            summary_lines.append(f"冲突: {' | '.join(conflict_descs)}")
        data_summary = "\n".join(summary_lines)

        try:
            report["narrative"] = polish_narrative(
                report["narrative"], stock_name, adjusted_score,
                portfolio_context=portfolio_ctx,
                is_us=_is_us,
                news=news,
                data_summary=data_summary,
            )
        except Exception as e:
            logger.debug(f"LLM 润色跳过: {e}")

    # 10. 行为护栏检测
    try:
        guardrail_warnings = check_guardrails(symbol, tech, score=adjusted_score, conflicts=conflicts)
        if guardrail_warnings:
            report["guardrails"] = guardrail_warnings
            # 护栏警告也加入叙事末尾
            guardrail_text = "\n\n".join(
                f"{w['message']} {w['advice']}" for w in guardrail_warnings
            )
            report["narrative"] += "\n\n" + guardrail_text
    except Exception as e:
        logger.warning(f"行为护栏检测失败: {e}")

    # 11. 记录信号到追踪系统（仅完整分析，skip_llm 模式不写信号 — 防止冒烟测试 / Dashboard 点击污染信号池）
    if not skip_llm:
      try:
        signal_id = record_signal(
            symbol=symbol,
            name=stock_name,
            score=adjusted_score,
            direction=final_signal,
            price=report["stock"]["price"],
            regime=regime_result.get("regime", "unknown"),
            confidence=confidence_val,
            reasons_bull=tech["trend"].get("reasons_bull", []),
            reasons_bear=tech["trend"].get("reasons_bear", []),
            conflicts=conflicts,
            raw_score=raw_score,
            strategy_version=OFFICIAL_STRATEGY_VERSION,
            signal_source="holding" if _holding else "watchlist" if _watching else "manual",
            decision_tags=decision_tags,
            shadow_direction=shadow_direction,
            shadow_policy=SHADOW_POLICY_VERSION,
            benchmark_symbol=benchmark_symbol,
            benchmark_date_at_signal=benchmark_date_at_signal,
            benchmark_price_at_signal=benchmark_price_at_signal,
            relative_strength_20d=relative_strength_20d,
        )
        report["signal"]["tracked_id"] = signal_id
      except Exception as e:
        logger.warning(f"信号记录失败: {e}")

    t3 = _time.monotonic()
    logger.info(f"⏱️ {symbol} 分析完成: 总耗时 {t3-t0:.1f}s (数据{t1-t0:.1f}s + 分析{t2-t1:.1f}s + 其他{t3-t2:.1f}s)")

    # 盘后写入缓存（仅完整分析，非 skip_llm）
    if is_market_closed and not skip_llm:
        _analyze_cache[cache_key] = report
        logger.info(f"📦 {symbol} 盘后缓存已写入")

    return report


@mcp.tool()
async def polish_narrative_llm(
    template_narrative: str,
    stock_name: str,
    score: int,
    portfolio_context: str = "",
    news_headlines: str = "",
):
    """
    LLM 叙事润色 — 将模板叙事润色为自然的分析师语气

    配合 analyze_stock(skip_llm=True) 使用，实现渐进式加载：
    先用模板叙事秒出结果，再异步调用此工具润色。

    Args:
        template_narrative: analyze_stock 返回的模板叙事文本
        stock_name: 股票名称
        score: 综合评分（adjusted_score）
        portfolio_context: 用户持仓上下文
        news_headlines: 新闻标题（换行分隔，由前端从 analyze_stock 结果拼接）

    Returns:
        润色后的叙事文本
    """
    # 将新闻标题字符串还原为 news list
    news = []
    if news_headlines:
        news = [{"title": t.strip()} for t in news_headlines.split("\n") if t.strip()]
    try:
        polished = await asyncio.to_thread(
            polish_narrative,
            template_narrative, stock_name, score,
            portfolio_context=portfolio_context,
            news=news,
        )
        return {"narrative": polished}
    except Exception as e:
        logger.warning(f"LLM 润色失败: {e}")
        return {"narrative": template_narrative}


@mcp.tool()
async def get_regime():
    """
    今日潮势 — 大盘现在是顺风出海还是暴风骤雨？

    通过上证指数的均线斜率、波动率、涨跌比等指标，
    识别市场处于 牛市/熊市/横盘/高波动 中的哪个阶段。
    不同体制下，同一技术形态的含义完全不同。

    Returns:
        当前市场体制及其对交易信号的调整建议
    """
    logger.info("🌊 感知潮势...")

    index_df = await asyncio.to_thread(market_data.get_index_daily, "000001", 120)
    regime_result = regime_detector.detect(index_df)

    if regime_result["regime"] == "unknown":
        return regime_result

    adjustment = regime_detector.get_regime_adjustment(regime_result["regime"])

    # 额外获取几个关键指数的当日表现
    indices = {}
    for code, name in [("000001", "上证指数"), ("399001", "深证成指"), ("399006", "创业板指")]:
        try:
            idx_df = await asyncio.to_thread(market_data.get_index_daily, code, 5)
            if not idx_df.empty:
                latest = idx_df["close"].iloc[-1]
                prev = idx_df["close"].iloc[-2]
                indices[name] = {
                    "close": round(latest, 2),
                    "pct_change": round((latest / prev - 1) * 100, 2),
                }
        except Exception:
            pass

    return {
        "regime": regime_result,
        "adjustment": adjustment,
        "indices": indices,
        "timestamp": _now_bj().isoformat(),
    }


@mcp.tool()
async def compare_stocks(symbols: str):
    """
    多股横向对比 — 在多只股票间比较技术面强弱

    输入逗号分隔的股票代码，对比它们的技术评分、
    趋势强度、量能状况等指标，帮助筛选最强标的。
    注意：对比基于原始技术评分（未加体制调整），跨市场对比（如 AAPL vs 600519）可直接比较。

    Args:
        symbols: 逗号分隔的股票代码，如 "002111,600519,000858" 或 "AAPL,MSFT,TSLA"

    Returns:
        横向对比表格，按技术评分排序
    """
    codes = [s.strip() for s in symbols.split(",") if s.strip()]
    if len(codes) < 2:
        return {"error": "至少需要两只股票进行对比，用逗号分隔"}

    results = []
    for code in codes[:10]:  # 最多10只
        name, df = await asyncio.gather(
            asyncio.to_thread(market_data.get_stock_name, code),
            asyncio.to_thread(market_data.get_stock_daily, code, 120),
        )
        if df.empty:
            results.append({"code": code, "name": name, "error": "数据获取失败"})
            continue

        tech = technical.analyze(df)
        if "error" in tech:
            results.append({"code": code, "name": name, "error": tech["error"]})
            continue

        results.append({
            "code": code,
            "name": name,
            "price": tech["price_position"]["price"],
            "score": tech["trend"]["score"],
            "signal": tech["trend"]["signal"],
            "rsi": tech["momentum"]["rsi_14"],
            "macd_cross": tech["momentum"]["macd_cross"],
            "volume_ratio": tech["volume"]["volume_ratio"],
            "pct_5d": tech["price_position"]["pct_5d"],
            "pct_20d": tech["price_position"]["pct_20d"],
            "position_20d": tech["price_position"]["position_20d"],
            "bullish_aligned": tech["ma"]["bullish_aligned"],
            "patterns": tech["patterns"],
        })

    # 按评分排序
    valid = [r for r in results if "score" in r]
    valid.sort(key=lambda x: x["score"], reverse=True)
    errors = [r for r in results if "error" in r]

    return {
        "comparison": valid + errors,
        "strongest": valid[0]["code"] if valid else None,
        "weakest": valid[-1]["code"] if valid else None,
        "timestamp": _now_bj().isoformat(),
    }


@mcp.tool()
async def get_money_flow_detail(symbol: str, days: int = 10):
    """
    资金流向详细分析 — 查看主力、大单、散户的进出

    分析个股的资金流向趋势，判断主力是在建仓还是出货。
    包含最近N日的资金流向历史和趋势判断。

    Args:
        symbol: 股票代码
        days: 查看天数

    Returns:
        资金流向分析报告
    """
    name, current, history_df, lhb = await asyncio.gather(
        asyncio.to_thread(market_data.get_stock_name, symbol),
        asyncio.to_thread(market_data.get_money_flow, symbol),
        asyncio.to_thread(market_data.get_money_flow_history, symbol, days),
        asyncio.to_thread(market_data.get_lhb, symbol),
    )

    history_summary = {}
    if not history_df.empty and "main_net" in history_df.columns:
        main_net = history_df["main_net"]
        history_summary = {
            "total_main_net": round(main_net.sum(), 2),
            "avg_main_net": round(main_net.mean(), 2),
            "positive_days": int((main_net > 0).sum()),
            "negative_days": int((main_net < 0).sum()),
            "trend": "持续流入" if main_net.tail(3).mean() > 0 else "持续流出",
        }

    return {
        "stock": {"code": symbol, "name": name},
        "current": current,
        "history": history_summary,
        "lhb_records": lhb,
        "timestamp": _now_bj().isoformat(),
    }


@mcp.tool()
async def get_stock_news_report(symbol: str, limit: int = 10):
    """
    个股新闻消息面 — 获取最新相关新闻

    抓取个股相关新闻，帮助判断消息面是利好还是利空。

    Args:
        symbol: 股票代码
        limit: 新闻条数

    Returns:
        新闻列表
    """
    name, news = await asyncio.gather(
        asyncio.to_thread(market_data.get_stock_name, symbol),
        asyncio.to_thread(market_data.get_stock_news, symbol, limit),
    )

    return {
        "stock": {"code": symbol, "name": name},
        "news": news,
        "count": len(news),
        "timestamp": _now_bj().isoformat(),
    }


@mcp.tool()
async def get_north_flow_report(days: int = 20):
    """
    北向资金分析 — 外资动向

    查看近期北向资金（沪股通+深股通）的净流入情况，
    外资被视为"聪明钱"，其动向对大盘有领先指示作用。

    Args:
        days: 查看天数

    Returns:
        北向资金流向报告
    """
    df = await asyncio.to_thread(market_data.get_north_flow, days)
    if df.empty:
        return {"error": "北向资金数据获取失败"}

    net = df["net_inflow"] if "net_inflow" in df.columns else pd.Series()
    summary = {}
    if not net.empty:
        summary = {
            "total_net": round(net.sum(), 2),
            "avg_daily": round(net.mean(), 2),
            "positive_days": int((net > 0).sum()),
            "negative_days": int((net < 0).sum()),
            "recent_3d": round(net.tail(3).sum(), 2),
            "trend": "净流入" if net.tail(5).mean() > 0 else "净流出",
        }

    return {
        "north_flow": summary,
        "days": days,
        "timestamp": _now_bj().isoformat(),
    }


@mcp.tool()
async def server_status():
    """
    查看观潮服务器状态

    Returns:
        服务器运行状态、版本信息、统计数据
    """
    return {
        "name": "观潮 (TideWatch)",
        "version": VERSION,
        "description": "AI 投研搭档 — 多维融合股票分析引擎",
        "stats": server_stats,
        "tools": [t.name for t in await mcp.list_tools()],
    }


@mcp.tool()
async def review_signals(days: int = 30, symbol: str = "", limit: int = 200):
    """
    查看历史信号和胜率统计 — 观潮的自省系统

    回顾过去 N 天的所有分析信号，检查哪些判断对了、哪些错了。
    胜率数据需要先运行 update_signal_outcomes 回填。

    Args:
        days: 查看天数（默认30天）
        symbol: 可选，指定股票代码只看该票
        limit: 最多返回信号条数（默认200）

    Returns:
        信号列表 + 胜率统计
    """
    stats, recent = await asyncio.gather(
        asyncio.to_thread(get_signal_stats, days),
        asyncio.to_thread(get_recent_signals, days, symbol if symbol else None),
    )

    # 简化信号列表（只保留关键字段）
    signals_summary = []
    for s in recent[:limit]:
        entry = {
            "id": s["id"],
            "date": s["timestamp"][:10],
            "time": s["timestamp"][11:16],  # HH:MM
            "symbol": s["symbol"],
            "name": s["name"],
            "direction": s["direction"],
            "score": s["score"],
            "price": s["price_at_signal"],
            "raw_score": s.get("raw_score"),
            "confidence": s.get("confidence"),
            "strategy_version": s.get("strategy_version"),
            "signal_source": s.get("signal_source"),
            "decision_tags": s.get("decision_tags"),
            "shadow_direction": s.get("shadow_direction"),
            "shadow_policy": s.get("shadow_policy"),
            "relative_strength_20d": s.get("relative_strength_20d"),
        }
        # 添加回填结果（如果有）
        if s.get("pct_5d") is not None:
            entry["5d"] = f"{s['pct_5d']:+.1f}% ({s['action_outcome_5d']})"
        if s.get("pct_10d") is not None:
            entry["10d"] = f"{s['pct_10d']:+.1f}% ({s['action_outcome_10d']})"
        if s.get("pct_20d") is not None:
            entry["20d"] = f"{s['pct_20d']:+.1f}% ({s['action_outcome_20d']})"
        for period in ("5d", "10d", "20d"):
            if s.get(f"shadow_outcome_{period}"):
                entry[f"shadow_{period}"] = s[f"shadow_outcome_{period}"]
        signals_summary.append(entry)

    return {
        "stats": stats,
        "signals": signals_summary,
        "timestamp": _now_bj().isoformat(),
    }


@mcp.tool()
async def update_signal_outcomes():
    """
    回填历史信号的实际走势 — 计算胜率

    检查所有未回填的历史信号，获取信号发出后 5/10/20 个交易日的实际价格，
    计算涨跌幅并判断信号是否正确。

    建议每天收盘后运行一次。

    Returns:
        回填统计（更新了多少条 5d/10d/20d 记录）
    """
    result = await asyncio.to_thread(update_outcomes, market_data)
    shadow_result = await asyncio.to_thread(update_shadow_outcomes)
    response = {
        "updated": result,
        "shadow_updated": shadow_result,
        "message": f"回填完成: 5日={result['5d']}条, 10日={result['10d']}条, 20日={result['20d']}条",
        "timestamp": _now_bj().isoformat(),
    }
    error_count = int(result.get("errors", 0))
    if error_count:
        response["degraded"] = True
        response["error"] = f"回填过程中有 {error_count} 条信号处理失败，请检查服务日志"
    return response


@mcp.tool()
async def manage_holdings(
    action: str,
    symbol: str = "",
    cost: float = 0,
    shares: int = 0,
):
    """
    持仓管理 — 添加、移除、查看持仓

    Args:
        action: 操作类型 ("add" / "remove" / "list")
        symbol: 股票代码（add/remove 时必填）
        cost: 买入成本价（add 时填写）
        shares: 持仓数量（add 时填写）

    Returns:
        操作结果和当前持仓列表
    """
    if action == "list":
        holdings = get_holdings()
        return {
            "holdings": holdings,
            "count": len(holdings),
            "message": f"当前持仓 {len(holdings)} 只" if holdings else "暂无持仓",
        }
    elif action == "add":
        if not symbol:
            return {"error": "请提供股票代码"}
        name = HOT_NAMES.get(symbol) or market_data.get_stock_name(symbol)
        add_holding(symbol, name=name, cost=cost, shares=shares)
        return {
            "message": f"✅ 已添加持仓: {symbol} {name}" + (f" 成本{cost} ×{shares}股" if cost else ""),
            "holdings": get_holdings(),
        }
    elif action == "remove":
        if not symbol:
            return {"error": "请提供股票代码"}
        remove_holding(symbol)
        return {
            "message": f"✅ 已移除持仓: {symbol}",
            "holdings": get_holdings(),
        }
    else:
        return {"error": f"未知操作: {action}，请用 add/remove/list"}


@mcp.tool()
async def manage_watchlist(
    action: str,
    symbol: str = "",
    reason: str = "",
):
    """
    自选股管理 — 添加、移除、查看自选

    Args:
        action: 操作类型 ("add" / "remove" / "list")
        symbol: 股票代码（add/remove 时必填）
        reason: 关注原因（add 时可选，如 "底部放量" "等回调"）

    Returns:
        操作结果和当前自选列表
    """
    if action == "list":
        watchlist = get_watchlist()
        return {
            "watchlist": watchlist,
            "count": len(watchlist),
            "message": f"当前自选 {len(watchlist)} 只" if watchlist else "暂无自选股",
        }
    elif action == "add":
        if not symbol:
            return {"error": "请提供股票代码"}
        name = HOT_NAMES.get(symbol) or market_data.get_stock_name(symbol)
        add_watchlist(symbol, name=name, reason=reason)
        return {
            "message": f"✅ 已添加自选: {symbol} {name}" + (f" ({reason})" if reason else ""),
            "watchlist": get_watchlist(),
        }
    elif action == "remove":
        if not symbol:
            return {"error": "请提供股票代码"}
        remove_watchlist(symbol)
        return {
            "message": f"✅ 已移除自选: {symbol}",
            "watchlist": get_watchlist(),
        }
    else:
        return {"error": f"未知操作: {action}，请用 add/remove/list"}


@mcp.tool()
async def manage_account(
    action: str,
    cash: float = 0,
    total_assets: float = 0,
    market_value: float = 0,
):
    """
    账户资金管理 — 更新或查看账户资金信息

    用于记录真实账户的可用资金、总资产和持仓市值，以便 AI 分析时了解仓位空间。
    注意：当前账户资金以人民币计价，美股持仓需自行折算。

    Args:
        action: 操作类型 ("update" / "view")
        cash: 可用资金（update 时填写）
        total_assets: 总资产（update 时填写，0 则不更新）
        market_value: 持仓市值（update 时填写，0 则不更新）

    Returns:
        账户资金摘要 + 持仓概览
    """
    if action == "view":
        account = get_account_info()
        holdings = get_holdings()
        return {
            "account": account,
            "holdings_count": len(holdings),
            "message": f"可用资金 ¥{account['cash']:,.2f} | 总资产 ¥{account['total_assets']:,.2f}" if account["cash"] else "暂未设置账户信息",
        }
    elif action == "update":
        if cash <= 0 and total_assets <= 0:
            return {"error": "请提供 cash（可用资金）或 total_assets（总资产）"}
        set_account_info(cash=cash, total_assets=total_assets, market_value=market_value)
        account = get_account_info()
        return {
            "message": f"✅ 账户已更新: 可用 ¥{account['cash']:,.2f} | 总资产 ¥{account['total_assets']:,.2f} | 市值 ¥{account['market_value']:,.2f}",
            "account": account,
        }
    else:
        return {"error": f"未知操作: {action}，请用 update/view"}


@mcp.tool()
async def scan_market(top_n: int = 10, force_refresh: bool = False):
    """
    三级股票池扫描 — 持仓 + 自选 + 热门，按技术评分排序

    从三级股票池（持仓 > 自选 > 热门80只）批量拉K线做技术分析评分，
    持仓显示浮盈浮亏，所有股票按评分排序。

    不依赖全市场实时行情接口（push2 反爬），使用日K线接口。

    Args:
        top_n: 热门池中返回最强/最弱各多少只（默认10）
        force_refresh: 强制刷新，跳过所有缓存（用于 daily cron 确保拿到最新收盘数据）

    Returns:
        持仓全部 + 自选全部 + 热门 Top/Bottom N，按评分排序
    """
    global _scan_bg_refreshing
    logger.info(f"🔍 三级股票池扫描: Top/Bottom {top_n}, force_refresh={force_refresh}")
    server_stats["scans_completed"] += 1

    # force_refresh: 跳过所有缓存，直接全量扫描
    if force_refresh:
        logger.info("🔄 force_refresh=true，跳过缓存，执行全量扫描...")
        await asyncio.to_thread(_run_scan_warmup)
        return _slice_scan_cache(top_n)

    cache_age = _time.monotonic() - _scan_cache["time"] if _scan_cache["result"] else float("inf")

    # 1) 新鲜缓存（5分钟内）→ 直接返回
    if _scan_cache["result"] and cache_age < _SCAN_CACHE_TTL:
        logger.info("⚙️ 使用扫描缓存（%ds内）", int(_SCAN_CACHE_TTL - cache_age))
        return _slice_scan_cache(top_n)

    # 2) Stale-While-Revalidate: 有旧缓存 → 先返回旧数据，后台异步刷新
    #    - 非盘中 + 缓存是收盘后数据：数据不变，直接返回
    #    - 非盘中 + 缓存是盘中数据：强制刷新（修复 2026-04-08 盲区：13:01 缓存冻结到次日）
    #    - 盘中：返回旧缓存 + 后台刷新，下次请求拿到新数据
    if _scan_cache["result"]:
        if not _is_market_hours():
            # 检查缓存是否是盘中的旧快照（收盘前数据，需刷新为收盘价）
            should_force = False
            cache_ts_str = _scan_cache["result"].get("timestamp", "")
            if cache_ts_str:
                try:
                    cache_ts = datetime.fromisoformat(cache_ts_str)
                    if not cache_ts.tzinfo:
                        cache_ts = cache_ts.replace(tzinfo=_BJ_TZ)
                    now = _now_bj()
                    # 今天 15:30 前的缓存可能不含完整收盘数据（baostock 结算延迟）
                    if (cache_ts.date() == now.date()
                            and cache_ts.hour * 60 + cache_ts.minute < 15 * 60 + 30
                            and now.weekday() < 5):
                        should_force = True
                        logger.info("⚙️ 非盘中但缓存是盘中数据（%s），强制刷新...", cache_ts.strftime("%H:%M"))
                except Exception as e:
                    logger.debug("缓存 timestamp 解析失败: %s", e)
            if not should_force:
                logger.info("⚙️ 非盘中，使用已有缓存（数据不变）")
                return _slice_scan_cache(top_n)
            # 先返回旧缓存，后台补齐收盘数据；上游故障时不能阻塞 Dashboard。
            if not _scan_bg_refreshing:
                _scan_bg_refreshing = True
                asyncio.get_event_loop().run_in_executor(None, _bg_refresh_scan)
            else:
                logger.info("♻️ 收盘数据后台刷新已在进行")
            return _slice_scan_cache(top_n)
        # 盘中过期，先返回后台刷新
        if not _scan_bg_refreshing:
            _scan_bg_refreshing = True
            logger.info("♻️ 返回过期缓存（%ds前），后台刷新中...", int(cache_age))
            asyncio.get_event_loop().run_in_executor(None, _bg_refresh_scan)
        else:
            logger.info("♻️ 返回过期缓存（%ds前），后台刷新已在进行", int(cache_age))
        return _slice_scan_cache(top_n)

    # 3) 完全无缓存 → 阻塞扫描（首次冷启动）
    logger.info("🔍 无缓存，执行全量扫描...")
    await asyncio.to_thread(_run_scan_warmup)
    return _slice_scan_cache(top_n)


def _slice_scan_cache(top_n: int):
    """从缓存中按 top_n 切片返回（过滤内部字段）"""
    cached = _scan_cache["result"]
    hot_all = cached.get("_hot_sorted", [])
    output = {k: v for k, v in cached.items() if not k.startswith("_")}
    output["hot_strongest"] = hot_all[:top_n]
    output["hot_weakest"] = sorted(hot_all[-top_n:], key=lambda x: x["score"]) if len(hot_all) > top_n else []
    timestamp = cached.get("timestamp")
    age_seconds = None
    if timestamp:
        try:
            data_time = datetime.fromisoformat(timestamp)
            if not data_time.tzinfo:
                data_time = data_time.replace(tzinfo=_BJ_TZ)
            age_seconds = max(0, int((_now_bj() - data_time).total_seconds()))
        except (TypeError, ValueError):
            pass
    market_data_date = cached.get("market_data_date")
    now = _now_bj()
    market_date_is_current = market_data_date == _expected_market_data_date(now)
    if age_seconds is None:
        status = "degraded"
    elif market_date_is_current and (not _is_market_hours() or age_seconds <= _SCAN_CACHE_TTL):
        status = "fresh"
    elif age_seconds <= 72 * 60 * 60:
        status = "stale"
    else:
        status = "degraded"
    output["meta"] = {
        "status": status,
        "data_timestamp": timestamp,
        "generated_at": _now_bj().isoformat(),
        "age_seconds": age_seconds,
        "source": cached.get("sources") or ["scan_cache"],
        "market_data_date": market_data_date,
        "refreshing": _scan_run_lock.locked() or _scan_bg_refreshing,
    }
    return output


def _bg_refresh_scan():
    """后台刷新 scan_market 缓存（在线程池中执行）"""
    global _scan_bg_refreshing
    try:
        _run_scan_warmup()
        logger.info("♻️ 后台刷新完成，缓存已更新")
    except Exception as e:
        logger.error(f"♻️ 后台刷新失败: {e}")
    finally:
        _scan_bg_refreshing = False



# ============================================================================
# 内部辅助函数
# ============================================================================


def _calc_confidence(adjusted_score: int, symbol: str) -> int:
    """
    v4 置信度计算 — 过度自信衰减 + 翻转惩罚 + P0 门槛

    数据依据 (135条回填):
    - 高 conf (70+): 72.1% 胜率
    - 中 conf (40-69): 50.0% 胜率
    - 低 conf (<40): 47.8% 胜率 → P0: 强制中性
    - 翻转信号: 33.3% 胜率 (12条) vs 非翻转 62.7% (102条)
    """
    conf = min(abs(adjusted_score), 100)

    # 过度自信衰减：|score|>=85 时 confidence × 0.7
    if abs(adjusted_score) >= 85:
        conf = int(conf * 0.7)

    # 翻转惩罚：方向和上一条信号相反时 × 0.6
    try:
        recent = get_recent_signals(days=7, symbol=symbol)
        if recent:
            prev = recent[0]
            prev_dir = prev.get("direction", "")
            # 注意：这里检测的是「评分方向翻转」而非「信号方向翻转」
            # v3 下 [+8,+50) 的 final_signal 是"中性观望"，但评分确实从负转正，仍属方向翻转
            curr_bullish = adjusted_score >= 8
            curr_bearish = adjusted_score <= -8
            prev_bullish = prev_dir in ("看多", "偏多")
            prev_bearish = prev_dir in ("看空", "偏空")
            if (curr_bullish and prev_bearish) or (curr_bearish and prev_bullish):
                conf = int(conf * 0.6)
    except Exception:
        pass  # 翻转检测失败不阻塞

    return max(conf, 1)


def _detect_conflicts(
    tech: dict, money: dict, regime: dict
) -> list[dict[str, str]]:
    """
    冲突检测 — 发现技术面与其它维度的矛盾信号

    这是观潮的核心差异化功能：
    "技术面看多但主力在出货" 这种矛盾才是真正有价值的洞察
    """
    conflicts = []
    trend = tech.get("trend", {})
    score = trend.get("score", 0)

    # 冲突1: 技术面看多但资金在流出
    if score > 10 and money.get("main_net_inflow", 0) < 0:
        conflicts.append({
            "type": "tech_vs_money",
            "severity": "high",
            "description": "⚠️ 技术面偏多但主力资金在流出，可能是诱多",
            "advice": "等资金回流确认后再进场",
        })

    # 冲突2: 技术面看空但资金在流入
    if score < -10 and money.get("main_net_inflow", 0) > 0:
        conflicts.append({
            "type": "tech_vs_money",
            "severity": "medium",
            "description": "📋 技术面偏空但主力在吸筹，可能是洗盘",
            "advice": "关注是否止跌企稳形成底部",
        })

    # 冲突3: 个股强但大盘弱
    regime_name = regime.get("regime", "")
    if score > 20 and regime_name in ("bear", "mild_bear"):
        conflicts.append({
            "type": "stock_vs_market",
            "severity": "medium",
            "description": "📉 个股技术面强但大盘偏弱，逆势走强需关注持续性",
            "advice": "轻仓试探，设好止损，大盘转好再加仓",
        })

    # 冲突4: 放量下跌
    vol = tech.get("volume", {})
    if vol.get("expanding") and tech.get("price_position", {}).get("pct_5d", 0) < -3:
        conflicts.append({
            "type": "volume_price",
            "severity": "high",
            "description": "🚨 放量下跌，可能是主力出逃信号",
            "advice": "避免抄底，等缩量企稳",
        })

    # 冲突5: 缩量上涨
    if vol.get("shrinking") and tech.get("price_position", {}).get("pct_5d", 0) > 3:
        conflicts.append({
            "type": "volume_price",
            "severity": "medium",
            "description": "📊 缩量上涨，上行动能不足",
            "advice": "关注后续量能能否跟上，否则可能是假突破",
        })

    return conflicts


# ============================================================================
# HTTP Transport: API Key Authentication Middleware
# ============================================================================


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _json_safe(value):
    """Convert pandas/numpy values to JSON-native values without stringifying booleans."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if pd.isna(value) if not isinstance(value, (str, bytes)) else False:
        return None
    return value


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _dashboard_auth_configured() -> bool:
    return DASHBOARD_AUTH_DISABLED or bool(DASHBOARD_CODE_HASH and DASHBOARD_SESSION_SECRET)


def _verify_dashboard_code(code: str) -> bool:
    if DASHBOARD_AUTH_DISABLED:
        return True
    try:
        algorithm, salt_b64, expected_b64 = DASHBOARD_CODE_HASH.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(
            code.encode(), salt=_b64url_decode(salt_b64), n=2**14, r=8, p=1, dklen=32
        )
        return hmac.compare_digest(actual, _b64url_decode(expected_b64))
    except (TypeError, ValueError):
        return False


def _create_dashboard_session() -> str:
    now = int(_time.time())
    payload = _b64url_encode(json.dumps({
        "sub": "polly", "iat": now, "exp": now + DASHBOARD_SESSION_SECONDS,
        "v": DASHBOARD_SESSION_VERSION,
    }, separators=(",", ":")).encode())
    signature = hmac.new(DASHBOARD_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{payload}.{_b64url_encode(signature)}"


def _verify_dashboard_session(token: str) -> bool:
    if DASHBOARD_AUTH_DISABLED:
        return True
    if not token or not DASHBOARD_SESSION_SECRET:
        return False
    try:
        payload, signature = token.split(".", 1)
        expected = hmac.new(DASHBOARD_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(signature)):
            return False
        data = json.loads(_b64url_decode(payload))
        return (
            data.get("sub") == "polly"
            and data.get("v") == DASHBOARD_SESSION_VERSION
            and int(data.get("exp", 0)) > int(_time.time())
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


class APIKeyMiddleware:
    """Pure ASGI middleware to validate API key for protected endpoints."""

    PUBLIC_PATHS = {
        "/", "/health", "/favicon.ico", "/styles.css", "/app.js",
        "/api/auth/login", "/api/auth/session", "/api/auth/logout",
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if path in self.PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        if path.startswith("/api/dashboard/"):
            cookie_header = headers.get(b"cookie", b"").decode()
            cookies = {}
            for part in cookie_header.split(";"):
                if "=" in part:
                    key, value = part.strip().split("=", 1)
                    cookies[key] = value
            if _verify_dashboard_session(cookies.get(DASHBOARD_COOKIE, "")):
                await self.app(scope, receive, send)
                return
            from starlette.responses import JSONResponse
            response = JSONResponse({"error": "Unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        if not MCP_API_KEY_ENABLED:
            await self.app(scope, receive, send)
            return

        # Extract API key from headers
        api_key = ""
        api_key = headers.get(b"x-api-key", b"").decode()
        if not api_key:
            auth_header = headers.get(b"authorization", b"").decode()
            if auth_header.startswith("Bearer "):
                api_key = auth_header[7:]

        if not hmac.compare_digest(api_key, MCP_API_KEY):
            from starlette.responses import JSONResponse
            response = JSONResponse(
                {"error": "Unauthorized", "message": "Invalid or missing API key"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _build_middleware():
    """Build middleware list for HTTP mode."""
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware

    middlewares = [
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]),
    ]
    if MCP_API_KEY_ENABLED:
        middlewares.append(Middleware(APIKeyMiddleware))
    return middlewares


def _create_http_app():
    """Create ASGI app for uvicorn direct usage."""
    return mcp.http_app(
        path="/mcp",
        middleware=_build_middleware(),
        json_response=True,
        stateless_http=True,
    )


# Expose for `uvicorn tidewatch.server:http_app`
http_app = _create_http_app()


# ============================================================================
# Entry Point
# ============================================================================


def main():
    """启动 TideWatch MCP Server（支持 stdio / http 双模式）"""
    parser = argparse.ArgumentParser(description="观潮 (TideWatch) MCP Server")
    parser.add_argument("--http", action="store_true", help="Run in HTTP mode (default: stdio)")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8889, help="HTTP port (default: 8889)")
    args = parser.parse_args()

    logger.info("🌊 观潮 (TideWatch) MCP Server 启动中...")
    logger.info(f"版本: {VERSION}")
    logger.info("工具: analyze_stock, get_regime, compare_stocks, get_money_flow_detail, get_stock_news_report, get_north_flow_report")

    if args.http:
        logger.info(f"传输模式: HTTP (Streamable HTTP) → {args.host}:{args.port}/mcp")
        logger.info(f"API Key 认证: {'✅ 已启用' if MCP_API_KEY_ENABLED else '❌ 未配置'}")
        import uvicorn
        uvicorn.run(http_app, host=args.host, port=args.port)
    else:
        logger.info("传输模式: stdio (本地)")
        mcp.run()


if __name__ == "__main__":
    main()
