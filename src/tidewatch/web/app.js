let detailRequestId = 0;  // 递增 ID，用于竞态取消
const detailCache = {};  // { code: { data, narrative, time } }

function showToast(msg, duration = 4000, type = '') {
  let el = document.getElementById('toast');
  if (!el) { el = document.createElement('div'); el.id = 'toast'; el.className = 'toast'; document.body.appendChild(el); }
  el.textContent = msg;
  el.className = 'toast' + (type ? ' ' + type : '');
  el.classList.add('show');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('show'), duration);
}

function showAuthGate() {
  document.getElementById('authGate').classList.remove('hidden');
  setTimeout(() => document.getElementById('accessCode').focus(), 0);
}

function hideAuthGate() {
  document.getElementById('authGate').classList.add('hidden');
}

function relativeAgeSeconds(seconds) {
  if (seconds == null) return '时间未知';
  if (seconds < 60) return '刚刚';
  if (seconds < 3600) return Math.floor(seconds / 60) + '分钟前';
  if (seconds < 86400) return Math.floor(seconds / 3600) + '小时前';
  return Math.floor(seconds / 86400) + '天前';
}

function renderDataTrust(meta) {
  if (!meta) return;
  const bar = document.getElementById('dataTrustBar');
  bar.className = 'data-trust-bar ' + (meta.status || 'degraded');
  const labels = { fresh: '数据已就绪', stale: '正在显示缓存', degraded: '数据源降级', partial: '部分数据可用' };
  const source = (meta.source || []).join(' + ');
  const marketDate = meta.market_data_date ? '市场日期 ' + meta.market_data_date : '';
  document.getElementById('dataTrustText').textContent = [labels[meta.status] || '数据状态未知', marketDate, source].filter(Boolean).join(' · ');
  document.getElementById('dataTrustAge').textContent = relativeAgeSeconds(meta.age_seconds);
}

document.getElementById('authForm').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.getElementById('authSubmit');
  const error = document.getElementById('authError');
  button.disabled = true; button.textContent = '验证中'; error.textContent = '';
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: document.getElementById('accessCode').value }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '验证码不正确');
    document.getElementById('accessCode').value = '';
    hideAuthGate();
    await init();
  } catch (reason) {
    error.textContent = reason.message;
  } finally {
    button.disabled = false; button.textContent = '进入';
  }
});

function isMarketOpen() {
  const now = new Date();
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  const hhmm = now.getHours() * 100 + now.getMinutes();
  return hhmm >= 915 && hhmm <= 1505;
}

// 判断缓存是否足够新（休盘期间 cron 数据可直接用）
function isCacheFreshEnough(cacheTime) {
  if (!cacheTime) return false;
  const ageMs = Date.now() - cacheTime;
  // 盘中：缓存 5min 内算新鲜
  if (isMarketOpen()) return ageMs < 5 * 60 * 1000;
  // 非交易日（周末）：缓存 48h 内算新鲜（周五 15:30 → 周日晚）
  const day = new Date().getDay();
  if (day === 0 || day === 6) return ageMs < 48 * 60 * 60 * 1000;
  // 工作日休盘：缓存 4h 内算新鲜（覆盖 cron 15:30 到晚间浏览窗口）
  return ageMs < 4 * 60 * 60 * 1000;
}

// 相对时间显示
function relativeTime(ts) {
  if (!ts) return '--';
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
  if (diff < 60) return '刚刚';
  if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
  if (diff < 86400) return Math.floor(diff / 3600) + '小时前';
  return Math.floor(diff / 86400) + '天前';
}

// 判断时间戳是否来自 cron（工作日 15:20-15:50 之间）
function isCronTimestamp(ts) {
  if (!ts) return false;
  const d = new Date(ts);
  const day = d.getDay();
  if (day === 0 || day === 6) return false;
  const hhmm = d.getHours() * 100 + d.getMinutes();
  return hhmm >= 1520 && hhmm <= 1550;
}

