#!/bin/bash
# TideWatch daily cron — 每个工作日北京 18:30 (UTC 10:30)
# 1) scan_market 刷新持仓/自选价格（force_refresh 跳过缓存）
# 2) analyze_stock 对每只持仓生成信号（含 LLM 叙事润色）
# 3) update_signal_outcomes 回填历史信号

LOG=/var/log/tidewatch-daily.log
API_KEY=$(grep "^MCP_API_KEY=" /home/azureuser/GitHub_Workspace/TideWatch-MCP-Server/.env | cut -d= -f2)
URL=http://localhost:8889/mcp

# 周末 early exit；工作日是否交易由 scan_market 的 market_data_date 判定。
TODAY_BJ=$(TZ=Asia/Shanghai date +%Y-%m-%d)
WEEKDAY_BJ=$(TZ=Asia/Shanghai date +%u)
if [ "$WEEKDAY_BJ" -ge 6 ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Weekend, skipping" >> $LOG
    exit 0
fi

call_mcp() {
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Calling $1..." >> $LOG
    R=$(curl -fsS -m ${3:-120} -X POST $URL -H 'Content-Type: application/json' -H 'Accept: application/json' -H "Authorization: Bearer $API_KEY" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}") || {
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $1 FAILED: transport" >> $LOG
        return 1
    }
    SUMMARY=$(echo "$R" | python3 -c '
import json, sys
try:
    outer = json.load(sys.stdin)
    if outer.get("error"):
        raise RuntimeError(outer["error"].get("message", "jsonrpc_error"))
    result = outer.get("result") or {}
    if result.get("isError"):
        raise RuntimeError("mcp_tool_error")
    text = (result.get("content") or [{}])[0].get("text", "")
    data = json.loads(text) if text else result.get("structuredContent", {})
    if data.get("error"):
        raise RuntimeError(str(data["error"]))
    if data.get("degraded"):
        raise RuntimeError("degraded_result")
    print("ok")
except Exception as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(1)
' 2>&1) || {
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $1 FAILED: $SUMMARY" >> $LOG
        return 1
    }
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $1 OK" >> $LOG
}

assert_scan_fresh() {
    echo "$R" | python3 /home/azureuser/GitHub_Workspace/TideWatch-MCP-Server/scripts/validate_scan_response.py \
        --expected-date "$TODAY_BJ" 2>> "$LOG"
}

echo '========================================' >> $LOG
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Daily scan started" >> $LOG

# Step 1: Refresh scan cache (单次即可，scan_market 扫描全部三级池)
call_mcp scan_market '{"top_n":10,"force_refresh":true}' 180 || exit 1
assert_scan_fresh
SCAN_GATE_STATUS=$?
if [ "$SCAN_GATE_STATUS" -eq 3 ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $TODAY_BJ has no market session, skipping" >> $LOG
    exit 0
elif [ "$SCAN_GATE_STATUS" -ne 0 ]; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] scan_market FAILED freshness/coverage gate" >> $LOG
    exit 1
fi

# Step 2: Analyze each holding with LLM (generates signals for tracking)
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Analyzing holdings with LLM..." >> $LOG
HOLDINGS_JSON=$(curl -s -m 30 -X POST $URL -H 'Content-Type: application/json' -H 'Accept: application/json' -H "Authorization: Bearer $API_KEY" -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"manage_holdings","arguments":{"action":"list"}}}')
SYMBOLS=$(echo "$HOLDINGS_JSON" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    text = d.get("result", {}).get("content", [{}])[0].get("text", "")
    data = json.loads(text)
    holdings = data.get("holdings", [])
    for h in holdings:
        sym = h.get("symbol", "")
        if sym:
            print(sym)
except:
    pass
' 2>/dev/null)

if [ -n "$SYMBOLS" ]; then
    for sym in $SYMBOLS; do
        call_mcp analyze_stock "{\"symbol\":\"$sym\"}" 120 || exit 1
        sleep 2
    done
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Holdings analysis completed" >> $LOG
else
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] No holdings found, skipping" >> $LOG
fi

# Step 3: Backfill signal outcomes
call_mcp update_signal_outcomes '{}' 600 || exit 1

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Daily scan completed" >> $LOG
