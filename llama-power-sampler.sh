#!/usr/bin/env bash
# llama-power-sampler.sh — sample GPU/CPU power every 30 seconds.
# Runs as a background process; writes to llama-energy.json.
# Usage: bash llama-power-sampler.sh (runs in loop)

ENERGY_STATE="$HOME/.hermes/llama-energy.json"

# Initialize state file
if [ ! -f "$ENERGY_STATE" ]; then
  echo '{"cumulative_wh": 0, "last_amd_watts": 0, "last_nvidia_watts": 0, "last_ts": 0}' > "$ENERGY_STATE"
fi

while true; do
  NOW=$(date +%s)

  # AMD GPU (ROCm)
  AMD_POWER=$(rocm-smi --showpower 2>/dev/null | grep "Current Socket" | awk -F': ' '{print $3}' | tr -d ' ')
  [ -z "$AMD_POWER" ] && AMD_POWER="0.0"

  # NVIDIA GPU
  NVIDIA_POWER=$(nvidia-smi --query-gpu=power.draw --format=csv,noheader,nounits 2>/dev/null | awk '{s+=$1} END {printf "%.1f", s}')
  [ -z "$NVIDIA_POWER" ] && NVIDIA_POWER="0.0"

  # CPU power (not directly available on AMD — try hwmon)
  CPU_POWER="N/A"
  for hw in /sys/class/hwmon/hwmon*/; do
    name=$(cat "$hw/name" 2>/dev/null)
    if [ "$name" = "k10temp" ]; then
      v=$(cat "$hw/power*_average" 2>/dev/null || cat "$hw/power*_input" 2>/dev/null)
      if [ -n "$v" ]; then
        CPU_POWER=$(echo "$v / 1000000" | bc 2>/dev/null || echo "$v")
        break
      fi
    fi
  done

  # Total GPU power
  TOTAL_POWER=$(echo "scale=1; $AMD_POWER + $NVIDIA_POWER" | bc 2>/dev/null || echo "$AMD_POWER")

  # Read previous sample
  LAST_AMD=$(jq -r '.last_amd_watts // 0' "$ENERGY_STATE" 2>/dev/null)
  LAST_NVIDIA=$(jq -r '.last_nvidia_watts // 0' "$ENERGY_STATE" 2>/dev/null)
  LAST_TS=$(jq -r '.last_ts // 0' "$ENERGY_STATE" 2>/dev/null)
  CUM_WH=$(jq -r '.cumulative_wh // 0' "$ENERGY_STATE" 2>/dev/null)

  # Calculate watt-hours since last sample
  if [ "$LAST_TS" != "0" ] && [ "$LAST_TS" != "" ]; then
    DELTA_S=$((NOW - LAST_TS))
    AVG_AMD=$(echo "scale=2; ($LAST_AMD + $AMD_POWER) / 2" | bc 2>/dev/null || echo "$AMD_POWER")
    AVG_NVIDIA=$(echo "scale=2; ($LAST_NVIDIA + $NVIDIA_POWER) / 2" | bc 2>/dev/null || echo "$NVIDIA_POWER")
    AVG_TOTAL=$(echo "scale=2; $AVG_AMD + $AVG_NVIDIA" | bc 2>/dev/null || echo "$TOTAL_POWER")
    DELTA_WH=$(echo "scale=4; $AVG_TOTAL * $DELTA_S / 3600" | bc 2>/dev/null || echo "0")
    CUM_WH=$(echo "scale=4; $CUM_WH + $DELTA_WH" | bc 2>/dev/null || echo "$CUM_WH")
  else
    DELTA_WH="0"
  fi

  # Update state file
  jq --argjson wh "$CUM_WH" --argjson amd "$AMD_POWER" --argjson nvidia "$NVIDIA_POWER" \
    --argjson ts "$NOW" \
    '.cumulative_wh = $wh | .last_amd_watts = $amd | .last_nvidia_watts = $nvidia | .last_ts = $ts' \
    "$ENERGY_STATE" > "$ENERGY_STATE.tmp" && mv "$ENERGY_STATE.tmp" "$ENERGY_STATE"

  sleep 30
done
