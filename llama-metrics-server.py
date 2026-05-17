#!/usr/bin/env python3
"""Simple metrics dashboard for llama-server token + energy data.
Reads state files and serves a live-updating dashboard on port 8888.
"""

import http.server
import json
import os
import time
from datetime import datetime, timezone

TOKENS_FILE = os.path.expanduser("~/.hermes/llama-tokens.json")
ENERGY_FILE = os.path.expanduser("~/.hermes/llama-energy.json")
LLAMA_URL = "http://localhost:8018/metrics"

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>llama-metrics</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #0d1117; color: #c9d1d9; padding: 24px;
  }
  h1 { font-size: 1.5rem; color: #58a6ff; margin-bottom: 8px; }
  .subtitle { color: #8b949e; font-size: 0.85rem; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px;
  }
  .card h2 { font-size: 0.8rem; text-transform: uppercase; color: #8b949e; letter-spacing: 0.05em; margin-bottom: 12px; }
  .metric { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #21262d; }
  .metric:last-child { border-bottom: none; }
  .metric .label { color: #8b949e; font-size: 0.9rem; }
  .metric .value { color: #c9d1d9; font-weight: 600; font-variant-numeric: tabular-nums; }
  .big { font-size: 1.8rem; font-weight: 700; color: #58a6ff; }
  .big .unit { font-size: 0.9rem; color: #8b949e; font-weight: 400; }
  .power-green { color: #3fb950; }
  .power-yellow { color: #d29922; }
  .power-red { color: #f85149; }
  #status { font-size: 0.75rem; color: #8b949e; margin-top: 16px; }
  #refresh { cursor: pointer; color: #58a6ff; text-decoration: underline; }
  .live-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
  .live-dot.ok { background: #3fb950; }
  .live-dot.err { background: #f85149; }
</style>
</head>
<body>
<h1>llama-metrics</h1>
<div class="subtitle">Real-time token &amp; energy dashboard</div>

<div class="grid">
  <div class="card">
    <h2>Tokens</h2>
    <div class="metric"><span class="label">Prompt tokens</span><span class="value" id="prompt-tokens">—</span></div>
    <div class="metric"><span class="label">Output tokens</span><span class="value" id="output-tokens">—</span></div>
    <div class="metric"><span class="label">Session total</span><span class="value" id="session-total">—</span></div>
    <div class="metric"><span class="label">All-time cumulative</span><span class="value" id="cumulative">—</span></div>
    <div class="metric"><span class="label">Context max</span><span class="value" id="ctx-max">—</span></div>
    <div class="metric"><span class="label">Active requests</span><span class="value" id="requests">—</span></div>
  </div>

  <div class="card">
    <h2>GPU Power</h2>
    <div class="metric"><span class="label">AMD (ROCm)</span><span class="value" id="amd-power">—</span></div>
    <div class="metric"><span class="label">NVIDIA</span><span class="value" id="nvidia-power">—</span></div>
    <div class="metric"><span class="label">Total GPU</span><span class="value" id="total-power">—</span></div>
    <div class="metric"><span class="label">CPU</span><span class="value" id="cpu-power">—</span></div>
  </div>

  <div class="card">
    <h2>Energy</h2>
    <div class="metric"><span class="label">All-time energy</span><span class="value" id="cum-wh">—</span></div>
    <div class="metric"><span class="label">Energy / 1M tokens</span><span class="value" id="wh-per-m">—</span></div>
  </div>
</div>

<div class="card">
  <h2>Throughput</h2>
  <div class="grid" style="margin:0;">
    <div class="metric"><span class="label">Prompt TPS</span><span class="value" id="prompt-tps">—</span></div>
    <div class="metric"><span class="label">Output TPS</span><span class="value" id="output-tps">—</span></div>
  </div>
</div>

<div id="status"><span class="live-dot" id="dot"></span><span id="status-text">Loading...</span> · <span id="refresh">Refresh now</span></div>

<script>
async function fetchMetrics() {
  const dot = document.getElementById('dot');
  const status = document.getElementById('status-text');
  try {
    const [tokens, energy, live] = await Promise.all([
      fetch('/api/tokens').then(r => r.json()),
      fetch('/api/energy').then(r => r.json()),
      fetch('/api/live').then(r => r.json())
    ]);
    dot.className = 'live-dot ok';
    status.textContent = 'Live · Updated ' + new Date().toLocaleTimeString();

    // Tokens
    document.getElementById('prompt-tokens').textContent = tokens.prompt_tokens?.toLocaleString() ?? '—';
    document.getElementById('output-tokens').textContent = tokens.predicted_tokens?.toLocaleString() ?? '—';
    document.getElementById('session-total').textContent = tokens.total?.toLocaleString() ?? '—';
    document.getElementById('cumulative').textContent = tokens.cumulative?.toLocaleString() ?? '—';
    document.getElementById('ctx-max').textContent = tokens.ctx_max?.toLocaleString() ?? '—';
    document.getElementById('requests').textContent = tokens.requests ?? '—';

    // Power
    const amd = energy.amd_watts ?? null;
    const nvidia = energy.nvidia_watts ?? null;
    const cpu = energy.cpu_power ?? 'N/A';
    document.getElementById('amd-power').textContent = amd != null ? amd.toFixed(1) + ' W' : '—';
    document.getElementById('nvidia-power').textContent = nvidia != null ? nvidia.toFixed(1) + ' W' : '—';
    const totalP = (amd != null && nvidia != null) ? (amd + nvidia) : null;
    const powerEl = document.getElementById('total-power');
    powerEl.textContent = totalP != null ? totalP.toFixed(1) + ' W' : '—';
    powerEl.className = 'value ' + powerClass(totalP);
    document.getElementById('cpu-power').textContent = cpu;

    // Energy
    document.getElementById('cum-wh').textContent = energy.cumulative_wh != null ? energy.cumulative_wh.toFixed(4) + ' Wh' : '—';
    if (tokens.cumulative && tokens.cumulative > 0 && energy.cumulative_wh != null) {
      const whPerM = (energy.cumulative_wh / (tokens.cumulative / 1e6)).toFixed(2);
      document.getElementById('wh-per-m').textContent = whPerM + ' Wh';
    }

    // Throughput
    document.getElementById('prompt-tps').textContent = tokens.prompt_tps != null ? tokens.prompt_tps.toFixed(1) + ' tok/s' : '—';
    document.getElementById('output-tps').textContent = tokens.output_tps != null ? tokens.output_tps.toFixed(1) + ' tok/s' : '—';

  } catch(e) {
    dot.className = 'live-dot err';
    status.textContent = 'Error: ' + e.message;
  }
}

function powerClass(w) {
  if (w == null) return '';
  if (w < 100) return 'power-green';
  if (w < 250) return 'power-yellow';
  return 'power-red';
}

document.getElementById('refresh').addEventListener('click', fetchMetrics);
fetchMetrics();
setInterval(fetchMetrics, 5000);
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
            import urllib.request
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


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8888)
    parser.add_argument('--host', default='0.0.0.0')
    args = parser.parse_args()

    server = http.server.HTTPServer((args.host, args.port), MetricsHandler)
    print(f"llama-metrics dashboard: http://{args.host}:{args.port}")
    server.serve_forever()
