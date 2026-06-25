#!/usr/bin/env bash
# Batch inference on the box. Args: <payload_key> <adapter_key> <out_key>
#   payload     = tar.zst of a staging dir with tools/infer_batch.py, tools/pose_xml.py,
#                 and prompts.jsonl (one prompt-message-list per line).
#   adapter_key = S3 key of a trained adapter tarball (from a train run); "-" for base-only.
#   out_key     = S3 key to upload generations.jsonl.zst to.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

PAYLOAD_KEY="${1:?need payload_key}"
ADAPTER_KEY="${2:?need adapter_key or '-'}"
OUT_KEY="${3:?need out_key}"
: "${RUN_BUCKET:?RUN_BUCKET not set}"
HF_BASE="${HF_BASE:-Sao10K/L3-8B-Lunaris-v1}"

DEPS="torch,transformers>=5,<6,peft,accelerate,safetensors,huggingface_hub"

cd ~/cricket
echo "=== fetch payload ==="
aws s3 cp "s3://$RUN_BUCKET/$PAYLOAD_KEY" payload.tar.zst
zstd -d -f payload.tar.zst -o payload.tar && tar xf payload.tar --strip-components=1

ADAPTER_ARG="--base-only"
if [ "$ADAPTER_KEY" != "-" ]; then
  echo "=== fetch adapter ==="
  aws s3 cp "s3://$RUN_BUCKET/$ADAPTER_KEY" adapter.tar.zst
  zstd -d -f adapter.tar.zst -o adapter.tar && tar xf adapter.tar
  ADAPTER_ARG="--adapter out-lora"
fi

echo "=== download base from HF ==="
uv run --with "$DEPS" python - <<PY
from huggingface_hub import snapshot_download
import os
p = snapshot_download("$HF_BASE")
os.makedirs("data/finetune", exist_ok=True)
open("data/finetune/base_path.txt", "w").write(p)
print("base ->", p)
PY

echo "=== generate ==="
uv run --with "$DEPS" python tools/infer_batch.py --prompts prompts.jsonl \
  --out generations.jsonl $ADAPTER_ARG

echo "=== upload generations ==="
zstd -f generations.jsonl -o generations.jsonl.zst
SHA=$(sha256sum generations.jsonl.zst | cut -d' ' -f1)
aws s3 cp generations.jsonl.zst "s3://$RUN_BUCKET/$OUT_KEY" --metadata "sha256=$SHA"
echo "DONE generations -> s3://$RUN_BUCKET/$OUT_KEY (sha256=$SHA)"
