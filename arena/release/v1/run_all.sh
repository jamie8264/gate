#!/usr/bin/env bash
# Batch DPA+DPB reproduction for the scenario/seed matrix.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY=/home/user/gate/.venv/bin/python
DEV_SEEDS="${DEV_SEEDS:-1 2 3 4 5}"
VAL_SEEDS="${VAL_SEEDS:-101 102 103 104 105}"
HOLDOUT_SEEDS="${HOLDOUT_SEEDS:-}"
SCENARIOS="${SCENARIOS:-normal:correlated normal:white fast:correlated event_heavy:correlated sensor_hard:correlated angle_sigma5:correlated slow:correlated}"
VARIANT="${VARIANT:-b3}"

run_case() {
  local seed="$1" scenario="$2" noise="$3" tag dpa_out dpb_out
  tag="seed_${seed}_${scenario}_${noise}"
  dpa_out="$ROOT/DPA/outputs/$tag"
  dpb_out="$ROOT/DPB/outputs/${tag}_${VARIANT}"
  if [ ! -f "$dpa_out/meta.json" ]; then
    (cd "$ROOT/DPA" && "$PY" -m dpa.cli --config config/default.yaml --seed "$seed" \
      --scenario "$scenario" --noise "$noise" --out "outputs/$tag" >/dev/null)
  fi
  (cd "$ROOT/DPB" && "$PY" -m dpb.cli --config config/default.yaml \
      --variant "$VARIANT" --dpa "../DPA/outputs/$tag" --out "outputs/${tag}_${VARIANT}" \
      --no-causal >/dev/null)
  printf 'done %s\n' "$tag"
}

for spec in $SCENARIOS; do
  scenario="${spec%%:*}"; noise="${spec##*:}"
  for seed in $DEV_SEEDS; do run_case "$seed" "$scenario" "$noise"; done
done
for spec in normal:correlated fast:correlated event_heavy:correlated; do
  scenario="${spec%%:*}"; noise="${spec##*:}"
  for seed in $VAL_SEEDS; do run_case "$seed" "$scenario" "$noise"; done
done
for seed in $HOLDOUT_SEEDS; do run_case "$seed" normal correlated; done

"$PY" "$ROOT/tools/aggregate.py"
