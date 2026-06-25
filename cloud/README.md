# cricket cloud GPU runner

A small AWS scaffolding to run the fine-tune **training** and **batch inference** jobs
on a rented GPU when the laptop 5090 is too slow (or too small, e.g. the 12B base).
The infra is job-agnostic: provision a spot GPU, push compressed data, run a job,
pull results, tear everything down. Teardown is the safety centerpiece.

> First cut: the local orchestration (boto3) and job scripts are written but have NOT
> been run against live AWS. Review `config.toml` and your account quotas before launch.

## Layout

```
cloud/
  config.toml      region / instance / AMI / bucket / tags  <- edit here
  aws_common.py    boto3 session, tagging, AMI-from-SSM, my-IP, state file
  provision.py     key pair + security group (SSH from your IP) + spot instance
  transfer.py      tar+zstd pack, S3 up/down, sha256 verify
  run.py           ssh in, run a job script, stream logs (paramiko)
  teardown.py      terminate + delete SG/key (+bucket); cost guard
  cli.py           one CLI over all of the above
  jobs/
    bootstrap.sh   one-time box setup (zstd, awscli, uv; GPU check)
    train.sh       payload -> HF base -> finetune_qlora -> upload adapter
    infer.sh       payload + adapter -> infer_batch -> upload generations
```

The remote generation entrypoint is `tools/infer_batch.py` (in the repo, shipped in the
payload). Training reuses `tools/finetune_qlora.py` (env-configurable).

## Prerequisites

- AWS credentials on the standard chain (env vars, `~/.aws/credentials`, or SSO).
- A vCPU quota for the chosen GPU family in `config.toml`'s region (g6e needs the
  "Running On-Demand G and VT instances" or the spot equivalent; request an increase if 0).
- Local deps are injected per-invocation; no global install:
  ```
  uv run --with "boto3,zstandard,paramiko" python cloud/cli.py <command>
  ```

## Train flow

```bash
# 0) build the training set locally (already done): data/finetune/train_full.jsonl
# 1) stage a payload dir with just what the box needs, then provision
mkdir -p cloud/_payload/tools cloud/_payload/data/finetune
cp tools/finetune_qlora.py cloud/_payload/tools/
cp data/finetune/train_full.jsonl cloud/_payload/data/finetune/
RUN='uv run --with "boto3,zstandard,paramiko" python cloud/cli.py'
$RUN provision
$RUN run bootstrap
# 2) upload payload, run training, pull the adapter
$RUN sync-up cloud/_payload payloads/train.tar.zst
$RUN run train payloads/train.tar.zst out/lunaris-rp-full-lora.tar.zst
$RUN sync-down out/lunaris-rp-full-lora.tar.zst cloud/_artifacts/full-lora.tar.zst
# 3) ALWAYS tear down
$RUN teardown
```

## Inference flow

```bash
# payload: tools/infer_batch.py + tools/pose_xml.py + prompts.jsonl
#   prompts.jsonl: one {"messages":[...], "expect":"Cricket"} per line (no assistant turn)
$RUN provision && $RUN run bootstrap
$RUN sync-up cloud/_payload payloads/infer.tar.zst
$RUN run infer payloads/infer.tar.zst out/lunaris-rp-full-lora.tar.zst out/generations.jsonl.zst
$RUN sync-down out/generations.jsonl.zst cloud/_artifacts/generations.jsonl.zst
$RUN teardown
```
Pass `-` as the adapter key to generate from the base model only.

## Safety / cost

- **Every** resource is tagged `Project=cricket-rp`. `teardown` finds and removes
  instances by that tag even if the local state file is stale; then it runs `guard`.
- `cloud/cli.py guard` (or `status`) lists any billable tagged resource still alive --
  run it any time to confirm nothing is left running.
- Spot by default with automatic on-demand fallback on capacity errors. Training
  checkpoints every `SAVE_STEPS`, so a spot reclaim loses at most one interval.
- The EBS volume is `DeleteOnTermination=true`. The S3 bucket is **kept** by default
  (results live there); `teardown --no-keep-bucket` empties and deletes it.
- Nothing here is committed: `.state.json`, `*.pem`, and `_artifacts/`/`_payload/`
  are gitignored.

## Notes

- AWS has no cheap *single* A100/H100 (those are 8-GPU `p4de`/`p5`). For the 8B,
  `g6e.xlarge` (1x L40S 48 GB, Ada) is the practical single-GPU box. For the 12B base,
  switch `instance_type` to a multi-GPU `p4de`/`p5` and raise `ebs_gb`.
- The base model is pulled from HF on the box, so only the ~149 MB train set (or the
  167 MB adapter) crosses the wire.
