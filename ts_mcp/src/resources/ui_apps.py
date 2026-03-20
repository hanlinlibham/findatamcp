"""
MCP Apps UI 资源模块 (AG Grid / AG Charts Enterprise)

注册 ui:// 协议资源，为工具返回提供交互式可视化：
- ui://tushare/kline-chart: K线图（AG Charts candlestick + volume 联动）
- ui://tushare/moneyflow-chart: 资金流向（堆叠柱状 + 净额折线）
- ui://tushare/market-dashboard: 市场仪表板（AG Grid + AG Charts 联动）

设计系统：dpagt v6 暖灰色调 + A股红涨绿跌
图表引擎：AG Grid Enterprise 34.x + AG Charts Enterprise
协议版本：2025-06-18 (MCP Apps SEP-1865)
"""

import logging
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ─── AG Grid License ───
AG_LICENSE = "AgGridLicense66fwc79n[NORMAL][v0102]_NDA3MDk2NjQwMDAwMA==80908dd5fb71b58d3ce28b2ed320216d"

# ─── CDN ───
AG_GRID_CDN = "https://cdn.jsdelivr.net/npm/ag-grid-enterprise@34.1.0/dist/ag-grid-enterprise.min.js"
AG_CHARTS_CDN = "https://cdn.jsdelivr.net/npm/ag-charts-enterprise@11.1.0/dist/ag-charts-enterprise.min.js"

# ─── 共享：dpagt v6 设计系统 CSS 变量 + MCP Apps 协议握手 ───
SHARED_HEAD = f"""\
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root {{
  /* dpagt v6 Light */
  --bg: hsl(40 27% 96%);
  --bg-card: hsl(0 0% 100%);
  --bg-elevated: hsl(40 25% 95%);
  --bg-muted: hsl(40 24% 92%);
  --fg: hsl(220 25% 15%);
  --fg-muted: hsl(220 12% 39%);
  --primary: hsl(212 53% 28%);
  --border: hsl(35 22% 78%);
  /* A股：红涨绿跌 */
  --up: hsl(0 67% 46%);
  --up-bg: hsl(0 70% 96%);
  --down: hsl(150 66% 30%);
  --down-bg: hsl(120 27% 94%);
  --warn: hsl(35 88% 42%);
  /* chart palette */
  --c1: hsl(212 53% 36%);   /* 深海蓝 */
  --c2: hsl(258 40% 50%);   /* 紫 */
  --c3: hsl(162 27% 58%);   /* 薄荷 */
  --c4: hsl(35 88% 52%);    /* 橙 */
  --c5: hsl(185 26% 35%);   /* 青 */
  /* fonts */
  --font-body: 'PingFang SC', 'Noto Sans SC', 'Heiti SC', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', 'JetBrains Mono', 'SF Mono', monospace;
  --radius: 6px;
}}
html[data-theme="oled"], .dark {{
  --bg: hsl(220 27% 8%);
  --bg-card: hsl(220 20% 12%);
  --bg-elevated: hsl(220 20% 14%);
  --bg-muted: hsl(220 16% 18%);
  --fg: hsl(39 35% 92%);
  --fg-muted: hsl(38 14% 67%);
  --primary: hsl(199 91% 64%);
  --border: hsl(220 16% 28%);
  --up: hsl(0 72% 56%);
  --up-bg: hsl(0 40% 16%);
  --down: hsl(150 60% 42%);
  --down-bg: hsl(150 30% 14%);
}}
* {{ margin: 0; box-sizing: border-box; }}
body {{
  font-family: var(--font-body);
  color: var(--fg);
  background: var(--bg);
  padding: 12px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}}
.header {{ margin-bottom: 10px; }}
.header h2 {{ font-size: 15px; font-weight: 600; letter-spacing: -0.01em; }}
.header .sub {{ font-size: 11px; color: var(--fg-muted); margin-top: 2px; }}
.loading {{ text-align: center; padding: 48px 0; color: var(--fg-muted); font-size: 13px; }}
</style>"""

