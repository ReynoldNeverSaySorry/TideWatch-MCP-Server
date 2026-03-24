# TideWatch Hackathon Registration

## Title

**TideWatch: AI Investment Research Copilot via MCP**

## Tagline

TideWatch is an AI-powered investment research copilot built as a Model Context Protocol (MCP) server that brings multi-dimensional stock analysis directly into your IDE. Instead of switching between terminals, websites, and spreadsheets, you simply ask your AI assistant "analyze Tesla" or "scan the market" — and get a comprehensive report covering 8-dimensional technical scoring, 6 market regime detection, behavioral guardrails (anti-FOMO alerts), signal tracking with outcome verification, and LLM-powered narrative synthesis, all in one conversational turn.

## Keywords

MCP, AI Copilot, Investment Research, Stock Analysis, Market Regime Detection, Signal Tracking, Behavioral Guardrails, LLM Narrative, FastMCP, baostock, Multi-Dimensional Scoring

## Description

### Problem

Retail investors face information overload: dozens of tabs, scattered tools, and no systematic way to cross-validate signals. Traditional stock screeners give you numbers but no context. AI chatbots give you generic answers but no real data. The gap between "raw market data" and "actionable, personalized insight" remains wide open.

### Solution

TideWatch is an MCP server that turns any AI assistant (GitHub Copilot, Claude, etc.) into a professional investment research copilot. It exposes 13 specialized tools through the Model Context Protocol:

- **`analyze_stock`** — 8-dimensional technical scoring (trend, momentum, volume, volatility, MACD, RSI, Bollinger, moving averages) with conflict detection ("technicals say buy, but institutional money is flowing out")
- **`get_regime`** — 6-type market regime identification (bull/bear/sideways × volatile/calm), providing the missing context that turns "hold" from lazy advice into informed strategy
- **`scan_market`** — Three-tier stock pool scanning (portfolio → watchlist → curated hot picks) with cached results and progressive loading
- **`review_signals` / `update_signal_outcomes`** — Signal tracking with 5/10/20-day outcome verification. First batch: **76.9% win rate** on 5-day signals
- **Behavioral Guardrails** — Anti-FOMO alerts for chasing highs, excessive trading frequency, and bottom-fishing in downtrends
- **`polish_narrative_llm`** — LLM-powered narrative synthesis that transforms raw numbers into human-readable investment stories, with portfolio-aware context ("you hold 100 shares at ¥45.20, currently down 8%")

### Architecture

Built with **FastMCP** (Python), deployed on Azure VM with Nginx reverse proxy, HTTPS, and API key authentication. Data sources include **baostock** (A-share daily K-lines, zero anti-scraping, 0.28s/stock) and **AKShare** (money flow, news, institutional activity), with **yfinance** for US stocks. A companion web dashboard provides visual market overview with skeleton loading, smart auto-refresh, and progressive detail panels.

### Key Differentiators

1. **MCP-Native** — Lives where developers already work. No new app to install, no new UI to learn. Just talk to your AI assistant.
2. **Conflict Detection** — Surfaces contradictory signals ("RSI oversold + institutional selling") that retail investors systematically miss.
3. **Signal Accountability** — Every signal is tracked and verified against actual outcomes. The system knows its own accuracy.
4. **Behavioral Guardrails** — The only "advisor" that tells you NOT to trade. Anti-FOMO is more valuable than any buy signal.
5. **US + China Market Support** — Dual-market analysis with SPY relative strength benchmarking for US stocks and CSI 300 regime detection for A-shares.

### Impact

- 13 MCP tools, ~3000 lines of production Python
- Deployed and actively used daily since March 11, 2026
- 76.9% signal win rate on first verification batch (5-day horizon)
- Dashboard serves real-time market intelligence with <2s load time (cached)
- Reduced daily investment research time from ~30 minutes to ~2 minutes of natural conversation
