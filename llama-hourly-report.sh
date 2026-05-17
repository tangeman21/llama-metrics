#!/usr/bin/env bash
# llama-hourly-report.sh — print a compact report from llama-server metrics.
# Power/energy data is collected by llama-power-sampler.sh (runs every 30s in background).

METRICS=$(curl -s --max-time 5 http://localhost:8018/metrics) || { echo "llama-server offline."; exit 0; }
TOKEN_STATE="$HOME/.hermes/llama-tokens.json"
ENERGY_STATE="$HOME/.hermes/llama-energy.json"

# --- Token metrics ---
PROMPT_TOKENS=$(echo "$METRICS" | grep '^llamacpp:prompt_tokens_total ' | awk '{printf "%.0f", $2}')
PREDICTED_TOKENS=$(echo "$METRICS" | grep '^llamacpp:tokens_predicted_total ' | awk '{printf "%.0f", $2}')
PROMPT_TPS=$(echo "$METRICS" | grep '^llamacpp:prompt_tokens_seconds ' | awk '{print $2}')
PREDICTED_TPS=$(echo "$METRICS" | grep '^llamacpp:predicted_tokens_seconds ' | awk '{print $2}')
CTX_MAX=$(echo "$METRICS" | grep '^llamacpp:n_tokens_max ' | awk '{print $2}')
REQUESTS=$(echo "$METRICS" | grep '^llamacpp:requests_processing ' | awk '{print $2}')

TOTAL=$((PROMPT_TOKENS + PREDICTED_TOKENS))
CUMULATIVE=$(jq -r '.cumulative // 0' "$TOKEN_STATE" 2>/dev/null || echo "0")

# Update token cumulative state
NEW_CUMULATIVE=$((CUMULATIVE + TOTAL))
jq --argjson cum "$NEW_CUMULATIVE" --argjson last "$TOTAL" --argjson pid "$$" \
  '.cumulative = $cum | .last_server_tokens = $last | .last_pid = $pid' "$TOKEN_STATE" > "$TOKEN_STATE.tmp" && mv "$TOKEN_STATE.tmp" "$TOKEN_STATE"

# --- Energy metrics (from background sampler) ---
if [ -f "$ENERGY_STATE" ]; then
  AMD_POWER=$(jq -r '.last_amd_watts // 0' "$ENERGY_STATE")
  NVIDIA_POWER=$(jq -r '.last_nvidia_watts // 0' "$ENERGY_STATE")
  CUM_WH=$(jq -r '.cumulative_wh // 0' "$ENERGY_STATE")
  TOTAL_POWER=$(echo "scale=1; $AMD_POWER + $NVIDIA_POWER" | bc 2>/dev/null || echo "$AMD_POWER")
  CPU_POWER="N/A"
else
  AMD_POWER="0.0"; NVIDIA_POWER="0.0"; CUM_WH="0"; TOTAL_POWER="0.0"
fi

# --- Output ---
echo "llama-server hourly report"
echo "  Input tokens (prompt):     ${PROMPT_TOKENS} (${PROMPT_TPS} tok/s)"
echo "  Output tokens (predicted): ${PREDICTED_TOKENS} (${PREDICTED_TPS} tok/s)"
echo "  Total this session:        ${TOTAL}"
echo "  All-time cumulative:       ${NEW_CUMULATIVE}"
echo "  Context max:               ${CTX_MAX}"
echo "  Active requests:           ${REQUESTS}"
echo ""
echo "  AMD GPU (ROCm):            ${AMD_POWER} W"
echo "  NVIDIA GPU:                ${NVIDIA_POWER} W"
echo "  CPU:                       ${CPU_POWER}"
echo "  Total GPU power:           ${TOTAL_POWER} W"
echo "  All-time energy:           $(printf '%.4f' "${CUM_WH:-0}") Wh"