SHARED_MCP_HANDSHAKE = """\
  // MCP Apps protocol handshake
  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    switch (msg.method) {
      case 'ui/notifications/tool-result':
        _render(msg.params.structuredContent || _parseContent(msg.params.content));
        break;
      case 'ui/notifications/host-context-changed':
        if (msg.params && msg.params.styles && msg.params.styles.variables)
          _applyTheme(msg.params.styles.variables);
        break;
    }
    if (msg.id !== undefined && msg.method === 'ui/initialize') {
      window.parent.postMessage({ jsonrpc:'2.0', id: msg.id, result: {
        protocolVersion: '2025-06-18',
        appCapabilities: { availableDisplayModes: ['inline','fullscreen'] }
      }}, '*');
      window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/initialized', params:{} }, '*');
    }
  });

  function _parseContent(c) {
    if (!c) return null;
    var arr = Array.isArray(c) ? c : [c];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }
  function _applyTheme(vars) {
    var r = document.documentElement;
    for (var k in vars) if (vars[k]) r.style.setProperty('--' + k, vars[k]);
  }
  function _notifySize() {
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed',
      params:{ height: document.documentElement.scrollHeight } }, '*');
  }
  function _esc(s) { var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
  function _fmtDate(d) {
    if (!d) return '';
    var s = String(d);
    return s.length === 8 ? s.substring(0,4)+'-'+s.substring(4,6)+'-'+s.substring(6,8) : s;
  }
"""

# ═══════════════════════════════════════════════════════════
# 1. K线图 — AG Charts candlestick + volume (单实例, grid 联动)
# ═══════════════════════════════════════════════════════════