async function mcpCall(tool, args = {}, timeoutMs = 60000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    let path, method = 'GET', body;
    if (tool === 'scan_market') {
      path = args.force_refresh ? '/api/dashboard/refresh' : '/api/dashboard/overview';
      method = args.force_refresh ? 'POST' : 'GET';
    } else if (tool === 'analyze_stock') {
      path = `/api/dashboard/stocks/${encodeURIComponent(args.symbol)}`;
    } else if (tool === 'get_regime') {
      path = '/api/dashboard/regime';
    } else if (tool === 'review_signals') {
      path = `/api/dashboard/signals?days=${encodeURIComponent(args.days || 3650)}&limit=5000`;
    } else if (tool === 'update_signal_outcomes') {
      path = '/api/dashboard/backfill'; method = 'POST';
    } else if (tool === 'polish_narrative_llm') {
      path = '/api/dashboard/narrative'; method = 'POST'; body = JSON.stringify({
        template_narrative: args.template_narrative,
        stock_name: args.stock_name,
        score: args.score,
        portfolio_context: args.portfolio_context,
        news_headlines: args.news_headlines,
      });
    } else {
      throw new Error(`不支持的工具: ${tool}`);
    }
    const resp = await fetch(path, {
      method, credentials: 'same-origin', signal: ctrl.signal,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body,
    });
    const data = await resp.json();
    if (resp.status === 401) { showAuthGate(); throw new Error('登录已失效'); }
    if (!resp.ok || data.error) throw new Error(data.error || `请求失败 (${resp.status})`);
    return data;
  } catch(e) {
    if (e.name === 'AbortError') throw new Error('分析超时，请稍后重试');
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

function scoreClass(score) {
  return score > 0 ? 'positive' : score < 0 ? 'negative' : '';
}

function isUSCode(code) { return code && /^[A-Za-z]/.test(code); }
function cur(code) { return isUSCode(code) ? '$' : '¥'; }
function displayName(s) {
  // 美股: ticker 做主标题, 全名过长时截断做副标题
  if (isUSCode(s.code || s.symbol)) return s.code || s.symbol;
  return s.name || s.code || s.symbol;
}
function displaySub(s) {
  if (isUSCode(s.code || s.symbol)) return s.name || '';
  return s.code || '';
}

function signalBadge(signal) {
  if (['看多', '偏多', '强烈看多'].includes(signal)) return `<span class="signal-badge bull">${signal}</span>`;
  if (['看空', '偏空', '强烈看空'].includes(signal)) return `<span class="signal-badge bear">${signal}</span>`;
  return `<span class="signal-badge neutral">${signal}</span>`;
}

function renderSparkline(prices) {
  if (!prices || prices.length < 2) return '<svg class="sparkline" width="60" height="20" viewBox="0 0 60 20"><line x1="0" y1="10" x2="60" y2="10" stroke="var(--text-muted)" stroke-width="1" stroke-dasharray="3,3" opacity="0.4"/></svg>';
  const w = 60, h = 20, pad = 1;
  const min = Math.min(...prices), max = Math.max(...prices);
  const range = max - min || 1;
  const pts = prices.map((p, i) =>
    `${(i / (prices.length - 1)) * w},${h - ((p - min) / range) * (h - pad * 2) - pad}`
  ).join(' ');
  const color = prices[prices.length - 1] >= prices[0] ? 'var(--red)' : 'var(--green)';
  return `<svg class="sparkline" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}

const SCORE_TIP = '评分范围 -100 ~ +100&#10;> +50 强烈看多 | > +20 看多&#10;±20 中性观望&#10;< -20 看空 | < -50 强烈看空';

function renderStockCard(s, showPnl = false, totalValue = 0) {
  const hasConflicts = s.conflicts && s.conflicts.length > 0;
  const isConflict = hasConflicts || (showPnl && s.pnl_pct > 0 && s.score < -10);

  let pnlHtml = '';
  if (showPnl && s.pnl_pct !== undefined) {
    const cls = s.pnl_pct >= 0 ? 'profit' : 'loss';
    const sign = s.pnl_pct >= 0 ? '+' : '';
    pnlHtml = `<span class="pnl ${cls}">${sign}${s.pnl_pct.toFixed(2)}%</span>`;
    if (s.pnl_amount !== undefined) {
      pnlHtml += ` <span class="pnl ${cls}">(${sign}${s.pnl_amount.toFixed(0)}${isUSCode(s.code) ? '美元' : '元'})</span>`;
    }
  }

  let holdingMeta = '';
  if (showPnl && s.cost) {
    const parts = [`成本${cur(s.code)}${s.cost.toFixed(2)}`];
    if (s.shares) parts.push(`${s.shares}股`);
    if (totalValue > 0 && s.price && s.shares) {
      parts.push(`仓位${((s.price * s.shares) / totalValue * 100).toFixed(1)}%`);
    }
    if (s.added_at) {
      const d = new Date(s.added_at);
      parts.push(`${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')}建仓`);
    }
    holdingMeta = `<div class="holding-meta">${parts.join(' · ')}</div>`;
  }

  let contextHtml = '';
  if (s.context) {
    const icon = isConflict ? '⚠️' : '💡';
    contextHtml = `<div class="stock-context${isConflict ? ' conflict-ctx' : ''}">${icon} ${s.context}</div>`;
  }

  const reasons = [];
  if (s.reasons_bull?.length) reasons.push('📈 ' + s.reasons_bull.join('、'));
  if (s.reasons_bear?.length) reasons.push('📉 ' + s.reasons_bear.join('、'));

  return `
    <div class="stock-card${isConflict ? ' conflict' : ''}" data-action="detail" data-code="${s.code}">
      <div class="stock-header">
        <div>
          <div class="stock-name">${displayName(s)}</div>
          <div class="stock-code">${displaySub(s)}</div>
        </div>
        <div style="text-align:right;display:flex;align-items:center;gap:8px;">
          ${renderSparkline(s.sparkline)}
          <div>
            <div class="stock-score ${scoreClass(s.score)}" title="${SCORE_TIP}">${s.score > 0 ? '+' : ''}${s.score}</div>
            ${signalBadge(s.signal)}
          </div>
        </div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:baseline;">
        <div class="stock-price">${cur(s.code)}${s.price?.toFixed(2) || '--'}</div>
        <div class="stock-meta">${pnlHtml}</div>
      </div>
      ${holdingMeta}
      ${contextHtml}
      ${reasons.length ? `<div class="stock-reasons">${reasons.join('<br>')}</div>` : ''}
      ${hasConflicts ? `<div class="stock-conflict-hint">${s.conflicts[0].description}</div>` : ''}
    </div>
  `;
}

function renderGrid(gridId, stocks, showPnl = false, totalValue = 0) {
  const grid = document.getElementById(gridId);
  if (!stocks || stocks.length === 0) {
    grid.innerHTML = '<div class="empty">暂无数据</div>';
    return;
  }
  grid.innerHTML = stocks.map(s => renderStockCard(s, showPnl, totalValue)).join('');
}

let lastScanData = null;

async function loadRegime() {
  try {
    const data = await mcpCall('get_regime');
    const badge = document.getElementById('regimeBadge');
    const r = data.regime || data;
    badge.textContent = `${r.emoji || ''} ${r.description || r.regime || '--'}`;
    badge.className = 'regime-badge';
    const desc = (r.description || r.regime || '');
    if (desc.includes('偏强') || desc.includes('牛')) badge.classList.add('regime-bull');
    else if (desc.includes('偏弱') || desc.includes('熊')) badge.classList.add('regime-bear');
    else if (desc.includes('高波动')) badge.classList.add('regime-volatile');
  } catch(e) {
    console.warn('Regime failed:', e);
  }
}

// ═══════════════════════════════════════════
// Detail Panel — 个股详情面板
// ═══════════════════════════════════════════

let currentDetailCode = null;

function getAllStockCodes() {
  if (!lastScanData) return [];
  const sections = ['holdings', 'watchlist', 'hot_strongest', 'hot_weakest'];
  const codes = [];
  sections.forEach(s => (lastScanData[s] || []).forEach(x => codes.push(x.code)));
  return codes;
}

function isInWatchlist(code) {
  return (lastScanData?.watchlist || []).some(s => s.code === code);
}
function isInHoldings(code) {
  return (lastScanData?.holdings || []).some(s => s.code === code);
}

