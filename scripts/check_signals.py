#!/usr/bin/env python3
"""快速查看信号回填状态"""
import requests, json, sys

ENV_PATH = ".env"
URL = "https://tidewatch.polly.wang/mcp"

# 读 API Key
with open(ENV_PATH) as f:
    for line in f:
        if line.startswith("MCP_API_KEY="):
            key = line.split("=", 1)[1].strip()
            break

def mcp_call(tool, args=None):
    r = requests.post(URL,
        json={"jsonrpc": "2.0", "method": "tools/call",
              "params": {"name": tool, "arguments": args or {}}, "id": 1},
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream",
                 "X-API-Key": key},
        timeout=120)
    data = r.json()
    return json.loads(data["result"]["content"][0]["text"])

# 如果传了 --backfill 参数，先回填
if "--backfill" in sys.argv:
    print("📊 回填中...")
    result = mcp_call("update_signal_outcomes")
    u = result.get("updated", {})
    print(f"  5d={u.get('5d',0)} | 10d={u.get('10d',0)} | 20d={u.get('20d',0)} | errors={u.get('errors',0)}")
    if u.get("message"):
        print(f"  {u['message']}")
    print()

# 查看信号
result = mcp_call("review_signals", {"days": 30})
stats = result.get("stats", {})
print(f"总信号: {result.get('total', '?')}")
print(f"5d回填: {stats.get('filled_5d', '?')} | 胜率: {stats.get('win_rate_5d', '?')}")
print(f"10d回填: {stats.get('filled_10d', '?')} | 20d回填: {stats.get('filled_20d', '?')}")
print()

for s in result.get("signals", [])[:10]:
    f = "✅" if s.get("outcome_5d") else "⏳"
    o5 = s.get("outcome_5d", "待回填")
    print(f"  {s['date']} | {s['symbol']:>8} {s.get('name',''):8} | score={s['score']:>4} | 5d={str(o5):20} {f}")

# 已回填统计
filled = [s for s in result.get("signals", []) if s.get("outcome_5d")]
pending = [s for s in result.get("signals", []) if not s.get("outcome_5d")]
print(f"\n已回填: {len(filled)} | 待回填: {len(pending)}")
if filled:
    correct = sum(1 for s in filled if "correct" in str(s.get("outcome_5d", "")))
    print(f"正确: {correct}/{len(filled)}")