KLINE_CHART_HTML = f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
{SHARED_HEAD}
<title>K线图</title>
<style>
#chart {{ width: 100%; height: 520px; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin-top: 8px; }}
.stat {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 8px 10px; }}
.stat-label {{ font-size: 10px; color: var(--fg-muted); text-transform: uppercase; letter-spacing: 0.04em; }}
.stat-value {{ font-size: 16px; font-weight: 600; font-family: var(--font-mono); margin-top: 2px; }}
.up {{ color: var(--up); }} .down {{ color: var(--down); }}
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script src="{AG_CHARTS_CDN}"></script>
<script>
(function() {{
  agCharts.AgCharts.setLicenseKey("{AG_LICENSE}");
  var chartInstance = null;

  {SHARED_MCP_HANDSHAKE}

  function _render(raw) {{
    if (!raw) return;
    var tsCode = raw.ts_code || '';
    var dailyData = raw.daily_data || raw.data || {{}};
    var items = dailyData.items || [];
    var stats = dailyData.price_statistics || {{}};
    var app = document.getElementById('app');
    app.classList.remove('loading');

    if (!items.length) {{
      // Fallback: show statistics cards only
      var title = _esc(tsCode) + (raw.days ? ' ' + raw.days + '日' : '') + ' 行情统计';
      var html = '<div class="header"><h2>' + title + '</h2>' +
        '<div class="sub">数据来源：Tushare Pro' +
        (dailyData.start_date ? ' | ' + _fmtDate(dailyData.start_date) + ' ~ ' + _fmtDate(dailyData.end_date) : '') +
        '</div></div>';
      if (stats && stats.max_price != null) {{
        var chg = dailyData.trend_statistics && dailyData.trend_statistics.total_change;
        var chgCls = chg >= 0 ? 'up' : 'down';
        var chgSign = chg >= 0 ? '+' : '';
        html += '<div class="stats">' +
          '<div class="stat"><div class="stat-label">最新价</div><div class="stat-value">' + (stats.latest_price || '-') + '</div></div>' +
          '<div class="stat"><div class="stat-label">区间涨跌</div><div class="stat-value ' + chgCls + '">' + (chg != null ? chgSign + chg.toFixed(2) + '%' : '-') + '</div></div>' +
          '<div class="stat"><div class="stat-label">最高</div><div class="stat-value up">' + stats.max_price + '</div></div>' +
          '<div class="stat"><div class="stat-label">最低</div><div class="stat-value down">' + stats.min_price + '</div></div>' +
          '<div class="stat"><div class="stat-label">均价</div><div class="stat-value">' + (stats.avg_price || '-') + '</div></div>' +
          '<div class="stat"><div class="stat-label">波动率</div><div class="stat-value">' + (stats.price_volatility != null ? (stats.price_volatility * 100).toFixed(2) + '%' : '-') + '</div></div>' +
          '</div>';
        html += '<div style="margin-top:10px;padding:10px;border-radius:var(--radius);background:var(--bg-muted);color:var(--fg-muted);font-size:12px;text-align:center">' +
          '提示：设置 include_items=true 可显示K线图</div>';
      }}
      app.innerHTML = html;
      _notifySize();
      return;
    }}

    // Sort ascending
    items.sort(function(a, b) {{ return String(a.trade_date||'').localeCompare(String(b.trade_date||'')); }});

    var title = _esc(tsCode) + (raw.days ? ' ' + raw.days + '日K线' : ' K线');
    app.innerHTML = '<div class="header"><h2>' + title + '</h2>' +
      '<div class="sub">' + _fmtDate(items[0].trade_date) + ' ~ ' + _fmtDate(items[items.length-1].trade_date) +
      ' | ' + items.length + '个交易日 | Tushare Pro</div></div>' +
      '<div id="chart"></div>';

    // Prepare data
    var data = items.map(function(it) {{
      return {{
        date: new Date(_fmtDate(it.trade_date)),
        open: it.open,
        high: it.high,
        low: it.low,
        close: it.close,
        volume: (it.vol || 0) / 100  // 手
      }};
    }});

    // Compute MAs
    function calcMA(arr, period) {{
      return arr.map(function(d, i) {{
        if (i < period - 1) return null;
        var sum = 0;
        for (var j = 0; j < period; j++) sum += arr[i - j].close;
        return +(sum / period).toFixed(2);
      }});
    }}
    var ma5 = calcMA(data, 5);
    var ma10 = calcMA(data, 10);
    var ma20 = calcMA(data, 20);
    data.forEach(function(d, i) {{
      d.ma5 = ma5[i]; d.ma10 = ma10[i]; d.ma20 = ma20[i];
    }});

    // Determine colors
    var upFill = getComputedStyle(document.documentElement).getPropertyValue('--up').trim() || '#c23531';
    var downFill = getComputedStyle(document.documentElement).getPropertyValue('--down').trim() || '#2f9e44';
    var borderColor = getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#ccc';
    var fgMuted = getComputedStyle(document.documentElement).getPropertyValue('--fg-muted').trim() || '#999';
    var primary = getComputedStyle(document.documentElement).getPropertyValue('--primary').trim() || '#2d5a8e';

    chartInstance = agCharts.AgCharts.create({{
      container: document.getElementById('chart'),
      data: data,
      theme: {{
        baseTheme: 'ag-default',
        overrides: {{
          common: {{
            background: {{ fill: 'transparent' }},
            axes: {{
              number: {{ label: {{ color: fgMuted, fontFamily: 'var(--font-mono)', fontSize: 10 }},
                         gridLine: {{ style: [{{ stroke: borderColor, lineDash: [3, 3] }}] }} }},
              time: {{ label: {{ color: fgMuted, fontFamily: 'var(--font-mono)', fontSize: 10 }} }}
            }}
          }}
        }}
      }},
      axes: [
        {{
          type: 'time',
          position: 'bottom',
          nice: false,
          label: {{ format: '%m-%d' }}
        }},
        {{
          type: 'number',
          position: 'left',
          keys: ['open', 'high', 'low', 'close', 'ma5', 'ma10', 'ma20'],
          label: {{ formatter: function(p) {{ return p.value.toFixed(2); }} }}
        }},
        {{
          type: 'number',
          position: 'right',
          keys: ['volume'],
          label: {{ formatter: function(p) {{ return (p.value / 10000).toFixed(0) + '万'; }} }}
        }}
      ],
      series: [
        {{
          type: 'candlestick',
          xKey: 'date',
          openKey: 'open', highKey: 'high', lowKey: 'low', closeKey: 'close',
          item: {{
            up: {{ fill: upFill, stroke: upFill }},
            down: {{ fill: downFill, stroke: downFill }}
          }},
          tooltip: {{
            renderer: function(p) {{
              var d = p.datum;
              var chg = d.close - d.open;
              var pct = d.open ? ((chg / d.open) * 100).toFixed(2) : '0.00';
              var clr = chg >= 0 ? upFill : downFill;
              return {{
                title: p.xValue.toLocaleDateString('zh-CN'),
                content: '<div style="font-family:var(--font-mono);font-size:12px;line-height:1.8">' +
                  '开 ' + d.open + '　高 ' + d.high + '<br>' +
                  '低 ' + d.low + '　收 ' + d.close + '<br>' +
                  '<span style="color:' + clr + '">涨跌 ' + (chg>=0?'+':'') + pct + '%</span><br>' +
                  '量 ' + (d.volume/10000).toFixed(0) + '万手</div>'
              }};
            }}
          }}
        }},
        {{
          type: 'bar',
          xKey: 'date',
          yKey: 'volume',
          yName: '成交量(手)',
          formatter: function(p) {{
            var d = p.datum;
            return {{ fill: d.close >= d.open ? upFill : downFill, fillOpacity: 0.35 }};
          }},
          tooltip: {{ enabled: false }}
        }},
        {{
          type: 'line', xKey: 'date', yKey: 'ma5', yName: 'MA5',
          stroke: '#f59e0b', strokeWidth: 1.2, marker: {{ enabled: false }}
        }},
        {{
          type: 'line', xKey: 'date', yKey: 'ma10', yName: 'MA10',
          stroke: primary, strokeWidth: 1.2, marker: {{ enabled: false }}
        }},
        {{
          type: 'line', xKey: 'date', yKey: 'ma20', yName: 'MA20',
          stroke: '#8b5cf6', strokeWidth: 1.2, marker: {{ enabled: false }}
        }}
      ],
      legend: {{
        position: 'top',
        item: {{ label: {{ color: fgMuted, fontSize: 11 }} }}
      }},
      navigator: {{ enabled: true, height: 24 }}
    }});

    _notifySize();
  }}
}})();
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════
# 2. 资金流向 — 堆叠柱状(大单结构) + 净额折线 + 零线
# ═══════════════════════════════════════════════════════════

