# llama-metrics

Hourly token count + energy (watt-hour) tracking for llama-server.

## Components

### `llama-power-sampler.sh`
Background process that samples GPU/CPU power every 30 seconds.
- AMD GPU (ROCm) via `rocm-smi`
- NVIDIA GPU via `nvidia-smi`
- CPU: not available on this AMD system (no RAPL/hwmon power)
- Writes cumulative watt-hours to `~/.hermes/llama-energy.json`

### `llama-hourly-report.sh`
Cron job (every 30m) that prints token counts + energy summary.
- Reads llama-server metrics from `http://localhost:8018/metrics`
- Reads power data from the background sampler's state file
- Writes cumulative token counts to `~/.hermes/llama-tokens.json`

## Setup

### 1. Start the power sampler (background, runs forever)
```bash
nohup bash ~/.hermes/scripts/llama-power-sampler.sh > /dev/null 2>&1 &
```

### 2. Set up cron job (every 30m)
```bash
# Using hermes cron tool, or manually:
(crontab -l 2>/dev/null; echo "*/30 * * * * bash ~/.hermes/scripts/llama-hourly-report.sh >> ~/.hermes/llama-report.log 2>&1") | crontab -
```

## State Files
- `~/.hermes/llama-energy.json` — power samples + cumulative Wh
- `~/.hermes/llama-tokens.json` — token counts + cumulative total

## Output Example
```
llama-server hourly report
  Input tokens (prompt):     1308980 (192.449 tok/s)
  Output tokens (predicted): 62591 (7.50917 tok/s)
  Total this session:        1371571
  All-time cumulative:       9102164
  Context max:               100095
  Active requests:           1

  AMD GPU (ROCm):            204.0 W
  NVIDIA GPU:                61.5 W
  CPU:                       N/A
  Total GPU power:           265.5 W
  All-time energy:           10.2960 Wh
```
