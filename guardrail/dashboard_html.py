"""The /dashboard page: a live, judge-facing view of the guardrail's state.

Deliberately dependency-free (no CDN, no build step) so it works the
moment the proxy is running, even offline. Polls the proxy's own JSON
endpoints every 2 seconds.
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Agentic Trading Guardrail — Live Status</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #0b0f14; color: #e6edf3; margin: 0; padding: 24px; }
  h1 { font-size: 20px; font-weight: 600; margin: 0 0 4px; }
  .sub { color: #8b949e; font-size: 13px; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
  .card .label { font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.04em; }
  .card .value { font-size: 28px; font-weight: 600; margin-top: 4px; }
  .status-ok { color: #3fb950; }
  .status-bad { color: #f85149; }
  .status-warn { color: #d29922; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: #8b949e; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #30363d; }
  td { padding: 6px 8px; border-bottom: 1px solid #21262d; vertical-align: top; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }
  .pill-allowed { background: rgba(63,185,80,0.15); color: #3fb950; }
  .pill-blocked { background: rgba(248,81,73,0.15); color: #f85149; }
  .checks { color: #8b949e; font-size: 12px; }
  .checks .fail { color: #f85149; }
  .section-title { font-size: 14px; font-weight: 600; margin: 24px 0 8px; }
  .rejections { font-size: 13px; }
  .rejections div { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #21262d; }
</style>
</head>
<body>
  <h1>Agentic Trading Guardrail</h1>
  <div class="sub">Live status — updates every 2s</div>

  <div class="grid">
    <div class="card"><div class="label">Kill switch</div><div class="value" id="kill-switch">—</div></div>
    <div class="card"><div class="label">Circuit breaker</div><div class="value" id="breaker">—</div></div>
    <div class="card"><div class="label">Orders received</div><div class="value" id="total">—</div></div>
    <div class="card"><div class="label">Blocked</div><div class="value" id="blocked">—</div></div>
  </div>

  <div class="section-title">Blocks by check</div>
  <div class="rejections" id="rejections">—</div>

  <div class="section-title">Recent decisions</div>
  <table>
    <thead><tr><th>Result</th><th>Symbol</th><th>Agent</th><th>Checks</th></tr></thead>
    <tbody id="decisions"></tbody>
  </table>

<script>
async function refresh() {
  try {
    const [stats, breaker, killSwitch, decisions] = await Promise.all([
      fetch('/stats').then(r => r.json()),
      fetch('/breaker/status').then(r => r.json()),
      fetch('/kill-switch/status').then(r => r.json()),
      fetch('/decisions?limit=15').then(r => r.json()),
    ]);

    document.getElementById('total').textContent = stats.total_orders;
    document.getElementById('blocked').textContent = stats.total_blocked;

    const ksEl = document.getElementById('kill-switch');
    ksEl.textContent = killSwitch.engaged ? 'ENGAGED' : 'clear';
    ksEl.className = 'value ' + (killSwitch.engaged ? 'status-bad' : 'status-ok');

    const brEl = document.getElementById('breaker');
    brEl.textContent = breaker.tripped ? 'TRIPPED' : 'clear';
    brEl.className = 'value ' + (breaker.tripped ? 'status-bad' : 'status-ok');

    const rejEl = document.getElementById('rejections');
    const entries = Object.entries(stats.rejections_by_check || {});
    rejEl.innerHTML = entries.length
      ? entries.map(([k, v]) => `<div><span>${k}</span><span>${v}</span></div>`).join('')
      : '<div style="color:#8b949e">No blocks yet</div>';

    const tbody = document.getElementById('decisions');
    tbody.innerHTML = decisions.map(d => {
      const pillClass = d.allowed ? 'pill-allowed' : 'pill-blocked';
      const pillText = d.allowed ? 'ALLOWED' : 'BLOCKED';
      const checksText = d.checks.map(c =>
        c.status === 'REJECT' ? `<span class="fail">${c.check}✗</span>` : `${c.check}✓`
      ).join(' ');
      return `<tr>
        <td><span class="pill ${pillClass}">${pillText}</span></td>
        <td>${d.symbol ?? '—'} ${d.side ?? ''} ${d.quantity ?? ''}</td>
        <td>${d.agent_id ?? '—'}</td>
        <td class="checks">${checksText}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="4" style="color:#8b949e">No orders yet</td></tr>';
  } catch (e) {
    console.error('dashboard refresh failed', e);
  }
}
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""