MONEYFLOW_CHART_HTML = f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
{SHARED_HEAD}
<title>资金流向</title>
<style>
#chart {{ width: 100%; height: 460px; }}
.summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 6px; margin-top: 8px; }}
.sum-card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 8px 10px; }}
.sum-label {{ font-size: 10px; color: var(--fg-muted); }}
.sum-value {{ font-size: 15px; font-weight: 600; font-family: var(--font-mono); margin-top: 2px; }}
.up {{ color: var(--up); }} .down {{ color: var(--down); }}
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script src="{AG_CHARTS_CDN}"></script>
<script>
(function() {{
  agCharts.AgCharts.setLicenseKey("{AG_LICENSE}");
  var chartInstance = null;

  {SHARED_MCP_HANDSHAKE}

  function toYi(v) {{ return v == null ? 0 : +(v / 100000).toFixed(4); }}

  function _render(raw) {{
    if (!raw) return;
    var tsCode = _esc(raw.ts_code || '');
    var items = raw.data || raw.items || [];
    if (!Array.isArray(items)) items = [];
    var app = document.getElementById('app');
    app.classList.remove('loading');

    if (!items.length) {{
      app.innerHTML = '<div class="header"><h2>' + tsCode + ' 资金流向</h2></div>' +
        '<div class="loading">暂无资金流向数据</div>';
      _notifySize(); return;
    }}

    items.sort(function(a, b) {{ return String(a.trade_date||'').localeCompare(String(b.trade_date||'')); }});

    // Compute data
    var data = items.map(function(it) {{
      var sm = toYi((it.buy_sm_amount||0) - (it.sell_sm_amount||0));
      var md = toYi((it.buy_md_amount||0) - (it.sell_md_amount||0));
      var lg = toYi((it.buy_lg_amount||0) - (it.sell_lg_amount||0));
      var elg = toYi((it.buy_elg_amount||0) - (it.sell_elg_amount||0));
      var net = it.net_mf_amount != null ? toYi(it.net_mf_amount) : sm + md + lg + elg;
      return {{
        date: _fmtDate(it.trade_date),
        sm: sm, md: md, lg: lg, elg: elg, net: net,
        mainForce: lg + elg  // 主力 = 大单+超大单
      }};
    }});

    // Summary
    var totalNet = 0, totalMain = 0;
    data.forEach(function(d) {{ totalNet += d.net; totalMain += d.mainForce; }});
    var netCls = totalNet >= 0 ? 'up' : 'down';
    var mainCls = totalMain >= 0 ? 'up' : 'down';

    app.innerHTML = '<div class="header"><h2>' + tsCode + ' 资金流向</h2>' +
      '<div class="sub">' + data[0].date + ' ~ ' + data[data.length-1].date +
      ' | ' + data.length + '个交易日 | 单位：亿元</div></div>' +
      '<div id="chart"></div>' +
      '<div class="summary">' +
        '<div class="sum-card"><div class="sum-label">区间净流入</div><div class="sum-value ' + netCls + '">' + (totalNet>=0?'+':'') + totalNet.toFixed(2) + '亿</div></div>' +
        '<div class="sum-card"><div class="sum-label">主力净流入</div><div class="sum-value ' + mainCls + '">' + (totalMain>=0?'+':'') + totalMain.toFixed(2) + '亿</div></div>' +
        '<div class="sum-card"><div class="sum-label">净流入天数</div><div class="sum-value">' + data.filter(function(d){{return d.net>0}}).length + '/' + data.length + '</div></div>' +
      '</div>';

    var upFill = getComputedStyle(document.documentElement).getPropertyValue('--up').trim();
    var downFill = getComputedStyle(document.documentElement).getPropertyValue('--down').trim();
    var fgMuted = getComputedStyle(document.documentElement).getPropertyValue('--fg-muted').trim();
    var borderColor = getComputedStyle(document.documentElement).getPropertyValue('--border').trim();

    chartInstance = agCharts.AgCharts.create({{
      container: document.getElementById('chart'),
      data: data,
      theme: {{
        baseTheme: 'ag-default',
        overrides: {{
          common: {{
            background: {{ fill: 'transparent' }},
            axes: {{
              category: {{ label: {{ color: fgMuted, fontSize: 10 }} }},
              number: {{ label: {{ color: fgMuted, fontFamily: 'var(--font-mono)', fontSize: 10 }},
                         gridLine: {{ style: [{{ stroke: borderColor, lineDash: [3, 3] }}] }} }}
            }}
          }}
        }}
      }},
      axes: [
        {{ type: 'category', position: 'bottom', label: {{ rotation: -30 }} }},
        {{ type: 'number', position: 'left',
           label: {{ formatter: function(p) {{ return p.value.toFixed(1); }} }},
           crossLines: [{{ type: 'line', value: 0, stroke: fgMuted, strokeWidth: 1 }}]
        }}
      ],
      series: [
        {{
          type: 'bar', xKey: 'date', yKey: 'elg', yName: '超大单',
          stacked: true, fill: upFill, fillOpacity: 0.8
        }},
        {{
          type: 'bar', xKey: 'date', yKey: 'lg', yName: '大单',
          stacked: true, fill: '#f59e0b', fillOpacity: 0.7
        }},
        {{
          type: 'bar', xKey: 'date', yKey: 'md', yName: '中单',
          stacked: true, fill: '#60a5fa', fillOpacity: 0.6
        }},
        {{
          type: 'bar', xKey: 'date', yKey: 'sm', yName: '散户',
          stacked: true, fill: '#9ca3af', fillOpacity: 0.5
        }},
        {{
          type: 'line', xKey: 'date', yKey: 'net', yName: '净流入',
          stroke: upFill, strokeWidth: 2.5,
          marker: {{ size: 3, fill: upFill }}
        }}
      ],
      legend: {{
        position: 'top',
        item: {{ label: {{ color: fgMuted, fontSize: 11 }} }}
      }},
      tooltip: {{
        class: 'ag-tooltip',
      }},
      navigator: {{ enabled: true, height: 20 }}
    }});

    _notifySize();
  }}
}})();
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════
# 3. 市场仪表板 — AG Grid 数据表 + AG Charts 涨跌分布
# ═══════════════════════════════════════════════════════════

