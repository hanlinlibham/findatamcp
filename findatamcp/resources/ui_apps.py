"""
MCP Apps UI 资源模块

注册 ui:// 协议资源，为工具返回提供交互式 HTML 可视化：
- ui://tushare/market-dashboard: 市场概况仪表板（ECharts）
- ui://tushare/macro-panel: 宏观经济指标面板
- ui://tushare/data-table: 通用可交互数据表格
- ui://tushare/kline-chart: K线图（OHLC+成交量+均线）
- ui://tushare/moneyflow-chart: 资金流向多线折线图

参考：MCP Apps 规范 (SEP-1865)
协议版本：2025-06-18
"""

import logging
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ECharts 5 — loaded from local file (no CDN dependency)
import pathlib as _pathlib
_ECHARTS_JS = (_pathlib.Path(__file__).parent.parent.parent / "static" / "echarts.min.js").read_text(encoding="utf-8")

# ─────────────────────────────────────────────────────────
# HTML 模板
# ─────────────────────────────────────────────────────────

MARKET_DASHBOARD_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>市场概况</title>
<style>
:root {
  --color-background-primary: light-dark(#ffffff, #1a1a1a);
  --color-text-primary: light-dark(#171717, #e5e5e5);
  --color-text-secondary: light-dark(#6b7280, #9ca3af);
  --color-border-primary: light-dark(#e5e5e5, #333333);
  --font-sans: system-ui, -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", monospace;
  --border-radius-md: 8px;
  --color-up: #ef4444;
  --color-down: #22c55e;
  --color-flat: #9ca3af;
}
* { margin: 0; box-sizing: border-box; }
body {
  font-family: var(--font-sans);
  color: var(--color-text-primary);
  background: transparent;
  padding: 16px; line-height: 1.5;
}
.header { margin-bottom: 16px; }
.header h2 { font-size: 16px; font-weight: 600; }
.header .sub { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }
.card { border: 1px solid var(--color-border-primary); border-radius: var(--border-radius-md); padding: 14px 12px; }
.stat-value { font-size: 22px; font-weight: 600; font-family: var(--font-mono); letter-spacing: -0.02em; }
.stat-label { font-size: 11px; color: var(--color-text-secondary); margin-top: 4px; }
.up { color: var(--color-up); }
.down { color: var(--color-down); }
.flat { color: var(--color-flat); }
#chart { width: 100%; height: 280px; margin-top: 8px; }
.loading { text-align: center; padding: 48px 0; color: var(--color-text-secondary); font-size: 13px; }
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script>var module=undefined,exports=undefined,define=undefined;</script>
<script>/* ECHARTS_PLACEHOLDER */</script>
<script>
(function(){
  var toolInput = null, toolResult = null;

  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    switch (msg.method) {
      case 'ui/notifications/tool-input':
        toolInput = msg.params && msg.params.arguments; break;
      case 'ui/notifications/tool-result':
        toolResult = msg.params;
        render(toolResult.structuredContent || parseContent(toolResult.content));
        break;
      case 'ui/notifications/host-context-changed':
        if (msg.params && msg.params.styles && msg.params.styles.variables)
          applyTheme(msg.params.styles.variables);
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

  function parseContent(content) {
    if (!content) return null;
    var arr = Array.isArray(content) ? content : [content];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }

  function applyTheme(vars) {
    var r = document.documentElement;
    for (var k in vars) if (vars[k]) r.style.setProperty('--' + k, vars[k]);
  }

  function fmt(n) {
    if (n == null) return '-';
    if (Math.abs(n) >= 10000) return (n/10000).toFixed(1) + '万亿';
    if (Math.abs(n) >= 1) return n.toFixed(1);
    return n.toFixed(2);
  }

  function render(raw) {
    if (!raw) return;
    var data = raw.data || raw;
    var app = document.getElementById('app');
    app.classList.remove('loading');
    var ad = data.advance_decline || {};
    var ls = data.limit_stats || {};
    var am = data.amount_stats || {};
    var vs = data.valuation_stats || {};
    var ps = data.pct_chg_stats || {};
    var mkt = data.market === 'all' ? 'A股' : data.market;

    var meanCls = ps.mean > 0 ? 'up' : ps.mean < 0 ? 'down' : '';
    var meanVal = ps.mean != null ? (ps.mean > 0 ? '+' : '') + ps.mean.toFixed(2) + '%' : '-';

    app.innerHTML =
      '<div class="header">' +
        '<h2>' + mkt + '市场概况</h2>' +
        '<div class="sub">' + (data.trade_date || '-') + ' · 共 ' + (data.total_stocks || '-') + ' 只</div>' +
      '</div>' +
      '<div class="grid">' +
        '<div class="card"><div class="stat-value ' + meanCls + '">' + meanVal + '</div><div class="stat-label">平均涨幅</div></div>' +
        '<div class="card"><div class="stat-value up">' + (ad.advance || '-') + '</div><div class="stat-label">上涨 (' + (ad.advance_ratio || 0) + '%)</div></div>' +
        '<div class="card"><div class="stat-value down">' + (ad.decline || '-') + '</div><div class="stat-label">下跌 (' + (ad.decline_ratio || 0) + '%)</div></div>' +
        '<div class="card"><div class="stat-value up">' + (ls.limit_up || 0) + '</div><div class="stat-label">涨停</div></div>' +
        '<div class="card"><div class="stat-value down">' + (ls.limit_down || 0) + '</div><div class="stat-label">跌停</div></div>' +
        '<div class="card"><div class="stat-value">' + fmt(am.total) + '亿</div><div class="stat-label">总成交额</div></div>' +
        '<div class="card"><div class="stat-value">' + (vs.pe_median != null ? vs.pe_median.toFixed(1) : '-') + '</div><div class="stat-label">PE 中位数</div></div>' +
        '<div class="card"><div class="stat-value">' + (vs.pb_median != null ? vs.pb_median.toFixed(2) : '-') + '</div><div class="stat-label">PB 中位数</div></div>' +
      '</div>' +
      '<div id="chart"></div>';
    renderCharts(data);
    notifySize();
  }

  function renderCharts(data) {
    var el = document.getElementById('chart');
    if (!el || !window.echarts) return;
    var c = echarts.init(el);
    var ad = data.advance_decline || {};
    c.setOption({
      tooltip: { trigger:'item', formatter:'{b}: {c} ({d}%)' },
      legend: { bottom: 0, textStyle: { fontSize: 11 } },
      series: [{
        type: 'pie', radius: ['38%','68%'], center: ['50%','45%'],
        padAngle: 2, itemStyle: { borderRadius: 4 },
        label: { formatter:'{b}\\n{c}只', fontSize: 11 },
        data: [
          { value: ad.advance || 0, name:'上涨', itemStyle:{ color:'#ef4444' } },
          { value: ad.flat || 0,    name:'平盘', itemStyle:{ color:'#d1d5db' } },
          { value: ad.decline || 0, name:'下跌', itemStyle:{ color:'#22c55e' } }
        ]
      }]
    });
    window.addEventListener('resize', function() { c.resize(); });
  }

  function notifySize() {
    var h = document.documentElement.scrollHeight;
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed', params:{ height: h } }, '*');
  }
})();
</script>
</body>
</html>"""


MACRO_PANEL_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>宏观经济面板</title>
<style>
:root {
  --color-background-primary: light-dark(#ffffff, #1a1a1a);
  --color-text-primary: light-dark(#171717, #e5e5e5);
  --color-text-secondary: light-dark(#6b7280, #9ca3af);
  --color-border-primary: light-dark(#e5e5e5, #333333);
  --font-sans: system-ui, -apple-system, "PingFang SC", sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", monospace;
  --border-radius-md: 8px;
}
* { margin: 0; box-sizing: border-box; }
body { font-family: var(--font-sans); color: var(--color-text-primary); background: transparent; padding: 16px; }
.header { margin-bottom: 16px; }
.header h2 { font-size: 16px; font-weight: 600; }
.header .sub { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.card { border: 1px solid var(--color-border-primary); border-radius: var(--border-radius-md); padding: 14px 12px; }
.card-title { font-size: 11px; color: var(--color-text-secondary); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.04em; }
.card-value { font-size: 20px; font-weight: 600; font-family: var(--font-mono); }
.card-detail { font-size: 11px; color: var(--color-text-secondary); margin-top: 4px; }
.card-tag { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 4px; margin-top: 6px; font-weight: 500; }
.tag-green { background: #dcfce7; color: #166534; }
.tag-red { background: #fee2e2; color: #991b1b; }
.tag-yellow { background: #fef3c7; color: #92400e; }
.tag-gray { background: #f3f4f6; color: #4b5563; }
.analysis { margin-top: 16px; padding: 12px; border: 1px solid var(--color-border-primary); border-radius: var(--border-radius-md); }
.analysis h3 { font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.analysis-item { font-size: 12px; color: var(--color-text-secondary); margin-bottom: 4px; }
.loading { text-align: center; padding: 48px 0; color: var(--color-text-secondary); font-size: 13px; }
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script>
(function(){
  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    if (msg.method === 'ui/notifications/tool-result') {
      var raw = msg.params;
      render(raw.structuredContent || parseContent(raw.content));
    }
    if (msg.method === 'ui/notifications/host-context-changed' && msg.params && msg.params.styles && msg.params.styles.variables) {
      var vars = msg.params.styles.variables;
      for (var k in vars) if (vars[k]) document.documentElement.style.setProperty('--'+k, vars[k]);
    }
    if (msg.id !== undefined && msg.method === 'ui/initialize') {
      window.parent.postMessage({ jsonrpc:'2.0', id:msg.id, result:{ protocolVersion:'2025-06-18', appCapabilities:{ availableDisplayModes:['inline','fullscreen'] } } }, '*');
      window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/initialized', params:{} }, '*');
    }
  });

  function parseContent(c) {
    if (!c) return null;
    var arr = Array.isArray(c) ? c : [c];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }

  function makeCard(title, value, period, tagClass, tagText, extra) {
    return '<div class="card">' +
      '<div class="card-title">' + title + '</div>' +
      '<div class="card-value">' + value + '</div>' +
      '<div class="card-detail">' + period + (extra ? ' &middot; ' + extra : '') + '</div>' +
      '<span class="card-tag ' + tagClass + '">' + tagText + '</span>' +
    '</div>';
  }

  function render(raw) {
    if (!raw) return;
    var data = raw.data || raw;
    var analysis = raw.analysis || {};
    var app = document.getElementById('app');
    app.classList.remove('loading');
    var cards = '';

    if (data.gdp) {
      var g = data.gdp;
      var gTag = g.gdp_yoy >= 5 ? 'tag-green' : g.gdp_yoy >= 3 ? 'tag-yellow' : 'tag-red';
      var gLabel = g.gdp_yoy >= 5 ? '高增长' : g.gdp_yoy >= 3 ? '中增长' : '低增长';
      cards += makeCard('GDP', g.gdp_yoy != null ? g.gdp_yoy + '%' : '-', g.quarter || '', gTag, gLabel, '');
    }
    if (data.cpi) {
      var c = data.cpi;
      var cTag = c.yoy >= 3 ? 'tag-red' : c.yoy >= 0 ? 'tag-green' : 'tag-yellow';
      var cLabel = c.yoy >= 3 ? '通胀压力' : c.yoy >= 0 ? '温和' : '通缩风险';
      cards += makeCard('CPI', c.yoy != null ? c.yoy + '%' : '-', c.month || '', cTag, cLabel, c.mom != null ? '环比 ' + c.mom + '%' : '');
    }
    if (data.ppi) {
      var p = data.ppi;
      var pTag = p.yoy >= 0 ? 'tag-green' : 'tag-yellow';
      cards += makeCard('PPI', p.yoy != null ? p.yoy + '%' : '-', p.month || '', pTag, p.yoy >= 0 ? '扩张' : '收缩', '');
    }
    if (data.pmi) {
      var m = data.pmi;
      var val = m.manufacturing_pmi || m.value;
      var mTag = val >= 50 ? 'tag-green' : 'tag-red';
      cards += makeCard('制造业 PMI', val != null ? val.toFixed(1) : '-', m.month || m.MONTH || '', mTag, val >= 50 ? '扩张' : '收缩', '');
    }
    if (data.money) {
      var mo = data.money;
      var moTag = mo.m2_yoy >= 10 ? 'tag-green' : mo.m2_yoy >= 8 ? 'tag-yellow' : 'tag-gray';
      cards += makeCard('M2 同比', mo.m2_yoy != null ? mo.m2_yoy + '%' : '-', mo.month || '', moTag, mo.m2_yoy >= 10 ? '宽松' : mo.m2_yoy >= 8 ? '适度' : '中性', '');
    }
    if (data.lpr) {
      var l = data.lpr;
      cards += makeCard('LPR 1Y/5Y', (l.lpr_1y || '-') + ' / ' + (l.lpr_5y || '-'), l.date || '', 'tag-gray', '基准利率', '');
    }

    var analysisHtml = '';
    var keys = Object.keys(analysis);
    if (keys.length > 0) {
      var items = '';
      for (var i = 0; i < keys.length; i++) items += '<div class="analysis-item">&middot; ' + analysis[keys[i]] + '</div>';
      analysisHtml = '<div class="analysis"><h3>综合判断</h3>' + items + '</div>';
    }

    app.innerHTML =
      '<div class="header"><h2>宏观经济面板</h2><div class="sub">数据来源：Tushare Pro</div></div>' +
      '<div class="grid">' + cards + '</div>' +
      analysisHtml;
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed', params:{ height: document.documentElement.scrollHeight } }, '*');
  }
})();
</script>
</body>
</html>"""


DATA_TABLE_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>数据表格</title>
<style>
:root {
  --color-background-primary: light-dark(#ffffff, #1a1a1a);
  --color-text-primary: light-dark(#171717, #e5e5e5);
  --color-text-secondary: light-dark(#6b7280, #9ca3af);
  --color-border-primary: light-dark(#e5e5e5, #333333);
  --color-row-hover: light-dark(#f9fafb, #222222);
  --font-sans: system-ui, -apple-system, "PingFang SC", sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", monospace;
}
* { margin: 0; box-sizing: border-box; }
body { font-family: var(--font-sans); color: var(--color-text-primary); background: transparent; padding: 16px; }
.header { margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; }
.header h2 { font-size: 15px; font-weight: 600; }
.header .count { font-size: 12px; color: var(--color-text-secondary); }
.search { width: 100%; padding: 6px 10px; border: 1px solid var(--color-border-primary); border-radius: 6px; background: transparent; color: var(--color-text-primary); font-size: 12px; margin-bottom: 10px; outline: none; }
.search:focus { border-color: #3b82f6; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { text-align: left; padding: 8px 10px; border-bottom: 2px solid var(--color-border-primary); font-weight: 600; font-size: 11px; color: var(--color-text-secondary); cursor: pointer; user-select: none; white-space: nowrap; }
th:hover { color: var(--color-text-primary); }
th .arrow { font-size: 10px; margin-left: 2px; }
td { padding: 7px 10px; border-bottom: 1px solid var(--color-border-primary); font-family: var(--font-mono); font-size: 12px; white-space: nowrap; }
tr:hover td { background: var(--color-row-hover); }
.up { color: #ef4444; }
.down { color: #22c55e; }
.right { text-align: right; }
.loading { text-align: center; padding: 48px 0; color: var(--color-text-secondary); font-size: 13px; }
.export-btn { font-size: 11px; padding: 4px 10px; border: 1px solid var(--color-border-primary); border-radius: 5px; background: transparent; color: var(--color-text-primary); cursor: pointer; }
.export-btn:hover { background: var(--color-row-hover); }
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script>
(function(){
  var tableData = [], sortCol = null, sortAsc = true, filterText = '';
  var LABELS = { ts_code:'代码', name:'名称', pct_chg:'涨跌幅%', close:'收盘', open:'开盘', high:'最高', low:'最低', pre_close:'昨收', volume:'成交量', amount:'成交额', trade_date:'日期', change:'涨跌额', industry:'行业', turnover_rate:'换手率%', start_price:'起始价', end_price:'终止价', data_points:'数据点' };

  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    if (msg.method === 'ui/notifications/tool-result') {
      var raw = msg.params;
      render(raw.structuredContent || parseContent(raw.content));
    }
    if (msg.method === 'ui/notifications/host-context-changed' && msg.params && msg.params.styles && msg.params.styles.variables) {
      var vars = msg.params.styles.variables;
      for (var k in vars) if (vars[k]) document.documentElement.style.setProperty('--'+k, vars[k]);
    }
    if (msg.id !== undefined && msg.method === 'ui/initialize') {
      window.parent.postMessage({ jsonrpc:'2.0', id:msg.id, result:{ protocolVersion:'2025-06-18', appCapabilities:{ availableDisplayModes:['inline','fullscreen'] } } }, '*');
      window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/initialized', params:{} }, '*');
    }
  });

  function parseContent(c) {
    if (!c) return null;
    var arr = Array.isArray(c) ? c : [c];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }

  function render(raw) {
    if (!raw) return;
    var d = raw.data || raw;
    if (Array.isArray(d)) tableData = d;
    else if (d.results) tableData = d.results;
    else if (d.items) tableData = d.items;
    else if (d.stocks) tableData = d.stocks;
    else if (d.top_gainers) tableData = d.top_gainers.concat(d.top_losers || []);
    else if (Array.isArray(d.data)) tableData = d.data;
    else if (Array.isArray(d.preview)) tableData = d.preview;
    else tableData = [d];

    if (!tableData.length) {
      document.getElementById('app').innerHTML = '<div class="loading">无数据</div>';
      return;
    }
    document.getElementById('app').classList.remove('loading');
    renderTable();
  }

  function renderTable() {
    var app = document.getElementById('app');
    var cols = [];
    var first = tableData[0];
    for (var k in first) if (first.hasOwnProperty(k) && k !== 'error') cols.push(k);

    var rows = tableData;
    if (filterText) {
      var q = filterText.toLowerCase();
      rows = rows.filter(function(r) {
        for (var i = 0; i < cols.length; i++) {
          if (String(r[cols[i]] || '').toLowerCase().indexOf(q) >= 0) return true;
        }
        return false;
      });
    }
    if (sortCol) {
      rows = rows.slice().sort(function(a, b) {
        var va = a[sortCol], vb = b[sortCol];
        if (typeof va === 'number' && typeof vb === 'number') return sortAsc ? va - vb : vb - va;
        return sortAsc ? String(va||'').localeCompare(String(vb||'')) : String(vb||'').localeCompare(String(va||''));
      });
    }

    var numCols = {};
    for (var i = 0; i < cols.length; i++) {
      if (typeof tableData[0][cols[i]] === 'number') numCols[cols[i]] = true;
    }

    var ths = '';
    for (var i = 0; i < cols.length; i++) {
      var c = cols[i];
      var arrow = sortCol === c ? (sortAsc ? '&#8593;' : '&#8595;') : '';
      ths += '<th class="' + (numCols[c] ? 'right' : '') + '" data-col="' + c + '">' + (LABELS[c] || c) + '<span class="arrow">' + arrow + '</span></th>';
    }

    var trs = '';
    for (var r = 0; r < rows.length; r++) {
      var tds = '';
      for (var ci = 0; ci < cols.length; ci++) {
        var c = cols[ci];
        var v = rows[r][c];
        var cls = numCols[c] ? 'right' : '';
        if ((c === 'pct_chg' || c === 'change') && typeof v === 'number') {
          cls += v > 0 ? ' up' : v < 0 ? ' down' : '';
          v = (v > 0 ? '+' : '') + v.toFixed(2);
        } else if (typeof v === 'number') {
          v = Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
        }
        tds += '<td class="' + cls + '">' + (v != null ? v : '-') + '</td>';
      }
      trs += '<tr>' + tds + '</tr>';
    }

    app.innerHTML =
      '<div class="header"><h2>数据明细</h2><div><span class="count">' + rows.length + ' 条</span> <button class="export-btn" id="exportBtn">导出 CSV</button></div></div>' +
      '<input class="search" placeholder="搜索…" value="' + filterText + '" id="searchInput">' +
      '<table><thead><tr>' + ths + '</tr></thead><tbody>' + trs + '</tbody></table>';

    document.getElementById('searchInput').addEventListener('input', function(e) {
      filterText = e.target.value;
      renderTable();
    });
    document.getElementById('exportBtn').addEventListener('click', exportCSV);

    var headers = app.querySelectorAll('th');
    for (var h = 0; h < headers.length; h++) {
      headers[h].addEventListener('click', function() {
        var col = this.getAttribute('data-col');
        if (sortCol === col) sortAsc = !sortAsc;
        else { sortCol = col; sortAsc = true; }
        renderTable();
      });
    }

    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed', params:{ height: document.documentElement.scrollHeight } }, '*');
  }

  function exportCSV() {
    if (!tableData.length) return;
    var cols = Object.keys(tableData[0]);
    var lines = [cols.join(',')];
    for (var i = 0; i < tableData.length; i++) {
      var row = [];
      for (var j = 0; j < cols.length; j++) row.push(JSON.stringify(tableData[i][cols[j]] != null ? tableData[i][cols[j]] : ''));
      lines.push(row.join(','));
    }
    var blob = new Blob(['\\uFEFF' + lines.join('\\n')], { type:'text/csv;charset=utf-8' });
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'data_' + new Date().toISOString().slice(0,10) + '.csv';
    a.click();
  }
})();
</script>
</body>
</html>"""


CANDLESTICK_CHART_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>K线图</title>
<style>
:root {
  --color-background-primary: light-dark(#ffffff, #1a1a1a);
  --color-background-secondary: light-dark(#f8f9fa, #222222);
  --color-text-primary: light-dark(#171717, #e5e5e5);
  --color-text-secondary: light-dark(#6b7280, #9ca3af);
  --color-border-primary: light-dark(#e5e5e5, #333333);
  --font-sans: system-ui, -apple-system, "PingFang SC", sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", monospace;
  --color-positive: #ef4444;
  --color-negative: #22c55e;
}
* { margin: 0; box-sizing: border-box; }
body {
  font-family: var(--font-sans);
  color: var(--color-text-primary);
  background: transparent;
  padding: 16px; line-height: 1.5;
}
.header { margin-bottom: 12px; }
.header h2 { font-size: 16px; font-weight: 600; }
.header .sub { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }
#chart-main { width: 100%; height: 400px; }
#chart-vol { width: 100%; height: 120px; }
.summary { margin-top: 12px; padding: 12px; border: 1px solid var(--color-border-primary); border-radius: 8px; background: var(--color-background-secondary); }
.summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }
.summary-item { font-size: 12px; }
.summary-label { color: var(--color-text-secondary); font-size: 11px; }
.summary-value { font-family: var(--font-mono); font-weight: 600; }
.loading { text-align: center; padding: 48px 0; color: var(--color-text-secondary); font-size: 13px; }
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script>var module=undefined,exports=undefined,define=undefined;</script>
<script>/* ECHARTS_PLACEHOLDER */</script>
<script>
(function(){
  var chartMain = null, chartVol = null;

  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    switch (msg.method) {
      case 'ui/notifications/tool-result':
        var raw = msg.params;
        render(raw.structuredContent || parseContent(raw.content));
        break;
      case 'ui/notifications/host-context-changed':
        if (msg.params && msg.params.styles && msg.params.styles.variables)
          applyTheme(msg.params.styles.variables);
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

  function parseContent(c) {
    if (!c) return null;
    var arr = Array.isArray(c) ? c : [c];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }

  function applyTheme(vars) {
    var r = document.documentElement;
    for (var k in vars) if (vars[k]) r.style.setProperty('--' + k, vars[k]);
  }

  function calcMA(items, period) {
    var result = [];
    for (var i = 0; i < items.length; i++) {
      if (i < period - 1) { result.push(null); continue; }
      var sum = 0;
      for (var j = 0; j < period; j++) {
        sum += items[i - j].close;
      }
      result.push(+(sum / period).toFixed(2));
    }
    return result;
  }

  function formatDate(d) {
    if (!d) return '';
    var s = String(d);
    if (s.length === 8) return s.substring(0, 4) + '-' + s.substring(4, 6) + '-' + s.substring(6, 8);
    return s;
  }

  function render(raw) {
    if (!raw) return;
    var tsCode = raw.ts_code || '';
    var days = raw.days || '';
    var dailyData = raw.daily_data || raw.data || {};
    var items = dailyData.items || [];
    var stats = dailyData.price_statistics || {};
    var app = document.getElementById('app');
    app.classList.remove('loading');

    // If no items array, show summary fallback
    if (!items.length) {
      var title = tsCode + (days ? ' ' + days + '日' : '') + ' 行情统计';
      var html = '<div class="header"><h2>' + title + '</h2>' +
        '<div class="sub">数据来源：Tushare Pro' +
        (dailyData.start_date ? ' | ' + formatDate(dailyData.start_date) + ' ~ ' + formatDate(dailyData.end_date) : '') +
        '</div></div>';
      if (stats && stats.max_price != null) {
        html += '<div class="summary"><div class="summary-grid">' +
          '<div class="summary-item"><div class="summary-label">最高价</div><div class="summary-value">' + stats.max_price + '</div></div>' +
          '<div class="summary-item"><div class="summary-label">最低价</div><div class="summary-value">' + stats.min_price + '</div></div>' +
          '<div class="summary-item"><div class="summary-label">均价</div><div class="summary-value">' + (stats.avg_price || '-') + '</div></div>' +
          '<div class="summary-item"><div class="summary-label">波动率</div><div class="summary-value">' + (stats.price_volatility != null ? stats.price_volatility.toFixed(2) + '%' : '-') + '</div></div>' +
          '<div class="summary-item"><div class="summary-label">最大单日涨幅</div><div class="summary-value" style="color:var(--color-positive)">' + (stats.max_single_day_gain != null ? '+' + stats.max_single_day_gain.toFixed(2) + '%' : '-') + '</div></div>' +
          '<div class="summary-item"><div class="summary-label">最大单日跌幅</div><div class="summary-value" style="color:var(--color-negative)">' + (stats.max_single_day_loss != null ? stats.max_single_day_loss.toFixed(2) + '%' : '-') + '</div></div>' +
          '</div></div>';
      } else {
        html += '<div class="summary" style="text-align:center;color:var(--color-text-secondary)">暂无行情数据</div>';
      }
      app.innerHTML = html;
      notifySize();
      return;
    }

    // Build chart
    var title = tsCode + (days ? ' ' + days + '日K线' : ' K线');
    app.innerHTML = '<div class="header"><h2>' + title + '</h2>' +
      '<div class="sub">数据来源：Tushare Pro | ' + formatDate(items[0].trade_date) + ' ~ ' + formatDate(items[items.length - 1].trade_date) +
      ' | 共 ' + items.length + ' 个交易日</div></div>' +
      '<div id="chart-main"></div><div id="chart-vol"></div>';

    if (!window.echarts) { notifySize(); return; }

    var dates = [];
    var ohlc = [];
    var volumes = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      dates.push(formatDate(it.trade_date));
      ohlc.push([it.open, it.close, it.low, it.high]);
      volumes.push(it.vol || 0);
    }

    var ma5 = calcMA(items, 5);
    var ma10 = calcMA(items, 10);
    var ma20 = calcMA(items, 20);

    // Main candlestick chart
    var elMain = document.getElementById('chart-main');
    chartMain = echarts.init(elMain);
    chartMain.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: function(params) {
          if (!params || !params.length) return '';
          var p = params[0];
          var idx = p.dataIndex;
          var it = items[idx];
          var chgColor = (it.pct_chg || 0) >= 0 ? '#ef4444' : '#22c55e';
          var chgSign = (it.pct_chg || 0) >= 0 ? '+' : '';
          var lines = [
            '<b>' + formatDate(it.trade_date) + '</b>',
            '开: ' + it.open + '  高: ' + it.high,
            '低: ' + it.low + '  收: ' + it.close,
            '<span style="color:' + chgColor + '">涨跌幅: ' + chgSign + (it.pct_chg != null ? it.pct_chg.toFixed(2) : '-') + '%</span>',
            '成交量: ' + ((it.vol || 0) / 100).toFixed(0) + '手'
          ];
          return lines.join('<br>');
        }
      },
      grid: { left: 60, right: 20, top: 30, bottom: 60 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: '#999' } },
        axisLabel: { fontSize: 10 }
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitLine: { lineStyle: { color: '#eee', type: 'dashed' } },
        axisLabel: { fontSize: 10 }
      },
      dataZoom: [
        { type: 'slider', xAxisIndex: 0, start: 0, end: 100, bottom: 8, height: 20 }
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          data: ohlc,
          itemStyle: {
            color: '#ef4444',
            color0: '#22c55e',
            borderColor: '#ef4444',
            borderColor0: '#22c55e'
          }
        },
        {
          name: 'MA5',
          type: 'line',
          data: ma5,
          smooth: true,
          lineStyle: { width: 1, color: '#f59e0b' },
          symbol: 'none'
        },
        {
          name: 'MA10',
          type: 'line',
          data: ma10,
          smooth: true,
          lineStyle: { width: 1, color: '#3b82f6' },
          symbol: 'none'
        },
        {
          name: 'MA20',
          type: 'line',
          data: ma20,
          smooth: true,
          lineStyle: { width: 1, color: '#a855f7' },
          symbol: 'none'
        }
      ]
    });

    // Volume sub-chart
    var elVol = document.getElementById('chart-vol');
    chartVol = echarts.init(elVol);
    var volData = [];
    for (var vi = 0; vi < items.length; vi++) {
      volData.push({
        value: items[vi].vol || 0,
        itemStyle: { color: items[vi].close >= items[vi].open ? '#ef4444' : '#22c55e' }
      });
    }
    chartVol.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        formatter: function(params) {
          if (!params || !params.length) return '';
          var p = params[0];
          return dates[p.dataIndex] + '<br>成交量: ' + ((p.value || 0) / 100).toFixed(0) + '手';
        }
      },
      grid: { left: 60, right: 20, top: 10, bottom: 30 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLabel: { show: false },
        axisLine: { lineStyle: { color: '#999' } }
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitLine: { lineStyle: { color: '#eee', type: 'dashed' } },
        axisLabel: { fontSize: 10, formatter: function(v) { return (v / 100).toFixed(0); } }
      },
      dataZoom: [
        { type: 'slider', xAxisIndex: 0, start: 0, end: 100, show: false }
      ],
      series: [{
        name: '成交量',
        type: 'bar',
        data: volData,
        barMaxWidth: 8
      }]
    });

    // Link dataZoom between main and volume charts
    chartMain.on('dataZoom', function(evt) {
      var opt = chartMain.getOption();
      if (opt.dataZoom && opt.dataZoom[0]) {
        chartVol.dispatchAction({
          type: 'dataZoom',
          start: opt.dataZoom[0].start,
          end: opt.dataZoom[0].end
        });
      }
    });

    window.addEventListener('resize', function() {
      if (chartMain) chartMain.resize();
      if (chartVol) chartVol.resize();
    });

    notifySize();
  }

  function notifySize() {
    var h = document.documentElement.scrollHeight;
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed', params:{ height: h } }, '*');
  }
})();
</script>
</body>
</html>"""


MONEYFLOW_CHART_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>资金流向</title>
<style>
:root {
  --color-background-primary: light-dark(#ffffff, #1a1a1a);
  --color-background-secondary: light-dark(#f8f9fa, #222222);
  --color-text-primary: light-dark(#171717, #e5e5e5);
  --color-text-secondary: light-dark(#6b7280, #9ca3af);
  --color-border-primary: light-dark(#e5e5e5, #333333);
  --font-sans: system-ui, -apple-system, "PingFang SC", sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", monospace;
  --color-positive: #ef4444;
  --color-negative: #22c55e;
}
* { margin: 0; box-sizing: border-box; }
body {
  font-family: var(--font-sans);
  color: var(--color-text-primary);
  background: transparent;
  padding: 16px; line-height: 1.5;
}
.header { margin-bottom: 12px; }
.header h2 { font-size: 16px; font-weight: 600; }
.header .sub { font-size: 12px; color: var(--color-text-secondary); margin-top: 2px; }
#chart { width: 100%; height: 400px; }
.loading { text-align: center; padding: 48px 0; color: var(--color-text-secondary); font-size: 13px; }
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script>var module=undefined,exports=undefined,define=undefined;</script>
<script>/* ECHARTS_PLACEHOLDER */</script>
<script>
(function(){
  var myChart = null;

  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    switch (msg.method) {
      case 'ui/notifications/tool-result':
        var raw = msg.params;
        render(raw.structuredContent || parseContent(raw.content));
        break;
      case 'ui/notifications/host-context-changed':
        if (msg.params && msg.params.styles && msg.params.styles.variables)
          applyTheme(msg.params.styles.variables);
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

  function parseContent(c) {
    if (!c) return null;
    var arr = Array.isArray(c) ? c : [c];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }

  function applyTheme(vars) {
    var r = document.documentElement;
    for (var k in vars) if (vars[k]) r.style.setProperty('--' + k, vars[k]);
  }

  function formatDate(d) {
    if (!d) return '';
    var s = String(d);
    if (s.length === 8) return s.substring(0, 4) + '-' + s.substring(4, 6) + '-' + s.substring(6, 8);
    return s;
  }

  function toYi(v) {
    if (v == null) return 0;
    // Tushare moneyflow amounts are in thousand yuan (千元)
    // Convert to 亿: divide by 100000 (1亿 = 100000千元)
    return +(v / 100000).toFixed(4);
  }

  function render(raw) {
    if (!raw) return;
    var tsCode = raw.ts_code || '';
    var items = raw.data || [];
    if (!Array.isArray(items)) {
      if (raw.data && Array.isArray(raw.data)) {
        items = raw.data;
      } else if (raw.items && Array.isArray(raw.items)) {
        items = raw.items;
      } else {
        items = [];
      }
    }

    var app = document.getElementById('app');
    app.classList.remove('loading');

    if (!items.length) {
      app.innerHTML = '<div class="header"><h2>' + tsCode + ' 资金流向</h2></div>' +
        '<div style="text-align:center;padding:48px 0;color:var(--color-text-secondary)">暂无资金流向数据</div>';
      notifySize();
      return;
    }

    // Sort by trade_date ascending
    items.sort(function(a, b) {
      return String(a.trade_date || '').localeCompare(String(b.trade_date || ''));
    });

    app.innerHTML = '<div class="header"><h2>' + tsCode + ' 资金流向</h2>' +
      '<div class="sub">' + formatDate(items[0].trade_date) + ' ~ ' + formatDate(items[items.length - 1].trade_date) +
      ' | 共 ' + items.length + ' 个交易日 | 单位：亿元</div></div>' +
      '<div id="chart"></div>';

    if (!window.echarts) { notifySize(); return; }

    var dates = [];
    var netTotal = [];
    var netSm = [];
    var netMd = [];
    var netLg = [];
    var netElg = [];

    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      dates.push(formatDate(it.trade_date));

      var netVal = it.net_mf_amount;
      if (netVal == null) {
        netVal = (it.buy_sm_amount || 0) + (it.buy_md_amount || 0) +
                 (it.buy_lg_amount || 0) + (it.buy_elg_amount || 0) -
                 (it.sell_sm_amount || 0) - (it.sell_md_amount || 0) -
                 (it.sell_lg_amount || 0) - (it.sell_elg_amount || 0);
      }
      netTotal.push(toYi(netVal));
      netSm.push(toYi((it.buy_sm_amount || 0) - (it.sell_sm_amount || 0)));
      netMd.push(toYi((it.buy_md_amount || 0) - (it.sell_md_amount || 0)));
      netLg.push(toYi((it.buy_lg_amount || 0) - (it.sell_lg_amount || 0)));
      netElg.push(toYi((it.buy_elg_amount || 0) - (it.sell_elg_amount || 0)));
    }

    var el = document.getElementById('chart');
    myChart = echarts.init(el);
    myChart.setOption({
      animation: false,
      tooltip: {
        trigger: 'axis',
        formatter: function(params) {
          if (!params || !params.length) return '';
          var lines = ['<b>' + params[0].axisValue + '</b>'];
          for (var pi = 0; pi < params.length; pi++) {
            var p = params[pi];
            var v = p.value;
            var color = v >= 0 ? '#ef4444' : '#22c55e';
            lines.push('<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + p.color + ';margin-right:4px"></span>' +
              p.seriesName + ': <span style="color:' + color + '">' + (v >= 0 ? '+' : '') + v.toFixed(2) + '</span> 亿');
          }
          return lines.join('<br>');
        }
      },
      legend: {
        data: ['净流入', '散户净流入', '中户净流入', '大户净流入', '超大户净流入'],
        bottom: 0,
        textStyle: { fontSize: 11 }
      },
      grid: { left: 60, right: 20, top: 30, bottom: 80 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: '#999' } },
        axisLabel: { fontSize: 10, rotate: 30 }
      },
      yAxis: {
        type: 'value',
        name: '亿元',
        nameTextStyle: { fontSize: 11, color: '#999' },
        splitLine: { lineStyle: { color: '#eee', type: 'dashed' } },
        axisLabel: { fontSize: 10 }
      },
      dataZoom: [
        { type: 'slider', xAxisIndex: 0, start: 0, end: 100, bottom: 36, height: 20 }
      ],
      series: [
        {
          name: '净流入',
          type: 'line',
          data: netTotal,
          lineStyle: { width: 2, color: '#ef4444' },
          itemStyle: { color: '#ef4444' },
          symbol: 'circle',
          symbolSize: 4,
          areaStyle: {
            color: {
              type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: 'rgba(239,68,68,0.15)' },
                { offset: 1, color: 'rgba(239,68,68,0)' }
              ]
            }
          }
        },
        {
          name: '散户净流入',
          type: 'line',
          data: netSm,
          lineStyle: { width: 1, color: '#9ca3af' },
          itemStyle: { color: '#9ca3af' },
          symbol: 'none'
        },
        {
          name: '中户净流入',
          type: 'line',
          data: netMd,
          lineStyle: { width: 1, color: '#60a5fa' },
          itemStyle: { color: '#60a5fa' },
          symbol: 'none'
        },
        {
          name: '大户净流入',
          type: 'line',
          data: netLg,
          lineStyle: { width: 1, color: '#f59e0b' },
          itemStyle: { color: '#f59e0b' },
          symbol: 'none'
        },
        {
          name: '超大户净流入',
          type: 'line',
          data: netElg,
          lineStyle: { width: 1, color: '#a855f7' },
          itemStyle: { color: '#a855f7' },
          symbol: 'none'
        }
      ]
    });

    window.addEventListener('resize', function() {
      if (myChart) myChart.resize();
    });

    notifySize();
  }

  function notifySize() {
    var h = document.documentElement.scrollHeight;
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed', params:{ height: h } }, '*');
  }
})();
</script>
</body>
</html>"""


FUND_NAV_CHART_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>基金净值走势</title>
<style>
:root {
  --color-text-primary: light-dark(#171717, #e5e5e5);
  --color-text-secondary: light-dark(#6b7280, #9ca3af);
  --color-border-primary: light-dark(#e5e5e5, #333333);
  --color-card-bg: light-dark(#ffffff, #1f2937);
  --font-sans: system-ui, -apple-system, "PingFang SC", sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", monospace;
}
* { margin: 0; box-sizing: border-box; }
body { font-family: var(--font-sans); color: var(--color-text-primary); background: transparent; padding: 16px; }
.header { margin-bottom: 14px; }
.header h2 { font-size: 16px; font-weight: 600; }
.header .sub { margin-top: 4px; font-size: 12px; color: var(--color-text-secondary); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 14px; }
.card { border: 1px solid var(--color-border-primary); border-radius: 10px; padding: 12px; background: var(--color-card-bg); }
.card .label { font-size: 11px; color: var(--color-text-secondary); }
.card .value { font-size: 20px; font-family: var(--font-mono); font-weight: 600; margin-top: 4px; }
#chart { width: 100%; height: 420px; }
.loading { text-align: center; padding: 48px 0; font-size: 13px; color: var(--color-text-secondary); }
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script>var module=undefined,exports=undefined,define=undefined;</script>
<script>/* ECHARTS_PLACEHOLDER */</script>
<script>
(function(){
  var chart = null;

  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    if (msg.method === 'ui/notifications/tool-result') {
      var raw = msg.params;
      render(parsePayload(raw.structuredContent || parseContent(raw.content)));
    }
    if (msg.method === 'ui/notifications/host-context-changed' && msg.params && msg.params.styles && msg.params.styles.variables) {
      applyTheme(msg.params.styles.variables);
    }
    if (msg.id !== undefined && msg.method === 'ui/initialize') {
      window.parent.postMessage({ jsonrpc:'2.0', id: msg.id, result:{ protocolVersion:'2025-06-18', appCapabilities:{ availableDisplayModes:['inline','fullscreen'] } } }, '*');
      window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/initialized', params:{} }, '*');
    }
  });

  function parseContent(c) {
    if (!c) return null;
    var arr = Array.isArray(c) ? c : [c];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }

  function applyTheme(vars) {
    for (var k in vars) if (vars[k]) document.documentElement.style.setProperty('--' + k, vars[k]);
  }

  function sortByDate(items, field) {
    return (items || []).slice().sort(function(a, b) {
      return String(a[field] || '').localeCompare(String(b[field] || ''));
    });
  }

  function parsePayload(raw) {
    if (!raw) return null;
    if (raw.ui && raw.ui.kind === 'fund-nav-chart') return raw.ui;
    var data = sortByDate(raw.data || [], 'nav_date');
    var latest = data.length ? data[data.length - 1] : {};
    var series = [
      { name: '单位净值', field: 'unit_nav' },
      { name: '累计净值', field: 'accum_nav' }
    ];
    if (data.some(function(item){ return item.adj_nav != null && item.adj_nav !== 0; })) {
      series.push({ name: '复权净值', field: 'adj_nav' });
    }
    return {
      title: (raw.ts_code || '基金') + ' 净值走势',
      subtitle: data.length ? (data[0].nav_date + ' - ' + data[data.length - 1].nav_date + ' · ' + data.length + ' 条记录') : '暂无数据',
      data: data,
      xField: 'nav_date',
      series: series,
      stats: [
        { label: '最新日期', value: latest.nav_date || '-' },
        { label: '最新单位净值', value: latest.unit_nav != null ? String(latest.unit_nav) : '-' },
        { label: '最新累计净值', value: latest.accum_nav != null ? String(latest.accum_nav) : '-' }
      ]
    };
  }

  function render(payload) {
    if (!payload || !payload.data || !payload.data.length) {
      document.getElementById('app').innerHTML = '<div class="loading">无净值数据</div>';
      return;
    }
    var stats = payload.stats || [];
    var statHtml = '';
    for (var i = 0; i < stats.length; i++) {
      statHtml += '<div class="card"><div class="label">' + esc(stats[i].label) + '</div><div class="value">' + esc(stats[i].value) + '</div></div>';
    }
    document.getElementById('app').classList.remove('loading');
    document.getElementById('app').innerHTML =
      '<div class="header"><h2>' + esc(payload.title || '基金净值') + '</h2><div class="sub">' + esc(payload.subtitle || '') + '</div></div>' +
      '<div class="stats">' + statHtml + '</div>' +
      '<div id="chart"></div>';
    renderChart(payload);
    notifySize();
  }

  function renderChart(payload) {
    if (!window.echarts) return;
    var el = document.getElementById('chart');
    if (!el) return;
    if (chart) chart.dispose();
    chart = echarts.init(el);
    var dates = payload.data.map(function(item){ return item[payload.xField]; });
    var series = payload.series.map(function(cfg, idx){
      return {
        name: cfg.name,
        type: 'line',
        smooth: true,
        symbol: 'none',
        yAxisIndex: 0,
        lineStyle: { width: 2 },
        data: payload.data.map(function(item){ return item[cfg.field]; })
      };
    });
    chart.setOption({
      animation: false,
      color: ['#2563eb', '#ef4444', '#10b981'],
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 56, right: 20, top: 40, bottom: 60 },
      xAxis: { type: 'category', data: dates, boundaryGap: false, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', scale: true, axisLabel: { fontSize: 10 } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 16 }],
      series: series
    });
    window.addEventListener('resize', function(){ if (chart) chart.resize(); });
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"]/g, function(s){
      return ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' })[s];
    });
  }

  function notifySize() {
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed', params:{ height: document.documentElement.scrollHeight } }, '*');
  }
})();
</script>
</body>
</html>"""


SERIES_CHART_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>通用趋势图</title>
<style>
:root {
  --color-text-primary: light-dark(#171717, #e5e5e5);
  --color-text-secondary: light-dark(#6b7280, #9ca3af);
  --color-border-primary: light-dark(#e5e5e5, #333333);
  --color-card-bg: light-dark(#ffffff, #1f2937);
  --font-sans: system-ui, -apple-system, "PingFang SC", sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", monospace;
}
* { margin: 0; box-sizing: border-box; }
body { font-family: var(--font-sans); color: var(--color-text-primary); background: transparent; padding: 16px; }
.header h2 { font-size: 16px; font-weight: 600; }
.header .sub { margin-top: 4px; font-size: 12px; color: var(--color-text-secondary); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin: 14px 0; }
.card { border: 1px solid var(--color-border-primary); border-radius: 10px; padding: 12px; background: var(--color-card-bg); }
.card .label { font-size: 11px; color: var(--color-text-secondary); }
.card .value { font-size: 18px; font-family: var(--font-mono); font-weight: 600; margin-top: 4px; }
.card .note { margin-top: 4px; font-size: 11px; color: var(--color-text-secondary); }
.panel { border: 1px solid var(--color-border-primary); border-radius: 12px; padding: 12px; margin-top: 12px; }
.panel-title { font-size: 13px; font-weight: 600; }
.panel-note { margin-top: 2px; font-size: 11px; color: var(--color-text-secondary); }
.panel-chart { width: 100%; height: 300px; margin-top: 8px; }
.loading { text-align: center; padding: 48px 0; font-size: 13px; color: var(--color-text-secondary); }
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script>var module=undefined,exports=undefined,define=undefined;</script>
<script>/* ECHARTS_PLACEHOLDER */</script>
<script>
(function(){
  var charts = [];

  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    if (msg.method === 'ui/notifications/tool-result') {
      var raw = msg.params;
      render(parsePayload(raw.structuredContent || parseContent(raw.content)));
    }
    if (msg.method === 'ui/notifications/host-context-changed' && msg.params && msg.params.styles && msg.params.styles.variables) {
      applyTheme(msg.params.styles.variables);
    }
    if (msg.id !== undefined && msg.method === 'ui/initialize') {
      window.parent.postMessage({ jsonrpc:'2.0', id: msg.id, result:{ protocolVersion:'2025-06-18', appCapabilities:{ availableDisplayModes:['inline','fullscreen'] } } }, '*');
      window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/initialized', params:{} }, '*');
    }
  });

  function parseContent(c) {
    if (!c) return null;
    var arr = Array.isArray(c) ? c : [c];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }

  function parsePayload(raw) {
    if (!raw) return null;
    if (raw.ui && raw.ui.kind === 'series-chart') return raw.ui;
    return raw.kind === 'series-chart' ? raw : null;
  }

  function applyTheme(vars) {
    for (var k in vars) if (vars[k]) document.documentElement.style.setProperty('--' + k, vars[k]);
  }

  function render(payload) {
    if (!payload || !payload.panels || !payload.panels.length) {
      document.getElementById('app').innerHTML = '<div class="loading">缺少可视化配置</div>';
      return;
    }
    charts.forEach(function(chart){ try { chart.dispose(); } catch(e) {} });
    charts = [];
    var stats = payload.stats || [];
    var statsHtml = '';
    for (var i = 0; i < stats.length; i++) {
      statsHtml += '<div class="card"><div class="label">' + esc(stats[i].label) + '</div><div class="value">' + esc(stats[i].value) + '</div>' +
        (stats[i].note ? '<div class="note">' + esc(stats[i].note) + '</div>' : '') + '</div>';
    }
    var panelsHtml = '';
    for (var p = 0; p < payload.panels.length; p++) {
      panelsHtml += '<section class="panel"><div class="panel-title">' + esc(payload.panels[p].title || ('图表 ' + (p + 1))) + '</div>' +
        (payload.panels[p].note ? '<div class="panel-note">' + esc(payload.panels[p].note) + '</div>' : '') +
        '<div class="panel-chart" id="chart-' + p + '"></div></section>';
    }
    document.getElementById('app').classList.remove('loading');
    document.getElementById('app').innerHTML =
      '<div class="header"><h2>' + esc(payload.title || '趋势图') + '</h2><div class="sub">' + esc(payload.subtitle || '') + '</div></div>' +
      (statsHtml ? '<div class="stats">' + statsHtml + '</div>' : '') +
      panelsHtml;

    for (var i = 0; i < payload.panels.length; i++) renderPanel(payload.panels[i], i);
    notifySize();
  }

  function renderPanel(panel, index) {
    if (!window.echarts) return;
    var el = document.getElementById('chart-' + index);
    if (!el) return;
    var chart = echarts.init(el);
    charts.push(chart);

    var rows = panel.data || [];
    var xField = panel.xField || 'date';
    var xData = rows.map(function(item){ return item[xField]; });
    var yAxes = (panel.yAxes || [{ name: '数值' }]).map(function(axis) {
      return {
        type: 'value',
        scale: true,
        name: axis.name || '',
        axisLabel: {
          fontSize: 10,
          formatter: function(value) {
            if (axis.format === 'percent') return value + '%';
            return value;
          }
        }
      };
    });
    var series = (panel.series || []).map(function(cfg, idx) {
      var type = cfg.type || ((cfg.data && cfg.data.length === 1) ? 'bar' : 'line');
      var seriesObj = {
        name: cfg.name,
        type: type,
        smooth: type === 'line',
        symbol: type === 'line' ? 'none' : 'circle',
        yAxisIndex: cfg.yAxisIndex || 0,
        data: cfg.data || rows.map(function(item){ return item[cfg.field]; })
      };
      if (panel.threshold != null && idx === 0) {
        seriesObj.markLine = {
          symbol: 'none',
          lineStyle: { type: 'dashed', color: '#9ca3af' },
          data: [{ yAxis: panel.threshold }]
        };
      }
      return seriesObj;
    });
    chart.setOption({
      animation: false,
      color: ['#2563eb', '#ef4444', '#10b981', '#f59e0b', '#a855f7'],
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 56, right: 20, top: 36, bottom: 52 },
      xAxis: { type: 'category', data: xData, boundaryGap: false, axisLabel: { fontSize: 10 } },
      yAxis: yAxes,
      dataZoom: xData.length > 12 ? [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 10 }] : [],
      series: series
    });
    window.addEventListener('resize', function(){ chart.resize(); });
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"]/g, function(s){
      return ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' })[s];
    });
  }

  function notifySize() {
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed', params:{ height: document.documentElement.scrollHeight } }, '*');
  }
})();
</script>
</body>
</html>"""


CORRELATION_MATRIX_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>相关性矩阵</title>
<style>
:root {
  --color-text-primary: light-dark(#171717, #e5e5e5);
  --color-text-secondary: light-dark(#6b7280, #9ca3af);
  --color-border-primary: light-dark(#e5e5e5, #333333);
  --color-card-bg: light-dark(#ffffff, #1f2937);
  --font-sans: system-ui, -apple-system, "PingFang SC", sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", monospace;
}
* { margin: 0; box-sizing: border-box; }
body { font-family: var(--font-sans); color: var(--color-text-primary); background: transparent; padding: 16px; }
.header h2 { font-size: 16px; font-weight: 600; }
.header .sub { margin-top: 4px; font-size: 12px; color: var(--color-text-secondary); }
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin: 14px 0; }
.card { border: 1px solid var(--color-border-primary); border-radius: 10px; padding: 12px; background: var(--color-card-bg); }
.card .label { font-size: 11px; color: var(--color-text-secondary); }
.card .value { font-size: 16px; font-weight: 600; margin-top: 4px; }
.card .note { font-size: 11px; color: var(--color-text-secondary); margin-top: 4px; }
.panel { border: 1px solid var(--color-border-primary); border-radius: 12px; padding: 12px; margin-top: 12px; }
.panel-title { font-size: 13px; font-weight: 600; }
.panel-chart { width: 100%; margin-top: 8px; }
#heatmap { height: 360px; }
#timeseries { height: 300px; }
.loading { text-align: center; padding: 48px 0; font-size: 13px; color: var(--color-text-secondary); }
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script>var module=undefined,exports=undefined,define=undefined;</script>
<script>/* ECHARTS_PLACEHOLDER */</script>
<script>
(function(){
  var heatmapChart = null, lineChart = null;

  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    if (msg.method === 'ui/notifications/tool-result') {
      var raw = msg.params;
      render(parsePayload(raw.structuredContent || parseContent(raw.content)));
    }
    if (msg.method === 'ui/notifications/host-context-changed' && msg.params && msg.params.styles && msg.params.styles.variables) {
      applyTheme(msg.params.styles.variables);
    }
    if (msg.id !== undefined && msg.method === 'ui/initialize') {
      window.parent.postMessage({ jsonrpc:'2.0', id: msg.id, result:{ protocolVersion:'2025-06-18', appCapabilities:{ availableDisplayModes:['inline','fullscreen'] } } }, '*');
      window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/initialized', params:{} }, '*');
    }
  });

  function parseContent(c) {
    if (!c) return null;
    var arr = Array.isArray(c) ? c : [c];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }

  function parsePayload(raw) {
    if (!raw) return null;
    if (raw.ui && raw.ui.kind === 'correlation-matrix') return raw.ui;
    return raw.kind === 'correlation-matrix' ? raw : {
      title: '价格相关性矩阵',
      subtitle: '',
      labels: Object.keys(raw.correlation_matrix || {}),
      stockNames: raw.stock_names || {},
      correlationMatrix: raw.correlation_matrix || {},
      timeSeries: raw.time_series || {},
      stats: []
    };
  }

  function applyTheme(vars) {
    for (var k in vars) if (vars[k]) document.documentElement.style.setProperty('--' + k, vars[k]);
  }

  function displayLabel(code, names) {
    var name = names && names[code];
    return name && name !== code ? (name + '\n' + code) : code;
  }

  function render(payload) {
    if (!payload || !payload.labels || !payload.labels.length) {
      document.getElementById('app').innerHTML = '<div class="loading">缺少相关性数据</div>';
      return;
    }
    var stats = payload.stats || [];
    var statsHtml = '';
    for (var i = 0; i < stats.length; i++) {
      statsHtml += '<div class="card"><div class="label">' + esc(stats[i].label) + '</div><div class="value">' + esc(stats[i].value) + '</div>' +
        (stats[i].note ? '<div class="note">' + esc(stats[i].note) + '</div>' : '') + '</div>';
    }
    document.getElementById('app').classList.remove('loading');
    document.getElementById('app').innerHTML =
      '<div class="header"><h2>' + esc(payload.title || '相关性矩阵') + '</h2><div class="sub">' + esc(payload.subtitle || '') + '</div></div>' +
      (statsHtml ? '<div class="stats">' + statsHtml + '</div>' : '') +
      '<section class="panel"><div class="panel-title">相关性热力图</div><div class="panel-chart" id="heatmap"></div></section>' +
      '<section class="panel"><div class="panel-title">归一化价格走势</div><div class="panel-chart" id="timeseries"></div></section>';
    renderHeatmap(payload);
    renderLines(payload);
    notifySize();
  }

  function renderHeatmap(payload) {
    if (!window.echarts) return;
    if (heatmapChart) heatmapChart.dispose();
    heatmapChart = echarts.init(document.getElementById('heatmap'));
    var labels = payload.labels;
    var axisLabels = labels.map(function(code){ return displayLabel(code, payload.stockNames); });
    var data = [];
    for (var y = 0; y < labels.length; y++) {
      for (var x = 0; x < labels.length; x++) {
        var value = payload.correlationMatrix[labels[y]] ? payload.correlationMatrix[labels[y]][labels[x]] : null;
        data.push([x, y, value == null ? null : Number(value)]);
      }
    }
    heatmapChart.setOption({
      animation: false,
      tooltip: {
        formatter: function(params) {
          return axisLabels[params.data[1]] + '<br>' + axisLabels[params.data[0]] + '<br>相关系数: ' + params.data[2];
        }
      },
      grid: { left: 90, right: 24, top: 20, bottom: 70 },
      xAxis: { type: 'category', data: axisLabels, splitArea: { show: true }, axisLabel: { interval: 0, fontSize: 10 } },
      yAxis: { type: 'category', data: axisLabels, splitArea: { show: true }, axisLabel: { interval: 0, fontSize: 10 } },
      visualMap: { min: -1, max: 1, calculable: false, orient: 'horizontal', left: 'center', bottom: 8, inRange: { color: ['#22c55e', '#f8fafc', '#ef4444'] } },
      series: [{
        type: 'heatmap',
        data: data,
        label: { show: true, formatter: function(params){ return params.data[2] == null ? '-' : Number(params.data[2]).toFixed(3); }, fontSize: 10 }
      }]
    });
    window.addEventListener('resize', function(){ if (heatmapChart) heatmapChart.resize(); });
  }

  function renderLines(payload) {
    if (!window.echarts) return;
    if (lineChart) lineChart.dispose();
    lineChart = echarts.init(document.getElementById('timeseries'));
    var codes = Object.keys(payload.timeSeries || {});
    if (!codes.length) return;
    var dateMap = {};
    codes.forEach(function(code){
      (payload.timeSeries[code] || []).forEach(function(item){ dateMap[item.date] = true; });
    });
    var dates = Object.keys(dateMap).sort();
    var series = codes.map(function(code){
      var points = payload.timeSeries[code] || [];
      var base = points.length && points[0].close ? points[0].close : 1;
      var lookup = {};
      for (var i = 0; i < points.length; i++) {
        lookup[points[i].date] = Number((points[i].close / base * 100).toFixed(2));
      }
      return {
        name: displayLabel(code, payload.stockNames),
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: dates.map(function(date){ return lookup[date] != null ? lookup[date] : null; })
      };
    });
    lineChart.setOption({
      animation: false,
      color: ['#2563eb', '#ef4444', '#10b981', '#f59e0b', '#a855f7'],
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 56, right: 20, top: 36, bottom: 52 },
      xAxis: { type: 'category', data: dates, boundaryGap: false, axisLabel: { fontSize: 10 } },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}' }, name: '基准=100' },
      dataZoom: dates.length > 12 ? [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 10 }] : [],
      series: series
    });
    window.addEventListener('resize', function(){ if (lineChart) lineChart.resize(); });
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"]/g, function(s){
      return ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' })[s];
    });
  }

  function notifySize() {
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed', params:{ height: document.documentElement.scrollHeight } }, '*');
  }
})();
</script>
</body>
</html>"""


FINANCIAL_METRICS_CHART_HTML = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>财务指标趋势</title>
<style>
:root {
  --color-text-primary: light-dark(#171717, #e5e5e5);
  --color-text-secondary: light-dark(#6b7280, #9ca3af);
  --color-border-primary: light-dark(#e5e5e5, #333333);
  --color-card-bg: light-dark(#ffffff, #1f2937);
  --font-sans: system-ui, -apple-system, "PingFang SC", sans-serif;
  --font-mono: "SF Mono", "JetBrains Mono", monospace;
}
* { margin: 0; box-sizing: border-box; }
body { font-family: var(--font-sans); color: var(--color-text-primary); background: transparent; padding: 16px; }
.header h2 { font-size: 16px; font-weight: 600; }
.header .sub { margin-top: 4px; font-size: 12px; color: var(--color-text-secondary); }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 14px 0; }
.card { border: 1px solid var(--color-border-primary); border-radius: 10px; padding: 12px; background: var(--color-card-bg); }
.card .label { font-size: 11px; color: var(--color-text-secondary); }
.card .value { font-size: 18px; font-family: var(--font-mono); font-weight: 600; margin-top: 4px; }
.card .note { font-size: 11px; color: var(--color-text-secondary); margin-top: 4px; }
.panel { border: 1px solid var(--color-border-primary); border-radius: 12px; padding: 12px; margin-top: 12px; }
.panel-title { font-size: 13px; font-weight: 600; }
.panel-note { font-size: 11px; color: var(--color-text-secondary); margin-top: 2px; }
.panel-chart { width: 100%; height: 240px; margin-top: 8px; }
.loading { text-align: center; padding: 48px 0; font-size: 13px; color: var(--color-text-secondary); }
</style>
</head>
<body>
<div id="app" class="loading">等待数据…</div>
<script>var module=undefined,exports=undefined,define=undefined;</script>
<script>/* ECHARTS_PLACEHOLDER */</script>
<script>
(function(){
  var charts = [];

  window.addEventListener('message', function(e) {
    var msg = e.data;
    if (!msg || !msg.jsonrpc) return;
    if (msg.method === 'ui/notifications/tool-result') {
      var raw = msg.params;
      render(parsePayload(raw.structuredContent || parseContent(raw.content)));
    }
    if (msg.method === 'ui/notifications/host-context-changed' && msg.params && msg.params.styles && msg.params.styles.variables) {
      applyTheme(msg.params.styles.variables);
    }
    if (msg.id !== undefined && msg.method === 'ui/initialize') {
      window.parent.postMessage({ jsonrpc:'2.0', id: msg.id, result:{ protocolVersion:'2025-06-18', appCapabilities:{ availableDisplayModes:['inline','fullscreen'] } } }, '*');
      window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/initialized', params:{} }, '*');
    }
  });

  function parseContent(c) {
    if (!c) return null;
    var arr = Array.isArray(c) ? c : [c];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].type === 'text') try { return JSON.parse(arr[i].text); } catch(e) {}
    }
    return null;
  }

  function parsePayload(raw) {
    if (!raw) return null;
    if (raw.ui && raw.ui.kind === 'financial-metrics-chart') return raw.ui;
    return raw.kind === 'financial-metrics-chart' ? raw : null;
  }

  function applyTheme(vars) {
    for (var k in vars) if (vars[k]) document.documentElement.style.setProperty('--' + k, vars[k]);
  }

  function render(payload) {
    if (!payload || !payload.panels || !payload.panels.length) {
      document.getElementById('app').innerHTML = '<div class="loading">缺少财务序列数据</div>';
      return;
    }
    charts.forEach(function(chart){ try { chart.dispose(); } catch(e) {} });
    charts = [];
    var cards = payload.cards || [];
    var cardsHtml = '';
    for (var i = 0; i < cards.length; i++) {
      cardsHtml += '<div class="card"><div class="label">' + esc(cards[i].label) + '</div><div class="value">' + esc(cards[i].value) + '</div>' +
        (cards[i].note ? '<div class="note">' + esc(cards[i].note) + '</div>' : '') + '</div>';
    }
    var panelsHtml = '';
    for (var p = 0; p < payload.panels.length; p++) {
      panelsHtml += '<section class="panel"><div class="panel-title">' + esc(payload.panels[p].title || ('指标 ' + (p + 1))) + '</div>' +
        (payload.panels[p].note ? '<div class="panel-note">' + esc(payload.panels[p].note) + '</div>' : '') +
        '<div class="panel-chart" id="metric-chart-' + p + '"></div></section>';
    }
    document.getElementById('app').classList.remove('loading');
    document.getElementById('app').innerHTML =
      '<div class="header"><h2>' + esc(payload.title || '财务指标趋势') + '</h2><div class="sub">' + esc(payload.subtitle || '') + '</div></div>' +
      (cardsHtml ? '<div class="cards">' + cardsHtml + '</div>' : '') +
      panelsHtml;
    for (var i = 0; i < payload.panels.length; i++) renderPanel(payload.panels[i], i);
    notifySize();
  }

  function renderPanel(panel, index) {
    if (!window.echarts) return;
    var el = document.getElementById('metric-chart-' + index);
    if (!el) return;
    var chart = echarts.init(el);
    charts.push(chart);
    var categories = panel.categories || [];
    var series = (panel.series || []).map(function(cfg) {
      var type = cfg.type || (cfg.data && cfg.data.length === 1 ? 'bar' : 'line');
      return {
        name: cfg.name,
        type: type,
        smooth: type === 'line',
        symbol: type === 'line' ? 'none' : 'circle',
        data: cfg.data || []
      };
    });
    var yAxis = panel.yAxis || { name: '数值' };
    chart.setOption({
      animation: false,
      color: ['#2563eb'],
      tooltip: { trigger: 'axis' },
      grid: { left: 56, right: 20, top: 24, bottom: 42 },
      xAxis: { type: 'category', data: categories, boundaryGap: false, axisLabel: { fontSize: 10 } },
      yAxis: {
        type: 'value',
        scale: true,
        name: yAxis.name || '',
        axisLabel: {
          formatter: function(value) {
            if (yAxis.format === 'percent') return value + '%';
            return value;
          }
        }
      },
      series: series
    });
    window.addEventListener('resize', function(){ chart.resize(); });
  }

  function esc(value) {
    return String(value == null ? '' : value).replace(/[&<>"]/g, function(s){
      return ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' })[s];
    });
  }

  function notifySize() {
    window.parent.postMessage({ jsonrpc:'2.0', method:'ui/notifications/size-changed', params:{ height: document.documentElement.scrollHeight } }, '*');
  }
})();
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────
# 资源注册
# ─────────────────────────────────────────────────────────

def register_ui_app_resources(mcp: FastMCP):
    """注册 MCP Apps ui:// 交互式 HTML 资源"""

    @mcp.resource(
        "ui://findata/market-dashboard",
        name="市场概况仪表板",
        description="A股市场整体涨跌、成交、涨停跌停统计的交互式仪表板（ECharts）",
        mime_type="text/html",
        meta={
            "ui": {
                "profile": "mcp-app",
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def market_dashboard_resource() -> str:
        return MARKET_DASHBOARD_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)

    @mcp.resource(
        "ui://tushare/macro-panel",
        name="宏观经济面板",
        description="GDP、CPI、PMI、M2、LPR 等宏观指标的交互式面板",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def macro_panel_resource() -> str:
        return MACRO_PANEL_HTML

    @mcp.resource(
        "ui://tushare/data-table",
        name="数据表格",
        description="可排序、可筛选、可导出 CSV 的通用交互式数据表格",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def data_table_resource() -> str:
        return DATA_TABLE_HTML

    @mcp.resource(
        "ui://findata/macro-panel",
        name="宏观经济面板（findata）",
        description="findata 命名空间下的宏观经济指标面板",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def macro_panel_resource_findata() -> str:
        return MACRO_PANEL_HTML

    @mcp.resource(
        "ui://findata/data-table",
        name="数据表格（findata）",
        description="findata 命名空间下的通用交互式数据表格",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def data_table_resource_findata() -> str:
        return DATA_TABLE_HTML

    @mcp.resource(
        "ui://findata/kline-chart",
        name="K线图",
        description="股票K线图（OHLC+成交量+均线），支持缩放",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def candlestick_chart_resource() -> str:
        return CANDLESTICK_CHART_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)

    @mcp.resource(
        "ui://findata/moneyflow-chart",
        name="资金流向图",
        description="个股资金流向多线折线图",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def moneyflow_chart_resource() -> str:
        return MONEYFLOW_CHART_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)

    @mcp.resource(
        "ui://findata/fund-nav-chart",
        name="基金净值图",
        description="基金单位净值、累计净值、复权净值走势图",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def fund_nav_chart_resource() -> str:
        return FUND_NAV_CHART_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)

    @mcp.resource(
        "ui://findata/correlation-matrix",
        name="相关性矩阵",
        description="多资产相关性热力图和归一化价格走势",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def correlation_matrix_resource() -> str:
        return CORRELATION_MATRIX_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)

    @mcp.resource(
        "ui://findata/series-chart",
        name="通用趋势图",
        description="适用于宏观数据、指数估值等多面板时间序列图",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def series_chart_resource() -> str:
        return SERIES_CHART_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)

    @mcp.resource(
        "ui://findata/financial-metrics-chart",
        name="财务指标趋势图",
        description="财务指标摘要卡片与多指标趋势图",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def financial_metrics_chart_resource() -> str:
        return FINANCIAL_METRICS_CHART_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)



    @mcp.resource(
        "ui://tushare/market-dashboard",
        name="市场概况仪表板（兼容别名）",
        description="兼容旧 ui://tushare 命名空间，内容同 ui://findata/market-dashboard",
        mime_type="text/html",
        meta={
            "ui": {
                "profile": "mcp-app",
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def market_dashboard_resource_legacy() -> str:
        return MARKET_DASHBOARD_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)

    @mcp.resource(
        "ui://tushare/kline-chart",
        name="K线图（兼容别名）",
        description="兼容旧 ui://tushare 命名空间，内容同 ui://findata/kline-chart",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def candlestick_chart_resource_legacy() -> str:
        return CANDLESTICK_CHART_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)

    @mcp.resource(
        "ui://tushare/moneyflow-chart",
        name="资金流向图（兼容别名）",
        description="兼容旧 ui://tushare 命名空间，内容同 ui://findata/moneyflow-chart",
        mime_type="text/html",
        meta={
            "ui": {
                "csp": {
                    "connectDomains": [],
                    "resourceDomains": []
                },
                "prefersBorder": True
            }
        }
    )
    def moneyflow_chart_resource_legacy() -> str:
        return MONEYFLOW_CHART_HTML.replace("/* ECHARTS_PLACEHOLDER */", _ECHARTS_JS)

    logger.info("✅ Registered 14 ui:// MCP App resources (9 findata + 5 tushare aliases/shared)")
