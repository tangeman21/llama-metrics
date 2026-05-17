#!/usr/bin/env python3
"""llama-metrics dashboard — tokens, power, energy with time-series graphs.
Reads state files + live metrics, serves a live-updating dashboard on port 8888.
"""

import http.server
import json
import os
import urllib.request
from datetime import datetime, timezone

TOKENS_FILE = os.path.expanduser("~/.hermes/llama-tokens.json")
ENERGY_FILE = os.path.expanduser("~/.hermes/llama-energy.json")
SNAPSHOT_DB = os.path.expanduser("~/.hermes/llama-snapshots.db")
LLAMA_URL = "http://localhost:8018/metrics"

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>llama-metrics</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0d1117; color: #c9d1d9; padding: 24px;
  }
  h1 { font-size: 1.5rem; color: #58a6ff; margin-bottom: 4px; }
  .subtitle { color: #8b949e; font-size: 0.85rem; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px;
  }
  .card h2 { font-size: 0.8rem; text-transform: uppercase; color: #8b949e; letter-spacing: 0.05em; margin-bottom: 12px; }
  .metric { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #21262d; }
  .metric:last-child { border-bottom: none; }
  .metric .label { color: #8b949e; font-size: 0.9rem; }
  .metric .value { color: #c9d1d9; font-weight: 600; font-variant-numeric: tabular-nums; }
  .big { font-size: 2rem; font-weight: 700; }
  .big .unit { font-size: 1rem; color: #8b949e; font-weight: 400; }
  .power-green { color: #3fb950; }
  .power-yellow { color: #d29922; }
  .power-red { color: #f85149; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }
  .badge-session { background: #1f6feb33; color: #58a6ff; }
  .badge-cumulative { background: #23863633; color: #3fb950; }
  .chart-card { margin-bottom: 24px; }
  .chart-card canvas { max-height: 280px; }
  .range-selector { display: flex; gap: 4px; margin-bottom: 12px; }
  .range-btn {
    background: #21262d; border: 1px solid #30363d; color: #8b949e; padding: 4px 12px;
    border-radius: 6px; cursor: pointer; font-size: 0.8rem;
  }
  .range-btn.active { background: #1f6feb; color: #fff; border-color: #1f6feb; }
  .range-btn:hover { background: #30363d; }
  #status { font-size: 0.75rem; color: #8b949e; margin-top: 16px; }
  #refresh { cursor: pointer; color: #58a6ff; text-decoration: underline; }
  .live-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
  .live-dot.ok { background: #3fb950; }
  .live-dot.err { background: #f85149; }
  .section-label { font-size: 0.7rem; color: #484f58; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; margin-top: 4px; }
</style>
</head>
<body>
<h1>llama-metrics</h1>
<div class="subtitle">Real-time token &amp; energy dashboard</div>

<!-- Top row: tokens + power + energy -->
<div class="grid">
  <div class="card">
    <h2>Tokens</h2>
    <div class="section-label">Session (this run)</div>
    <div class="metric"><span class="label">Prompt tokens</span><span class="value" id="session-prompt">—</span></div>
    <div class="metric"><span class="label">Output tokens</span><span class="value" id="session-output">—</span></div>
    <div class="metric"><span class="label">Session total</span><span class="value big" id="session-total">—</span></div>
    <div class="section-label" style="margin-top:12px;">All-time cumulative</div>
    <div class="metric"><span class="label">Cumulative total</span><span class="value big" id="cumulative">—</span></div>
    <div class="metric"><span class="label">Context max</span><span class="value" id="ctx-max">—</span></div>
    <div class="metric"><span class="label">Active requests</span><span class="value" id="requests">—</span></div>
  </div>

  <div class="card">
    <h2>GPU Power</h2>
    <div class="metric"><span class="label">AMD (ROCm)</span><span class="value" id="amd-power">—</span></div>
    <div class="metric"><span class="label">NVIDIA</span><span class="value" id="nvidia-power">—</span></div>
    <div class="metric"><span class="label">Total GPU</span><span class="value big" id="total-power">—</span></div>
    <div class="metric"><span class="label">CPU</span><span class="value" id="cpu-power">—</span></div>
  </div>

  <div class="card">
    <h2>Energy</h2>
    <div class="metric"><span class="label">All-time energy</span><span class="value big" id="cum-wh">—</span></div>
    <div class="metric"><span class="label">Energy / 1M tokens</span><span class="value" id="wh-per-m">—</span></div>
    <div class="metric"><span class="label">Avg power</span><span class="value" id="avg-power">—</span></div>
  </div>
</div>

<!-- Line graphs -->
<div class="grid">
  <div class="card chart-card">
    <h2>Tokens Over Time</h2>
    <div class="range-selector">
      <button class="range-btn active" data-hours="1">1h</button>
      <button class="range-btn" data-hours="6">6h</button>
      <button class="range-btn" data-hours="24">24h</button>
      <button class="range-btn" data-hours="168">7d</button>
    </div>
    <canvas id="tokens-chart"></canvas>
  </div>
  <div class="card chart-card">
    <h2>Cumulative Tokens &amp; Energy</h2>
    <div class="range-selector">
      <button class="range-btn active" data-hours="1">1h</button>
      <button class="range-btn" data-hours="6">6h</button>
      <button class="range-btn" data-hours="24">24h</button>
      <button class="range-btn" data-hours="168">7d</button>
    </div>
    <canvas id="cumulative-chart"></canvas>
  </div>
</div>

<div class="grid">
  <div class="card chart-card">
    <h2>Power Draw Over Time</h2>
    <div class="range-selector">
      <button class="range-btn active" data-hours="1">1h</button>
      <button class="range-btn" data-hours="6">6h</button>
      <button class="range-btn" data-hours="24">24h</button>
      <button class="range-btn" data-hours="168">7d</button>
    </div>
    <canvas id="power-chart"></canvas>
  </div>
  <div class="card chart-card">
    <h2>Energy Over Time</h2>
    <div class="range-selector">
      <button class="range-btn active" data-hours="1">1h</button>
      <button class="range-btn" data-hours="6">6h</button>
      <button class="range-btn" data-hours="24">24h</button>
      <button class="range-btn" data-hours="168">7d</button>
    </div>
    <canvas id="energy-chart"></canvas>
  </div>
</div>

<div id="status"><span class="live-dot" id="dot"></span><span id="status-text">Loading...</span> · <span id="refresh">Refresh now</span></div>

<script>
// --- Chart instances ---
let tokensChart, cumulativeChart, powerChart, energyChart;
let currentRange = { tokens: 1, cumulative: 1, power: 1, energy: 1 };

function initCharts() {
  const chartOpts = (yLabel) => ({
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { color: '#8b949e', font: { size: 11 } } },
      tooltip: { backgroundColor: '#1c2128', titleColor: '#c9d1d9', bodyColor: '#c9d1d9', borderColor: '#30363d', borderWidth: 1 }
    },
    scales: {
      x: { type: 'time', grid: { color: '#21262d' }, ticks: { color: '#8b949e', maxTicksLimit: 8 } },
      y: { grid: { color: '#21262d' }, ticks: { color: '#8b949e' }, title: { display: !!yLabel, text: yLabel, color: '#8b949e' } }
    }
  });

  // Tokens chart
  const tCtx = document.getElementById('tokens-chart').getContext('2d');
  tokensChart = new Chart(tCtx, {
    type: 'line',
    data: { datasets: [
      { label: 'Prompt tokens', borderColor: '#58a6ff', backgroundColor: '#58a6ff33', fill: true, tension: 0.3, pointRadius: 0 },
      { label: 'Output tokens', borderColor: '#3fb950', backgroundColor: '#3fb95033', fill: true, tension: 0.3, pointRadius: 0 }
    ]},
    options: chartOpts('tokens')
  });

  // Cumulative chart
  const cCtx = document.getElementById('cumulative-chart').getContext('2d');
  cumulativeChart = new Chart(cCtx, {
    type: 'line',
    data: { datasets: [
      { label: 'Cumulative tokens', borderColor: '#58a6ff', backgroundColor: '#58a6ff22', fill: true, tension: 0.1, pointRadius: 0, yAxisID: 'y' },
      { label: 'Cumulative Wh', borderColor: '#d29922', backgroundColor: '#d2992222', fill: true, tension: 0.1, pointRadius: 0, yAxisID: 'y1' }
    ]},
    options: {
      ...chartOpts(null),
      scales: {
        x: { type: 'time', grid: { color: '#21262d' }, ticks: { color: '#8b949e', maxTicksLimit: 8 } },
        y: { position: 'left', grid: { color: '#21262d' }, ticks: { color: '#8b949e' }, title: { display: true, text: 'Tokens', color: '#8b949e' } },
        y1: { position: 'right', grid: { drawOnChartArea: false }, ticks: { color: '#d29922' }, title: { display: true, text: 'Wh', color: '#d2949e' } }
      }
    }
  });

  // Power chart
  const pCtx = document.getElementById('power-chart').getContext('2d');
  powerChart = new Chart(pCtx, {
    type: 'line',
    data: { datasets: [
      { label: 'AMD GPU', borderColor: '#f85149', tension: 0.3, pointRadius: 0 },
      { label: 'NVIDIA GPU', borderColor: '#d29922', tension: 0.3, pointRadius: 0 },
      { label: 'Total', borderColor: '#c9d1d9', borderDash: [5,5], tension: 0.3, pointRadius: 0 }
    ]},
    options: chartOpts('Watts')
  });

  // Energy chart
  const eCtx = document.getElementById('energy-chart').getContext('2d');
  energyChart = new Chart(eCtx, {
    type: 'line',
    data: { datasets: [
      { label: 'Cumulative Wh', borderColor: '#d29922', backgroundColor: '#d2992222', fill: true, tension: 0.1, pointRadius: 0 }
    ]},
    options: chartOpts('Wh')
  });
}

// --- Range buttons ---
document.querySelectorAll('.range-selector').forEach(selector => {
  const chartName = selector.closest('.card').querySelector('canvas').id.replace('-chart', '');
  selector.querySelectorAll('.range-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      selector.querySelectorAll('.range-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentRange[chartName] = parseInt(btn.dataset.hours);
      updateCharts();
    });
  });
});

function formatNum(n) {
  if (n == null) return '—';
  return n.toLocaleString();
}

function powerClass(w) {
  if (w == null) return '';
  if (w < 100) return 'power-green';
  if (w < 250) return 'power-yellow';
  return 'power-red';
}

async function fetchData() {
  const dot = document.getElementById('dot');
  const status = document.getElementById('status-text');
  try {
    const [tokens, energy, live, snapshots] = await Promise.all([
      fetch('/api/tokens').then(r => r.json()),
      fetch('/api/energy').then(r => r.json()),
      fetch('/api/live').then(r => r.json()),
      fetch('/api/snapshots').then(r => r.json())
    ]);
    dot.className = 'live-dot ok';
    status.textContent = 'Live · Updated ' + new Date().toLocaleTimeString();

    // Session tokens (from live llama-server)
    document.getElementById('session-prompt').textContent = formatNum(live.prompt_tokens ?? null);
    document.getElementById('session-output').textContent = formatNum(live.predicted_tokens ?? null);
    const sessionTotal = (live.prompt_tokens ?? 0) + (live.predicted_tokens ?? 0);
    document.getElementById('session-total').innerHTML = formatNum(sessionTotal) + ' <span class="badge badge-session">session</span>';
    document.getElementById('cumulative').innerHTML = formatNum(tokens.cumulative ?? null) + ' <span class="badge badge-cumulative">all-time</span>';
    document.getElementById('ctx-max').textContent = formatNum(live.ctx_max ?? null);
    document.getElementById('requests').textContent = live.requests ?? '—';

    // Power
    const amd = energy.amd_watts ?? null;
    const nvidia = energy.nvidia_watts ?? null;
    const cpu = energy.cpu_power ?? 'N/A';
    document.getElementById('amd-power').textContent = amd != null ? amd.toFixed(1) + ' W' : '—';
    document.getElementById('nvidia-power').textContent = nvidia != null ? nvidia.toFixed(1) + ' W' : '—';
    const totalP = (amd != null && nvidia != null) ? (amd + nvidia) : null;
    const powerEl = document.getElementById('total-power');
    powerEl.innerHTML = totalP != null ? totalP.toFixed(1) + ' <span class="unit">W</span>' : '—';
    powerEl.className = 'big ' + powerClass(totalP);
    document.getElementById('cpu-power').textContent = cpu;

    // Energy
    document.getElementById('cum-wh').innerHTML = (energy.cumulative_wh != null ? energy.cumulative_wh.toFixed(4) : '—') + ' <span class="unit">Wh</span>';
    if (tokens.cumulative && tokens.cumulative > 0 && energy.cumulative_wh != null) {
      const whPerM = (energy.cumulative_wh / (tokens.cumulative / 1e6)).toFixed(2);
      document.getElementById('wh-per-m').textContent = whPerM + ' Wh';
    }
    // Avg power from snapshots
    if (snapshots.length >= 2) {
      const first = snapshots[0], last = snapshots[snapshots.length - 1];
      const dt = (last.epoch - first.epoch) / 3600; // hours
      const dWh = (last.cum_wh ?? 0) - (first.cum_wh ?? 0);
      if (dt > 0) {
        document.getElementById('avg-power').textContent = (dWh / dt).toFixed(1) + ' W';
      }
    }

    // Update charts
    updateChartData(snapshots);
  } catch(e) {
    dot.className = 'live-dot err';
    status.textContent = 'Error: ' + e.message;
  }
}

function updateChartData(snapshots) {
  const hours = { tokens: currentRange.tokens, cumulative: currentRange.cumulative, power: currentRange.power, energy: currentRange.energy };

  // Filter snapshots by range
  const cutoff = Date.now() / 1000 - hours.tokens * 3600;
  const filtered = snapshots.filter(s => s.epoch >= cutoff);

  const labels = filtered.map(s => new Date(s.ts));

  // Tokens chart
  tokensChart.data.labels = labels;
  tokensChart.data.datasets[0].data = filtered.map(s => s.prompt_tokens);
  tokensChart.data.datasets[1].data = filtered.map(s => s.predicted_tokens);
  tokensChart.update();

  // Cumulative chart
  cumulativeChart.data.labels = labels;
  cumulativeChart.data.datasets[0].data = filtered.map(s => s.cumulative);
  cumulativeChart.data.datasets[1].data = filtered.map(s => s.cum_wh);
  cumulativeChart.update();

  // Power chart
  powerChart.data.labels = labels;
  powerChart.data.datasets[0].data = filtered.map(s => s.amd_w);
  powerChart.data.datasets[1].data = filtered.map(s => s.nvidia_w);
  powerChart.data.datasets[2].data = filtered.map(s => s.amd_w + s.nvidia_w);
  powerChart.update();

  // Energy chart
  energyChart.data.labels = labels;
  energyChart.data.datasets[0].data = filtered.map(s => s.cum_wh);
  energyChart.update();
}

document.getElementById('refresh').addEventListener('click', fetchData);
initCharts();
fetchData();
setInterval(fetchData, 5000);
</script>
</body>
</html>"""


class MetricsHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == '/api/tokens':
            self.send_json(self.read_tokens())
        elif self.path == '/api/energy':
            self.send_json(self.read_energy())
        elif self.path == '/api/live':
            self.send_json(self.read_live())
        elif self.path == '/api/snapshots':
            self.send_json(self.read_snapshots())
        else:
            self.send_error(404)

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def read_tokens(self):
        try:
            with open(TOKENS_FILE) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return {
            "prompt_tokens": data.get("last_server_tokens", 0),
            "cumulative": data.get("cumulative", 0),
        }

    def read_energy(self):
        try:
            with open(ENERGY_FILE) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return {
            "amd_watts": data.get("last_amd_watts"),
            "nvidia_watts": data.get("last_nvidia_watts"),
            "cpu_power": "N/A",
            "cumulative_wh": data.get("cumulative_wh"),
        }

    def read_live(self):
        """Read live metrics from llama-server /metrics endpoint."""
        try:
            resp = urllib.request.urlopen(LLAMA_URL, timeout=3)
            text = resp.read().decode()
            result = {}
            for line in text.splitlines():
                if line.startswith('llamacpp:prompt_tokens_total'):
                    result['prompt_tokens'] = int(float(line.split()[1]))
                elif line.startswith('llamacpp:tokens_predicted_total'):
                    result['predicted_tokens'] = int(float(line.split()[1]))
                elif line.startswith('llamacpp:prompt_tokens_seconds'):
                    result['prompt_tps'] = float(line.split()[1])
                elif line.startswith('llamacpp:predicted_tokens_seconds'):
                    result['output_tps'] = float(line.split()[1])
                elif line.startswith('llamacpp:n_tokens_max'):
                    result['ctx_max'] = int(float(line.split()[1]))
                elif line.startswith('llamacpp:requests_processing'):
                    result['requests'] = int(float(line.split()[1]))
            return result
        except Exception:
            return {}

    def read_snapshots(self):
        """Read time-series snapshots from SQLite."""
        try:
            conn = sqlite3.connect(SNAPSHOT_DB)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM snapshots ORDER BY epoch DESC LIMIT 5000"
            ).fetchall()
            conn.close()
            # Return in chronological order
            result = [dict(r) for r in reversed(rows)]
            return result
        except (FileNotFoundError, sqlite3.OperationalError):
            return []


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8888)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()

    server = http.server.HTTPServer((args.host, args.port), MetricsHandler)
    print(f"llama-metrics dashboard: http://{args.host}:{args.port}")
    server.serve_forever()