MARKET_DASHBOARD_HTML = f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
{SHARED_HEAD}
<title>市场概况</title>
<style>
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 6px; margin-bottom: 12px; }}
.kpi {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 10px; }}
.kpi-value {{ font-size: 20px; font-weight: 700; font-family: var(--font-mono); letter-spacing: -0.02em; }}
.kpi-label {{ font-size: 10px; color: var(--fg-muted); margin-top: 3px; text-transform: uppercase; letter-spacing: 0.04em; }}
.up {{ color: var(--up); }} .down {{ color: var(--down); }}
.chart-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }}
#chart-dist {{ height: 220px; }}
#chart-pie {{ height: 220px; }}
@media (max-width: 480px) {{ .chart-row {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script src="{AG_CHARTS_CDN}"></script>
<script>
(function() {{
  agCharts.AgCharts.setLicenseKey("{AG_LICENSE}");

  {SHARED_MCP_HANDSHAKE}

  function _render(raw) {{
    if (!raw) return;
    var data = raw.data || raw;
    var app = document.getElementById('app');
    app.classList.remove('loading');

    var ad = data.advance_decline || {{}};
    var ls = data.limit_stats || {{}};
    var am = data.amount_stats || {{}};
    var ps = data.pct_chg_stats || {{}};
    var mkt = data.market === 'all' ? 'A股' : _esc(data.market || '');

    var meanCls = (ps.mean||0) >= 0 ? 'up' : 'down';
    var meanSign = (ps.mean||0) >= 0 ? '+' : '';
    var amtYi = am.total != null ? (am.total >= 10000 ? (am.total/10000).toFixed(1)+'万亿' : am.total.toFixed(0)+'亿') : '-';

    app.innerHTML =
      '<div class="header"><h2>' + mkt + '市场概况</h2>' +
      '<div class="sub">' + _esc(data.trade_date || '-') + ' · 共 ' + (data.total_stocks||'-') + ' 只</div></div>' +
      '<div class="kpi-grid">' +
        '<div class="kpi"><div class="kpi-value ' + meanCls + '">' + meanSign + (ps.mean!=null?ps.mean.toFixed(2):'0.00') + '%</div><div class="kpi-label">平均涨幅</div></div>' +
        '<div class="kpi"><div class="kpi-value up">' + (ad.advance||0) + '</div><div class="kpi-label">上涨 (' + (ad.advance_ratio||0) + '%)</div></div>' +
        '<div class="kpi"><div class="kpi-value down">' + (ad.decline||0) + '</div><div class="kpi-label">下跌 (' + (ad.decline_ratio||0) + '%)</div></div>' +
        '<div class="kpi"><div class="kpi-value up">' + (ls.limit_up||0) + '</div><div class="kpi-label">涨停</div></div>' +
        '<div class="kpi"><div class="kpi-value down">' + (ls.limit_down||0) + '</div><div class="kpi-label">跌停</div></div>' +
        '<div class="kpi"><div class="kpi-value">' + amtYi + '</div><div class="kpi-label">成交额</div></div>' +
      '</div>' +
      '<div class="chart-row"><div id="chart-dist"></div><div id="chart-pie"></div></div>';

    var upFill = getComputedStyle(document.documentElement).getPropertyValue('--up').trim();
    var downFill = getComputedStyle(document.documentElement).getPropertyValue('--down').trim();
    var fgMuted = getComputedStyle(document.documentElement).getPropertyValue('--fg-muted').trim();
    var borderColor = getComputedStyle(document.documentElement).getPropertyValue('--border').trim();

    // Distribution histogram
    var dist = data.pct_chg_distribution || ps.distribution;
    if (dist && typeof dist === 'object') {{
      var distData = [];
      var rangeOrder = ['<-5%', '-5~-3%', '-3~-1%', '-1~0%', '0~1%', '1~3%', '3~5%', '>5%'];
      rangeOrder.forEach(function(key) {{
        if (dist[key] != null) distData.push({{ range: key, count: dist[key] }});
      }});
      if (!distData.length) {{
        Object.keys(dist).forEach(function(k) {{ distData.push({{ range: k, count: dist[k] }}); }});
      }}
      if (distData.length) {{
        agCharts.AgCharts.create({{
          container: document.getElementById('chart-dist'),
          data: distData,
          theme: {{ baseTheme: 'ag-default', overrides: {{ common: {{ background: {{ fill: 'transparent' }} }} }} }},
          title: {{ text: '涨跌分布', fontSize: 13, color: fgMuted }},
          axes: [
            {{ type: 'category', position: 'bottom', label: {{ color: fgMuted, fontSize: 9, rotation: -30 }} }},
            {{ type: 'number', position: 'left', label: {{ color: fgMuted, fontSize: 9 }},
               gridLine: {{ style: [{{ stroke: borderColor, lineDash: [3,3] }}] }} }}
          ],
          series: [{{
            type: 'bar', xKey: 'range', yKey: 'count', yName: '股票数',
            formatter: function(p) {{
              var r = p.datum.range;
              var isDown = r.indexOf('-') === 0 || r.indexOf('<-') === 0;
              return {{ fill: isDown ? downFill : upFill, fillOpacity: 0.75 }};
            }},
            cornerRadius: 3
          }}],
          legend: {{ enabled: false }}
        }});
      }}
    }}

    // Pie chart: advance / flat / decline
    var pieData = [
      {{ label: '上涨', value: ad.advance || 0 }},
      {{ label: '平盘', value: ad.flat || 0 }},
      {{ label: '下跌', value: ad.decline || 0 }}
    ];
    agCharts.AgCharts.create({{
      container: document.getElementById('chart-pie'),
      data: pieData,
      theme: {{ baseTheme: 'ag-default', overrides: {{ common: {{ background: {{ fill: 'transparent' }} }} }} }},
      title: {{ text: '涨跌比', fontSize: 13, color: fgMuted }},
      series: [{{
        type: 'donut',
        angleKey: 'value',
        calloutLabelKey: 'label',
        sectorLabelKey: 'value',
        innerRadiusRatio: 0.55,
        fills: [upFill, '#d1d5db', downFill],
        calloutLabel: {{ color: fgMuted, fontSize: 11 }},
        sectorLabel: {{ color: '#fff', fontSize: 11, fontWeight: 600 }}
      }}],
      legend: {{ enabled: false }}
    }});

    _notifySize();
  }}
}})();
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════
# 资源注册
# ═══════════════════════════════════════════════════════════

def register_ui_app_resources(mcp: FastMCP):
    """注册 MCP Apps ui:// 交互式 HTML 资源 (AG Charts Enterprise)"""

    @mcp.resource(
        "ui://tushare/kline-chart",
        name="K线图",
        description="股票K线图（AG Charts candlestick + 成交量 + 均线），支持缩放导航",
        mime_type="text/html",
        meta={
            "ui": {
                "profile": "mcp-app",
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": ["https://cdn.jsdelivr.net"]
                },
                "prefersBorder": True
            }
        }
    )
    def kline_chart_resource() -> str:
        return KLINE_CHART_HTML

    @mcp.resource(
        "ui://tushare/moneyflow-chart",
        name="资金流向图",
        description="个股资金流向：堆叠柱状(大单/中单/小单结构) + 净额折线 + 汇总统计",
        mime_type="text/html",
        meta={
            "ui": {
                "profile": "mcp-app",
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": ["https://cdn.jsdelivr.net"]
                },
                "prefersBorder": True
            }
        }
    )
    def moneyflow_chart_resource() -> str:
        return MONEYFLOW_CHART_HTML

    @mcp.resource(
        "ui://tushare/market-dashboard",
        name="市场概况仪表板",
        description="A股市场整体KPI卡片 + 涨跌分布直方图 + 涨跌比环形图",
        mime_type="text/html",
        meta={
            "ui": {
                "profile": "mcp-app",
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": ["https://cdn.jsdelivr.net"]
                },
                "prefersBorder": True
            }
        }
    )
    def market_dashboard_resource() -> str:
        return MARKET_DASHBOARD_HTML

    logger.info("✅ Registered 3 ui:// MCP App resources (AG Charts Enterprise)")
