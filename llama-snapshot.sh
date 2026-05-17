#!/usr/bin/env bash
# llama-snapshot.sh — write a time-series snapshot for graphing.
# Called by the power sampler every 5 minutes.
# Writes JSONL to ~/.hermes/llama-snapshots.jsonl

SNAPSHOT_FILE="$HOME/.hermes/llama-snapshots.jsonl"
TOKENS_FILE="$HOME/.hermes/llama-tokens.json"
ENERGY_FILE="$HOME/.hermes/llama-energy.json"

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EPOCH=$(date +%s)

# Token metrics from llama-server
METRICS=$(curl -s --max-time 3 http://localhost:8018/metrics 2>/dev/null)
PROMPT_TOKENS=$(echo "$METRICS" | grep '^llamacpp:prompt_tokens_total ' | awk '{printf "%.0f", $2}')
PREDICTED_TOKENS=$(echo "$METRICS" | grep '^llamacpp:tokens_predicted_total ' | awk '{printf "%.0f", $2}')
PROMPT_TPS=$(echo "$METRICS" | grep '^llamacpp:prompt_tokens_seconds ' | awk '{print $2}')
PREDICTED_TPS=$(echo "$METRICS" | grep '^llamacpp:predicted_tokens_seconds ' | awk '{print $2}')
CTX_MAX=$(echo "$METRICS" | grep '^llamacpp:n_tokens_max ' | awk '{print $2}')
REQUESTS=$(echo "$METRICS" | grep '^llamacpp:requests_processing ' | awk '{print $2}')

# Token cumulative from state file
CUMULATIVE=$(jq -r '.cumulative // 0' "$TOKENS_FILE" 2>/dev/null || echo "0")

# Power from energy state file
AMD_POWER=$(jq -r '.last_amd_watts // 0' "$ENERGY_FILE" 2>/dev/null)
NVIDIA_POWER=$(jq -r '.last_nvidia_watts // 0' "$ENERGY_FILE" 2>/dev/null)
CUM_WH=$(jq -r '.cumulative_wh // 0' "$ENERGY_FILE" 2>/dev/null)

# Total power
TOTAL_POWER=$(echo "scale=1; $AMD_POWER + $NVIDIA_POWER" | bc 2>/dev/null || echo "$AMD_POWER")

# Write snapshot (append-only JSONL)
echo "{\"ts\":\"$NOW\",\"epoch\":$EPOCH,\"prompt_tokens\":$PROMPT_TOKENS,\"predicted_tokens\":$PREDICTED_TOKENS,\"cumulative\":$CUMULATIVE,\"total_power_w\":$TOTAL_POWER,\"amd_w\":$AMD_POWER,\"nvidia_w\":$NVIDIA_POWER,\"cum_wh\":$CUM_WH,\"prompt_tps\":$PROMPT_TPS,\"output_tps\":$PREDICTED_TPS,\"ctx_max\":$CTX_MAX,\"requests\":$REQUESTS}" >> "$SNAPSHOT_FILE"
