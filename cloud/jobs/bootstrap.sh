#!/usr/bin/env bash
# One-time box setup. The Deep Learning Base AMI ships the NVIDIA driver + CUDA;
# we add zstd, the AWS CLI, and uv (which manages ephemeral Python envs per job).
set -euo pipefail

echo "=== GPU ==="
nvidia-smi || { echo "ERROR: no GPU visible"; exit 1; }

echo "=== packages ==="
sudo apt-get update -y
sudo apt-get install -y zstd awscli

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

mkdir -p ~/cricket
echo "bootstrap done."
