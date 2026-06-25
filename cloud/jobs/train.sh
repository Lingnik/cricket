#!/usr/bin/env bash
# Train on the box. Args: <payload_key> <out_key>
#   payload  = tar.zst of a staging dir containing tools/finetune_qlora.py and
#              data/finetune/<TRAIN_FILE> (default train_full.jsonl).
#   out_key  = S3 key to upload the resulting adapter tarball to.
# The base model is pulled from HF on the box (not uploaded). RUN_BUCKET is injected by run.py.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

PAYLOAD_KEY="${1:?need payload_key}"
OUT_KEY="${2:?need out_key}"
: "${RUN_BUCKET:?RUN_BUCKET not set}"
HF_BASE="${HF_BASE:-Sao10K/L3-8B-Lunaris-v1}"
TRAIN_FILE="${TRAIN_FILE:-train_full.jsonl}"
EPOCHS="${EPOCHS:-1}"
SAVE_STEPS="${SAVE_STEPS:-400}"

DEPS="torch,transformers>=5,<6,peft,accelerate,safetensors,huggingface_hub"

cd ~/cricket
echo "=== fetch payload ==="
aws s3 cp "s3://$RUN_BUCKET/$PAYLOAD_KEY" payload.tar.zst
zstd -d -f payload.tar.zst -o payload.tar && tar xf payload.tar --strip-components=1

echo "=== download base from HF ==="
uv run --with "$DEPS" python - <<PY
from huggingface_hub import snapshot_download
import os
p = snapshot_download("$HF_BASE")
os.makedirs("data/finetune", exist_ok=True)
open("data/finetune/base_path.txt", "w").write(p)
print("base ->", p)
PY

echo "=== train ==="
TRAIN_FILE="$TRAIN_FILE" OUT_DIR="$PWD/out-lora" EPOCHS="$EPOCHS" \
  SAVE_STRATEGY=steps SAVE_STEPS="$SAVE_STEPS" \
  uv run --with "$DEPS" python tools/finetune_qlora.py

echo "=== upload adapter ==="
tar c -C "$PWD" out-lora | zstd -o out-lora.tar.zst
SHA=$(sha256sum out-lora.tar.zst | cut -d' ' -f1)
aws s3 cp out-lora.tar.zst "s3://$RUN_BUCKET/$OUT_KEY" --metadata "sha256=$SHA"
echo "DONE adapter -> s3://$RUN_BUCKET/$OUT_KEY (sha256=$SHA)"