function renderDetailHead(stock, signal, quick) {
  const name = stock?.name || quick?.name || currentDetailCode;
  const code = stock?.code || quick?.code || currentDetailCode;
  const price = stock?.price ?? quick?.price;
  const pct = stock?.pct_change;
  const score = signal?.adjusted_score ?? quick?.score ?? 0;
  const dir = signal?.direction || quick?.signal || '--';

  let html = `<div class="detail-head">`;
  const _isUS = isUSCode(code);
  html += `<h2>${_isUS ? code : name}</h2><div class="stock-code">${_isUS ? name : code}</div>`;
  html += `<div class="detail-price-row">`;
  html += `<span class="detail-price">${cur(code)}${price?.toFixed(2) || '--'}</span>`;
  if (pct !== undefined && pct !== 0) {
    const cls = pct >= 0 ? 'profit' : 'loss';
    html += `<span class="detail-pct pnl ${cls}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</span>`;
  }
  html += `<span class="stock-score ${scoreClass(score)}" style="font-size:20px;" title="${SCORE_TIP}">${score > 0 ? '+' : ''}${score}</span>`;
  html += signalBadge(dir);
  html += `</div>`; // price-row

  // PnL (if holding)
  if (quick?.pnl_pct !== undefined) {
    const cls = quick.pnl_pct >= 0 ? 'profit' : 'loss';
    const sign = quick.pnl_pct >= 0 ? '+' : '';
    html += `<div class="detail-pnl-row">`;
    html += `<span class="pnl ${cls}">浮盈 ${sign}${quick.pnl_pct.toFixed(2)}%</span>`;
    if (quick.pnl_amount !== undefined) html += `<span class="pnl ${cls}">(${sign}${quick.pnl_amount.toFixed(0)}${isUSCode(code) ? '美元' : '元'})</span>`;
    if (quick.cost) html += `<span style="color:var(--text-muted);">成本${cur(code)}${quick.cost.toFixed(2)}</span>`;
    if (quick.shares) html += `<span style="color:var(--text-muted);">${quick.shares}股</span>`;
    html += `</div>`;
  }

  // Sparkline (enlarged)
  if (quick?.sparkline?.length >= 2) {
    html += `<div class="detail-sparkline-wrap">`;
    html += renderDetailSparkline(quick.sparkline);
    html += `<div class="meta">`;
    const sp = quick.sparkline;
    const spChange = ((sp[sp.length-1] / sp[0] - 1) * 100).toFixed(2);
    html += `7日趋势 <span class="pnl ${parseFloat(spChange) >= 0 ? 'profit' : 'loss'}">${parseFloat(spChange) >= 0 ? '+' : ''}${spChange}%</span><br>`;
    html += `最高 ${cur(code)}${Math.max(...sp).toFixed(2)} · 最低 ${cur(code)}${Math.min(...sp).toFixed(2)}`;
    html += `</div></div>`;
  }

  // Bull/bear reasons from quick
  if (quick?.reasons_bull?.length) html += `<div style="font-size:12px;color:var(--red);margin-top:8px;">📈 ${quick.reasons_bull.join('、')}</div>`;
  if (quick?.reasons_bear?.length) html += `<div style="font-size:12px;color:var(--green);margin-top:3px;">📉 ${quick.reasons_bear.join('、')}</div>`;

  html += `</div>`; // detail-head
  return html;
}

function renderDetailSparkline(prices) {
  const w = 180, h = 50, pad = 2;
  const min = Math.min(...prices), max = Math.max(...prices);
  const range = max - min || 1;
  const pts = prices.map((p, i) =>
    `${(i / (prices.length - 1)) * w},${h - ((p - min) / range) * (h - pad * 2) - pad}`
  ).join(' ');
  const color = prices[prices.length - 1] >= prices[0] ? 'var(--red)' : 'var(--green)';
  // Fill area
  const fillPts = pts + ` ${w},${h} 0,${h}`;
  const fillColor = prices[prices.length - 1] >= prices[0] ? 'rgba(220,38,38,0.06)' : 'rgba(22,163,74,0.06)';
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
    <polygon points="${fillPts}" fill="${fillColor}"/>
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

function renderDimGrid(data) {
  const tech = data.technical || {};
  const mom = tech.momentum || {};
  const vol = tech.volume || {};
  const boll = tech.volatility || {};
  const ma = tech.ma || {};
  const pos = tech.price_position || {};
  const money = data.money_flow || {};
  const regime = data.regime || {};
  const news = data.news || [];

  let html = '<div class="dim-grid">';

  // 1. 技术面
  const techScore = tech.trend?.score || 0;
  let techDetails = '';
  if (mom.rsi_14) techDetails += `<span class="dim-tag ${mom.rsi_14 > 70 ? 'bear' : mom.rsi_14 < 30 ? 'bull' : 'neutral'}">RSI ${mom.rsi_14}</span>`;
  if (mom.macd_cross && mom.macd_cross !== '无') techDetails += `<span class="dim-tag ${mom.macd_cross === '金叉' ? 'bull' : 'bear'}">${mom.macd_cross}</span>`;
  if (ma.bullish_aligned) techDetails += `<span class="dim-tag bull">多头排列</span>`;
  if (ma.bearish_aligned) techDetails += `<span class="dim-tag bear">空头排列</span>`;
  if (boll.boll_position !== undefined) techDetails += `<span class="dim-tag info">BOLL ${boll.boll_position.toFixed(0)}%</span>`;
  if (tech.patterns?.length) techDetails += `<br><span style="font-size:11px;color:var(--text-muted);">${tech.patterns.slice(0,3).join('、')}</span>`;
  // Position info
  let posInfo = '';
  if (pos.pct_5d !== undefined) posInfo += `5日 ${pos.pct_5d >= 0 ? '+' : ''}${pos.pct_5d.toFixed(1)}%`;
  if (pos.pct_20d !== undefined) posInfo += ` · 20日 ${pos.pct_20d >= 0 ? '+' : ''}${pos.pct_20d.toFixed(1)}%`;
  if (posInfo) techDetails += `<div style="margin-top:4px;font-size:11px;color:var(--text-muted);">${posInfo}</div>`;

  html += `<div class="dim-card">
    <div class="dim-card-title">📊 技术面</div>
    <div class="dim-card-score ${scoreClass(techScore)}">${techScore > 0 ? '+' : ''}${techScore}</div>
    <div class="dim-card-detail">${techDetails}</div>
  </div>`;

  // 2. 资金面
  let moneyScore = '';
  let moneyDetails = '';
  if (money.error) {
    moneyDetails = `<span style="color:var(--text-muted);">${money.error}</span>`;
  } else if (money.main_net_inflow !== undefined) {
    const mainNet = money.main_net_inflow;
    const mainPct = money.main_net_inflow_pct;
    moneyScore = `${mainNet >= 0 ? '+' : ''}${(mainNet / 10000).toFixed(1)}万`;
    moneyDetails += `<span class="dim-tag ${mainNet >= 0 ? 'bull' : 'bear'}">主力 ${mainPct >= 0 ? '+' : ''}${mainPct.toFixed(1)}%</span>`;
    if (money.super_large_net) moneyDetails += `<span class="dim-tag ${money.super_large_net >= 0 ? 'bull' : 'bear'}">超大单 ${(money.super_large_net / 10000).toFixed(0)}万</span>`;
  }
  if (vol.volume_ratio) {
    moneyDetails += `<div style="margin-top:4px;font-size:11px;color:var(--text-muted);">量比 ${vol.volume_ratio.toFixed(2)}${vol.shrinking ? ' 📉缩量' : ''}${vol.expanding ? ' 📈放量' : ''}</div>`;
  }
  html += `<div class="dim-card">
    <div class="dim-card-title">💰 资金面</div>
    <div class="dim-card-score" style="font-size:${moneyScore ? 18 : 14}px;color:var(--text-secondary);">${moneyScore || '--'}</div>
    <div class="dim-card-detail">${moneyDetails || '<span style="color:var(--text-muted);">无数据</span>'}</div>
  </div>`;

  // 3. 消息面
  let newsDetails = '';
  if (news.length > 0) {
    newsDetails = news.slice(0, 3).map(n => {
      const title = typeof n === 'string' ? n : (n.title || n.content || '');
      return `<div style="font-size:11px;margin-bottom:3px;color:var(--text-secondary);">${title.length > 40 ? title.slice(0, 40) + '...' : title}</div>`;
    }).join('');
  }
  html += `<div class="dim-card">
    <div class="dim-card-title">📰 消息面</div>
    <div class="dim-card-score" style="font-size:14px;color:var(--text-secondary);">${news.length > 0 ? news.length + '条近期新闻' : '无近期消息'}</div>
    <div class="dim-card-detail">${newsDetails || '<span style="color:var(--text-muted);">暂无</span>'}</div>
  </div>`;

  // 4. 市场体制
  const regimeEmoji = regime.emoji || '🌊';
  const regimeDesc = regime.description || regime.regime || '--';
  const regimeAdj = data.signal?.regime_adjustment || 0;
  html += `<div class="dim-card">
    <div class="dim-card-title">🌐 市场体制</div>
    <div class="dim-card-score" style="font-size:16px;">${regimeEmoji} ${regimeDesc}</div>
    <div class="dim-card-detail">
      ${regimeAdj !== 0 ? `<span class="dim-tag ${regimeAdj > 0 ? 'bull' : 'bear'}">体制调整 ${regimeAdj > 0 ? '+' : ''}${regimeAdj}</span>` : ''}
      ${data.advice?.position_max ? `<div style="margin-top:4px;font-size:11px;color:var(--text-muted);">建议仓位 ≤ ${data.advice.position_max}</div>` : ''}
    </div>
  </div>`;

  html += '</div>'; // dim-grid
  return html;
}

function renderConflicts(conflicts, guardrails) {
  if (!conflicts?.length && !guardrails?.length) return '';
  let html = '<div class="detail-conflicts">';
  if (conflicts?.length) {
    conflicts.forEach(c => {
      const isSevere = (c.type || '').includes('资金') || (c.description || '').includes('出货');
      html += `<div class="conflict-alert${isSevere ? ' severe' : ''}">
        <div class="conflict-title">⚠️ ${c.description}</div>
        ${c.advice ? `<div class="conflict-advice">${c.advice}</div>` : ''}
      </div>`;
    });
  }
  if (guardrails?.length) {
    guardrails.forEach(g => {
      html += `<div class="guardrail-alert">🛡️ ${g.message} — ${g.advice}</div>`;
    });
  }
  html += '</div>';
  return html;
}

function renderNarrative(narrative) {
  if (!narrative) return '';
  let formatted = narrative
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^##\s+(.+)$/gm, '<div style="font-weight:600;color:var(--text);margin-top:8px;">$1</div>');
  return `<div class="detail-narrative">${formatted}</div>`;
}

function narrativeLoading() {
  return `<div class="narrative-loading" id="narrativeLoading"><span class="ld-icon">🔍</span>AI 深度分析中...</div>`;
}

function renderDetailBody(data, quick, narrativeHtml) {
  let left = '';
  if (data.meta?.status === 'partial' && data.meta.warnings?.length) {
    left += `<div class="detail-advice"><span>ℹ️ ${data.meta.warnings[0]}</span></div>`;
  }
  left += renderDimGrid(data);
  left += renderConflicts(data.conflicts, data.guardrails);
  if (data.advice) {
    left += `<div class="detail-advice">`;
    if (data.advice.position_max) left += `<span>📏 建议仓位 ≤ ${data.advice.position_max}</span>`;
    if (data.advice.stop_loss_hint) left += `<span>🛑 ${data.advice.stop_loss_hint}</span>`;
    left += `</div>`;
  }

  let right = '<div class="detail-right-title">🤖 AI 深度分析</div>';
  right += narrativeHtml;

  return `<div class="detail-body"><div class="detail-left">${left}</div><div class="detail-right">${right}</div></div>`;
}

function renderDetailActions(code) {
  return '';
}

function narrativeSkeleton() {
  return `<div class="narrative-skeleton">
    <div class="skeleton-line w80 h24"></div>
    <div class="skeleton-line w60"></div>
    <div class="skeleton-line w80"></div>
    <div class="skeleton-line w40"></div>
  </div>`;
}

function dimGridSkeleton() {
  const card = `<div class="dim-card"><div class="skeleton-line w40 h24"></div><div class="skeleton-line w60"></div><div class="skeleton-line w80"></div></div>`;
  return `<div class="dim-grid">${card}${card}${card}${card}</div>`;
}

async function showDetail(code) {
  const thisRequest = ++detailRequestId;  // 每次点击递增，旧请求自动失效
  currentDetailCode = code;
  const overlay = document.getElementById('detailOverlay');
  const content = document.getElementById('detailContent');
  overlay.classList.add('show');

  // Phase 1: 从 scan 缓存立即显示 (0ms)
  const cached = lastScanData;
  let quick = null;
  if (cached) {
    const all = [...(cached.holdings||[]), ...(cached.watchlist||[]), ...(cached.hot_strongest||[]), ...(cached.hot_weakest||[])];
    quick = all.find(s => s.code === code);
  }

  // 休盘期间用缓存（仅当缓存数据有效时）
  const dc = detailCache[code];
  if (dc && !isMarketOpen() && dc.data && dc.data.signal && dc.data.signal.adjusted_score != null) {
    let html = renderDetailHead(dc.data.stock, dc.data.signal, quick);
    const narHtml = dc.narrative ? renderNarrative(dc.narrative) : renderNarrative(dc.data.narrative);
    html += renderDetailBody(dc.data, quick, narHtml);
    content.innerHTML = html;
    return;
  }

  let phase1 = renderDetailHead(null, null, quick);
  phase1 += `<div class="detail-body"><div class="detail-left">${dimGridSkeleton()}</div><div class="detail-right"><div class="detail-right-title">🤖 AI 深度分析</div>${narrativeSkeleton()}</div></div>`;
  content.innerHTML = phase1;

  // Phase 2: analyze_stock(skip_llm=true) → 跳过 LLM 秒出结果 (~1-2s)
  try {
    const data = await mcpCall('analyze_stock', { symbol: code, skip_llm: true });

    // 检查用户是否已切换到其他股票
    if (thisRequest !== detailRequestId) return;

    let html = renderDetailHead(data.stock, data.signal, quick);
    html += renderDetailBody(data, quick, narrativeLoading());
    content.innerHTML = html;

    // 缓存 analyze_stock 结果（仅当数据有效时，防止 baostock 故障返回的残缺报告被缓存）
    if (data && data.signal && data.signal.adjusted_score != null) {
      detailCache[code] = { data, narrative: null, time: Date.now() };
    }

    // Phase 3: 后台异步 LLM 润色叙事 (不阻塞 UI)
    polishNarrativeAsync(code, data.narrative, data.stock?.name || '', data.signal?.adjusted_score || 0, data.portfolio_context || '', data.news || []);

  } catch(e) {
    if (thisRequest !== detailRequestId) return;
    content.innerHTML = renderDetailHead(null, null, quick) +
      `<div class="empty">深度分析失败: ${e.message}<br><button data-action="retry-detail" data-code="${code}" style="margin-top:8px;padding:4px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg-base);cursor:pointer;">重试</button></div>`;
  }
}

// Phase 3: 异步 LLM 深度分析
async function polishNarrativeAsync(code, templateNarrative, stockName, score, portfolioContext, newsData) {
  try {
    // 新闻标题拼接为换行分隔字符串
    const newsHeadlines = (newsData || []).map(n => n.title).filter(Boolean).join('\n');
    const result = await mcpCall('polish_narrative_llm', {
      template_narrative: templateNarrative,
      stock_name: stockName,
      score: score,
      portfolio_context: portfolioContext || '',
      news_headlines: newsHeadlines
    });
    if (currentDetailCode !== code) return;
    const placeholder = document.getElementById('narrativeLoading');
    if (!placeholder) return;
    const final = result.narrative || templateNarrative;
    // 缓存 LLM 叙事
    if (detailCache[code]) detailCache[code].narrative = final;
    const narHtml = renderNarrative(final);
    placeholder.outerHTML = narHtml;
  } catch(e) {
    // LLM 失败 → 显示模板叙事
    if (currentDetailCode !== code) return;
    const placeholder = document.getElementById('narrativeLoading');
    if (placeholder) placeholder.outerHTML = renderNarrative(templateNarrative);
    console.debug('LLM analysis fallback:', e.message);
  }
}

function closeDetail() {
  currentDetailCode = null;
  document.getElementById('detailOverlay').classList.remove('show');
}

function renderSkeletons() {
  const skeleton = `<div class="skeleton-card"><div class="skeleton-line w60 h24"></div><div class="skeleton-line w40"></div><div class="skeleton-line w80"></div><div class="skeleton-line w60"></div></div>`;
  ['holdingsGrid', 'strongGrid', 'weakGrid'].forEach(id => {
    const el = document.getElementById(id);
    if (el && !el.children.length) el.innerHTML = skeleton.repeat(3);
  });
}

function saveToCache(data) {
  try { localStorage.setItem('tidewatch_scan', JSON.stringify({ data, time: Date.now() })); } catch(e) {}
}

function saveReviewToCache(data) {
  try { localStorage.setItem('tidewatch_review_v2', JSON.stringify({ data, days: reviewDays, time: Date.now() })); } catch(e) {}
}

function loadReviewFromCache() {
  try {
    const raw = localStorage.getItem('tidewatch_review_v2');
    if (!raw) return null;
    const { data, days, time } = JSON.parse(raw);
    if (days !== reviewDays) return null;
    const day = new Date().getDay();
    const maxAge = (day === 0 || day === 6) ? 48 * 60 * 60 * 1000 : 24 * 60 * 60 * 1000;
    if (Date.now() - time > maxAge) return null;
    return { data, time };
  } catch(e) { return null; }
}

function loadFromCache() {
  try {
    const raw = localStorage.getItem('tidewatch_scan');
    if (!raw) return null;
    const { data, time } = JSON.parse(raw);
    // 周末给 48h（配合 isCacheFreshEnough 的周末策略）
    const day = new Date().getDay();
    const maxAge = (day === 0 || day === 6) ? 48 * 60 * 60 * 1000 : 24 * 60 * 60 * 1000;
    if (Date.now() - time > maxAge) return null;
    return data;
  } catch(e) { return null; }
}

function renderScanData(data, fromCache = false) {
  lastScanData = data;
  renderDataTrust(data.meta);
  const gridIds = ['holdingsGrid', 'watchlistGrid', 'strongGrid', 'weakGrid'];

  // 检测是否在替换已有内容（缓存→真实），需要 fade 过渡
  const hasExisting = !fromCache && gridIds.some(id => {
    const el = document.getElementById(id);
    return el && el.children.length && !el.querySelector('.skeleton-card');
  });

  const doRender = () => {
    document.getElementById('totalPnlLabel').textContent = '持仓总浮盈';
    document.getElementById('totalPnl').textContent = '--';
    document.getElementById('totalPnl').className = 'stat-value';
    document.getElementById('totalValue').textContent = '--';
    document.getElementById('availCash').textContent = '--';
    document.getElementById('watchlistSection').style.display = 'none';
    document.getElementById('watchlistGrid').innerHTML = '';
    document.getElementById('watchlistCount').textContent = '';
    let portfolioValue = 0;
    if (data.holdings?.length) data.holdings.forEach(h => { if (h.price && h.shares) portfolioValue += h.price * h.shares; });
    renderGrid('holdingsGrid', data.holdings, true, portfolioValue);
    document.getElementById('holdingsCount').textContent = `(${data.holdings?.length || 0})${fromCache ? ' 缓存' : ''}`;

    if (data.watchlist?.length > 0) {
      document.getElementById('watchlistSection').style.display = '';
      renderGrid('watchlistGrid', data.watchlist);
      document.getElementById('watchlistCount').textContent = `(${data.watchlist.length})`;
    }

    renderGrid('strongGrid', data.hot_strongest);
    renderGrid('weakGrid', data.hot_weakest);
    document.getElementById('strongCount').textContent = `(${data.hot_strongest?.length || 0})`;
    document.getElementById('weakCount').textContent = `(${data.hot_weakest?.length || 0})`;

    const ps = data.pool_size || {};
    document.getElementById('poolSize').textContent = `${ps.scanned || 0} / ${ps.total || 0}`;
    // 智能时间显示：相对时间 + cron 标记
    const lastScanEl = document.getElementById('lastScan');
    if (data.timestamp) {
      const rel = relativeTime(data.timestamp);
      const isCron = isCronTimestamp(data.timestamp);
      const timeStr = new Date(data.timestamp).toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
      let label = rel + ' · ' + timeStr;
      if (fromCache) label += ' (缓存)';
      lastScanEl.innerHTML = label + (isCron ? ' <span class="cron-badge"><span class="cron-dot"></span>定时</span>' : '');
    } else {
      lastScanEl.textContent = '--';
    }
    document.getElementById('totalPnl').title = '基于日K线收盘价，非盘中实时';

    if (data.holdings?.length) {
      let totalPnl = 0, totalValue = 0;
      const hasUS = data.holdings.some(h => isUSCode(h.code));
      const hasA = data.holdings.some(h => !isUSCode(h.code));
      data.holdings.forEach(h => {
        if (h.pnl_amount !== undefined) totalPnl += h.pnl_amount;
        if (h.price && h.shares && !isNaN(h.price * h.shares)) totalValue += h.price * h.shares;
      });
      const pnlEl = document.getElementById('totalPnl');
      pnlEl.textContent = `${totalPnl >= 0 ? '+' : '-'}${Math.abs(totalPnl).toFixed(2)}`;
      pnlEl.className = `stat-value ${totalPnl >= 0 ? 'positive' : 'negative'}`;
      document.getElementById('totalValue').textContent = totalValue > 0 ? totalValue.toFixed(2) : '--';
      // 混合币种提示
      const label = document.getElementById('totalPnlLabel');
      if (hasUS && hasA) label.textContent = '持仓总浮盈（混合币种）';
      else if (hasUS) label.textContent = '持仓总浮盈（$）';
      else label.textContent = '持仓总浮盈（¥）';
    }

    // 可用资金（从账户信息取）
    const acct = data.account || {};
    if (acct.cash > 0) {
      document.getElementById('availCash').textContent = acct.cash.toFixed(2);
    }
  };

  if (hasExisting) {
    // 缓存→真实：先淡出 → 替换内容 → 淡入
    gridIds.forEach(id => document.getElementById(id)?.classList.add('fade-out'));
    setTimeout(() => {
      doRender();
      gridIds.forEach(id => document.getElementById(id)?.classList.remove('fade-out'));
    }, 150);
  } else {
    doRender();
  }
}

async function refreshAll() {
  const btn = document.getElementById('refreshBtn');
  const bar = document.getElementById('progressBar');
  const main = document.querySelector('.main');
  btn.classList.add('loading');
  bar.classList.add('active');
  main.classList.add('refreshing');
  try {
    const [scanData] = await Promise.all([
      mcpCall('scan_market', { top_n: 5, force_refresh: true }),
      loadRegime(),
    ]);
    renderScanData(scanData);
    saveToCache(scanData);
    showToast('✅ 数据已更新', 2000, 'success');
  } catch(e) {
    console.error('Refresh failed:', e);
    showToast('⚠️ 刷新失败，请稍后重试');
  } finally {
    btn.classList.remove('loading');
    bar.classList.remove('active');
    main.classList.remove('refreshing');
  }
}

// ═══════════════════════════════════════════
// Tab Navigation + Signal Review
// ═══════════════════════════════════════════

let currentTab = 'live';
let reviewData = null;
let reviewFilter = 'all';
let reviewDays = 3650;

function switchTab(tab) {
  if (tab === currentTab) return;
  currentTab = tab;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.tab-btn[data-tab="${tab}"]`).classList.add('active');
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.getElementById(tab === 'live' ? 'livePanel' : 'reviewPanel').classList.add('active');
  if (tab === 'review') {
    if (reviewData) {
      // 预加载已完成，直接渲染（无需再等）
      renderReviewStats(reviewData);
      renderSignalTimeline(reviewData.signals, reviewFilter);
    } else {
      loadSignalReview();
    }
  }
}

function refreshCurrent() {
  if (currentTab === 'live') refreshAll();
  else if (currentTab === 'review') loadSignalReview(true);  // 手动刷新强制拉取
}

function parseOutcome(str) {
  if (!str) return null;
  const match = str.match(/([+-]?\d+\.?\d*)%\s*\((\w+)\)/);
  if (!match) return null;
  return { pct: parseFloat(match[1]), outcome: match[2] };
}

function dedupeSignals(signals) {
  const byDateSymbol = {};
  signals.forEach(signal => {
    const key = signal.date + '|' + signal.symbol;
    const existing = byDateSymbol[key];
    if (!existing || Number(signal.id) > Number(existing.id)) byDateSymbol[key] = signal;
  });
  return Object.values(byDateSymbol);
}

async function loadSignalReview(forceRefresh = false) {
  const timeline = document.getElementById('signalTimeline');

  // 尝试用 localStorage 缓存（休盘 + 缓存新鲜 → 跳过请求）
  if (!forceRefresh) {
    const cached = loadReviewFromCache();
    if (cached && isCacheFreshEnough(cached.time)) {
      reviewData = cached.data;
      renderReviewStats(reviewData);
      renderSignalTimeline(reviewData.signals, reviewFilter);
      return;
    }
  }

  timeline.innerHTML = '<div class="empty" style="padding:40px;">加载信号数据中...</div>';
  try {
    reviewData = await mcpCall('review_signals', { days: reviewDays });
    saveReviewToCache(reviewData);
    renderReviewStats(reviewData);
    renderSignalTimeline(reviewData.signals, reviewFilter);
  } catch(e) {
    // 请求失败但有缓存 → 用缓存兜底
    const cached = loadReviewFromCache();
    if (cached) {
      reviewData = cached.data;
      renderReviewStats(reviewData);
      renderSignalTimeline(reviewData.signals, reviewFilter);
      showToast('⚠️ 信号数据加载失败，显示缓存');
    } else {
      timeline.innerHTML = `<div class="empty">加载失败: ${e.message}<br><button data-action="retry-signals" style="margin-top:8px;padding:4px 12px;border:1px solid var(--border);border-radius:6px;background:var(--bg-base);cursor:pointer;">重试</button></div>`;
    }
  }
}

function renderReviewStats(data) {
  const signals = data.signals;

  // Deduplicate for consistent counts: same date+symbol → keep latest
  const deduped = dedupeSignals(signals);

  // 5d win rate
  const filled5 = deduped.map(s => parseOutcome(s['5d'])).filter(Boolean);
  const directional5 = filled5.filter(outcome => ['correct', 'wrong'].includes(outcome.outcome));
  const correct5 = directional5.filter(outcome => outcome.outcome === 'correct').length;
  const winRate5 = directional5.length ? correct5 / directional5.length * 100 : null;
  const wr5El = document.getElementById('rvWinRate5d');
  if (winRate5 !== null) {
    wr5El.textContent = winRate5.toFixed(1) + '%';
    wr5El.className = 'stat-value ' + (winRate5 > 60 ? 'win-high' : winRate5 > 40 ? 'win-mid' : 'win-low');
  } else {
    wr5El.textContent = '--';
    wr5El.className = 'stat-value';
  }

  // Bull/Bear win rates
  let bullTotal = 0, bullCorrect = 0, bearTotal = 0, bearCorrect = 0;
  let correctReturns = [], wrongReturns = [];
  let correctCount = 0, wrongCount = 0, abstainCount = 0, pendingCount = 0;

  deduped.forEach(s => {
    const p = parseOutcome(s['5d']);
    if (!p) { pendingCount++; return; }
    if (p.outcome === 'abstain') { abstainCount++; return; }
    const isBull = s.direction.includes('多');
    const isBear = s.direction.includes('空');
    if (isBull) { bullTotal++; if (p.outcome === 'correct') bullCorrect++; }
    if (isBear) { bearTotal++; if (p.outcome === 'correct') bearCorrect++; }
    // Aligned return: positive = signal direction was profitable
    const aligned = isBull ? p.pct : -p.pct;
    if (p.outcome === 'correct') { correctReturns.push(Math.abs(p.pct)); correctCount++; }
    else if (p.outcome === 'wrong') { wrongReturns.push(Math.abs(p.pct)); wrongCount++; }
  });

  const bullEl = document.getElementById('rvBullWin');
  if (bullTotal <= 2) {
    bullEl.textContent = bullTotal > 0 ? bullCorrect + '/' + bullTotal + ' 样本不足' : '--';
    bullEl.className = 'stat-value'; bullEl.style.color = 'var(--text-muted)';
  } else {
    const bwr = (bullCorrect / bullTotal * 100).toFixed(0);
    bullEl.textContent = bwr + '% (' + bullCorrect + '/' + bullTotal + ')';
    bullEl.className = 'stat-value ' + (bwr > 60 ? 'win-high' : bwr > 40 ? 'win-mid' : 'win-low');
    bullEl.style.color = '';
  }
  const bearEl = document.getElementById('rvBearWin');
  if (bearTotal <= 2) {
    bearEl.textContent = bearTotal > 0 ? bearCorrect + '/' + bearTotal + ' 样本不足' : '--';
    bearEl.className = 'stat-value'; bearEl.style.color = 'var(--text-muted)';
  } else {
    const bewr = (bearCorrect / bearTotal * 100).toFixed(0);
    bearEl.textContent = bewr + '% (' + bearCorrect + '/' + bearTotal + ')';
    bearEl.className = 'stat-value ' + (bewr > 60 ? 'win-high' : bewr > 40 ? 'win-mid' : 'win-low');
    bearEl.style.color = '';
  }

  // Average return magnitude
  const avgC = correctReturns.length > 0 ? (correctReturns.reduce((a,b) => a+b, 0) / correctReturns.length).toFixed(1) : '--';
  const avgW = wrongReturns.length > 0 ? (wrongReturns.reduce((a,b) => a+b, 0) / wrongReturns.length).toFixed(1) : '--';
  document.getElementById('rvAvgReturn').innerHTML =
    '<span style="color:var(--blue)">✅ ' + avgC + '%</span> <span style="color:var(--text-muted)">/</span> <span style="color:var(--gold)">❌ ' + avgW + '%</span>';

  // Filled count
  document.getElementById('rvFilled').textContent = filled5.length + ' / ' + deduped.length;

  // Filter counts (deduped)
  document.getElementById('rvCountAll').textContent = '(' + deduped.length + ')';
  document.getElementById('rvCountCorrect').textContent = '(' + correctCount + ')';
  document.getElementById('rvCountWrong').textContent = '(' + wrongCount + ')';
  document.getElementById('rvCountAbstain').textContent = '(' + abstainCount + ')';
  document.getElementById('rvCountPending').textContent = '(' + pendingCount + ')';
}

function renderSignalTimeline(signals, filter) {
  const timeline = document.getElementById('signalTimeline');

  // 与统计口径一致：同一天同一股票只保留最后一次判断。
  const deduped = dedupeSignals(signals);

  let filtered = deduped;
  if (filter === 'correct') filtered = deduped.filter(s => { const p = parseOutcome(s['5d']); return p && p.outcome === 'correct'; });
  else if (filter === 'wrong') filtered = deduped.filter(s => { const p = parseOutcome(s['5d']); return p && p.outcome === 'wrong'; });
  else if (filter === 'abstain') filtered = deduped.filter(s => { const p = parseOutcome(s['5d']); return p && p.outcome === 'abstain'; });
  else if (filter === 'pending') filtered = deduped.filter(s => !s['5d']);

  if (filtered.length === 0) {
    timeline.innerHTML = '<div class="empty">暂无匹配的信号</div>';
    return;
  }

  // Group by date
  const groups = {};
  filtered.forEach(s => {
    if (!groups[s.date]) groups[s.date] = [];
    groups[s.date].push(s);
  });

  let html = '';
  Object.keys(groups).sort().reverse().forEach(date => {
    const items = groups[date];
    html += '<div class="date-group">';
    html += '<div class="date-group-header">' + date + ' <span class="date-group-count">(' + items.length + '条信号)</span></div>';
    html += '<div class="signal-grid">';
    items.forEach(s => {
      const p5 = parseOutcome(s['5d']);
      const p10 = parseOutcome(s['10d']);
      const p20 = parseOutcome(s['20d']);
      const outcome = p5 ? p5.outcome : 'pending';

      html += '<div class="signal-review-card ' + outcome + '">';
      // Row 1: Name + Code | Signal badge + Score (color = direction)
      html += '<div class="signal-head">';
      html += '<div><span class="signal-name">' + displayName({code: s.symbol, name: s.name, symbol: s.symbol}) + '</span><span class="signal-code-sm">' + displaySub({code: s.symbol, name: s.name, symbol: s.symbol}) + (s.time ? ' · ' + s.time : '') + '</span></div>';
      html += '<div class="signal-score-area">';
      if (s.direction) html += signalBadge(s.direction);
      html += '<span class="signal-review-score ' + scoreClass(s.score) + '">' + (s.score > 0 ? '+' : '') + s.score + '</span>';
      html += '</div></div>';

      // Row 2: Price | Outcome badge
      html += '<div class="signal-price-row">';
      html += '<span class="signal-entry-price">' + cur(s.symbol) + (s.price ? s.price.toFixed(2) : '--') + '</span>';
      if (outcome === 'correct') html += '<span class="outcome-badge correct">✅ 正确</span>';
      else if (outcome === 'wrong') html += '<span class="outcome-badge wrong">❌ 错误</span>';
      else if (outcome === 'abstain') html += '<span class="outcome-badge abstain">👁 观望</span>';
      else html += '<span class="outcome-badge pending">⏳ 待验证</span>';
      html += '</div>';

      // Row 3: Outcomes (only show when at least one is filled)
      if (p5 || p10 || p20) {
        html += '<div class="signal-outcomes">';
        if (p5) {
          const cls = p5.pct >= 0 ? 'up' : 'down';
          html += '<span>5日 <span class="filled ' + cls + '">' + (p5.pct >= 0 ? '+' : '') + p5.pct.toFixed(1) + '%</span></span>';
        }
        if (p10) {
          const cls = p10.pct >= 0 ? 'up' : 'down';
          html += '<span>10日 <span class="filled ' + cls + '">' + (p10.pct >= 0 ? '+' : '') + p10.pct.toFixed(1) + '%</span></span>';
        }
        if (p20) {
          const cls = p20.pct >= 0 ? 'up' : 'down';
          html += '<span>20日 <span class="filled ' + cls + '">' + (p20.pct >= 0 ? '+' : '') + p20.pct.toFixed(1) + '%</span></span>';
        }
        html += '</div>';
      }

      html += '</div>';
    });
    html += '</div></div>';
  });

  timeline.innerHTML = html;
}

function setReviewFilter(filter) {
  reviewFilter = filter;
  document.querySelectorAll('.review-filter-btn').forEach(b => b.classList.remove('active'));
  document.querySelector('.review-filter-btn[data-filter="' + filter + '"]').classList.add('active');
  if (reviewData) renderSignalTimeline(reviewData.signals, filter);
}

function setReviewRange(days) {
  if (days === reviewDays) return;
  reviewDays = days;
  reviewData = null;
  document.querySelectorAll('.review-range-btn').forEach(button => {
    button.classList.toggle('active', Number(button.dataset.days) === days);
  });
  loadSignalReview(true);
}

async function runBackfill() {
  const btn = document.getElementById('backfillBtn');
  btn.disabled = true;
  btn.textContent = '回填中...';
  try {
    const result = await mcpCall('update_signal_outcomes', {}, 180000);  // 3min timeout（回填需逐条拉K线，周末baostock可能慢）
    const u = result.updated;
    showToast('回填完成: 5日=' + u['5d'] + '条, 10日=' + u['10d'] + '条, 20日=' + u['20d'] + '条', 3000, 'success');
    loadSignalReview(true);  // 回填后强制刷新
  } catch(e) {
    showToast('回填失败: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 回填信号';
  }
}

async function init() {
  // Phase 0: 立刻隐藏 loading，显示骨架屏 + 缓存数据
  const cached = loadFromCache();
  const cacheEntry = (() => { try { const r = localStorage.getItem('tidewatch_scan'); return r ? JSON.parse(r) : null; } catch(e) { return null; } })();
  const cacheAge = cacheEntry?.time || 0;
  if (cached) {
    document.getElementById('loading').classList.add('hidden');
    renderScanData(cached, true);
  } else {
    document.getElementById('loading').classList.add('hidden');
    renderSkeletons();
  }

  // Phase 1: regime 先亮（快，~2s）
  loadRegime();

  // Phase 2: localStorage 只负责秒开；服务端 overview 始终拉取并给出可信状态。
  try {
    const scanData = await mcpCall('scan_market', { top_n: 5 });
    renderScanData(scanData);
    saveToCache(scanData);
  } catch(e) {
    if (cached) {
      showToast('⚠️ 实时数据加载失败，显示缓存');
    } else {
      document.getElementById('holdingsGrid').innerHTML = `<div class="empty">加载失败: ${e.message}<br><button data-action="reload" style="margin-top:12px;padding:6px 16px;border:1px solid var(--border);border-radius:6px;background:var(--bg-base);cursor:pointer;">重试</button></div>`;
    }
  }

  // Phase 3: 后台预加载信号复盘数据（优先 localStorage 缓存，否则静默拉取）
  setTimeout(() => {
    const cachedReview = loadReviewFromCache();
    if (!reviewData && cachedReview && isCacheFreshEnough(cachedReview.time)) {
      reviewData = cachedReview.data;
    }

    // stale-while-revalidate：缓存只负责秒显，每次启动仍静默校验服务端最新数据。
    mcpCall('review_signals', { days: reviewDays }).then(data => {
      reviewData = data;
      saveReviewToCache(data);
      if (currentTab === 'review') {
        renderReviewStats(data);
        renderSignalTimeline(data.signals, reviewFilter);
      }
    }).catch(() => {});
  }, 3000);
}

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeDetail();
  if (e.key === 'r' && !e.ctrlKey && !e.metaKey && document.activeElement.tagName !== 'INPUT') refreshAll();
  // Arrow keys: navigate stocks in detail view
  if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && currentDetailCode) {
    const codes = getAllStockCodes();
    const idx = codes.indexOf(currentDetailCode);
    if (idx === -1) return;
    const next = e.key === 'ArrowRight' ? (idx + 1) % codes.length : (idx - 1 + codes.length) % codes.length;
    closeDetail();
    setTimeout(() => showDetail(codes[next]), 80);
  }
});

// 智能自动刷新：仅盘中 + 可见标签 + 无详情面板（休盘依赖 cron 数据）
setInterval(() => {
  if (!isMarketOpen()) return;  // 休盘不刷新，cron 数据已足够
  if (document.visibilityState !== 'visible') return;
  if (currentDetailCode) return;
  if (currentTab !== 'live') return;
  refreshAll();
}, 5 * 60 * 1000);

document.querySelectorAll('.tab-btn').forEach(button => {
  button.addEventListener('click', () => switchTab(button.dataset.tab));
});
document.getElementById('refreshBtn').addEventListener('click', refreshCurrent);
document.querySelectorAll('.review-filter-btn').forEach(button => {
  button.addEventListener('click', () => setReviewFilter(button.dataset.filter));
});
document.querySelectorAll('.review-range-btn').forEach(button => {
  button.addEventListener('click', () => setReviewRange(Number(button.dataset.days)));
});
document.getElementById('backfillBtn').addEventListener('click', runBackfill);
document.getElementById('detailClose').addEventListener('click', closeDetail);
document.getElementById('detailOverlay').addEventListener('click', event => {
  if (event.target === event.currentTarget) closeDetail();
});
document.addEventListener('click', event => {
  const target = event.target.closest('[data-action]');
  if (!target) return;
  const action = target.dataset.action;
  if (action === 'detail') showDetail(target.dataset.code);
  else if (action === 'retry-detail') { closeDetail(); setTimeout(() => showDetail(target.dataset.code), 100); }
  else if (action === 'retry-signals') loadSignalReview(true);
  else if (action === 'reload') location.reload();
});

async function bootstrap() {
  try {
    const response = await fetch('/api/auth/session', { credentials: 'same-origin' });
    const session = await response.json();
    if (!session.authenticated) throw new Error('not_authenticated');
    hideAuthGate();
    await init();
  } catch {
    document.getElementById('loading').classList.add('hidden');
    showAuthGate();
  }
}

bootstrap();
