"""cricket cloud GPU runner -- one CLI over provision / transfer / run / teardown.

    uv run --with "boto3,zstandard,paramiko" python cloud/cli.py <command>

Commands:
    provision                 launch a spot GPU box (key + SG + instance), write state
    status                    show the active instance + run the cost guard
    sync-up   <dir> <key>     tar+zstd a local dir and upload to the run bucket
    sync-down <key> <dest>    download a result archive (sha256-verified)
    run       <job> [args]    run cloud/jobs/<job>.sh on the box, streaming logs
    teardown  [--no-keep-bucket]   terminate + delete SG/key (+bucket), then guard
    guard                     list any billable tagged resources still alive
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aws_common as A      # noqa: E402
import provision as P       # noqa: E402
import run as R             # noqa: E402
import teardown as D        # noqa: E402
import transfer as T        # noqa: E402


def _status(cfg):
    st = A.load_state()
    if st.get("instance_id"):
        print("instance %s  ip=%s  bucket=%s  since=%s"
              % (st["instance_id"], st.get("public_ip"), st.get("bucket"), st.get("created_utc")))
    else:
        print("no active instance (state file empty).")
    D.guard(cfg)


def main():
    cfg = A.load_config()
    ap = argparse.ArgumentParser(prog="cloud", description="cricket cloud GPU runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("provision")
    sub.add_parser("status")
    sub.add_parser("guard")
    u = sub.add_parser("sync-up"); u.add_argument("src_dir"); u.add_argument("key")
    d = sub.add_parser("sync-down"); d.add_argument("key"); d.add_argument("dest")
    r = sub.add_parser("run"); r.add_argument("job"); r.add_argument("args", nargs="*")
    t = sub.add_parser("teardown"); t.add_argument("--no-keep-bucket", action="store_true")
    args = ap.parse_args()

    sess = A.session(cfg)
    if args.cmd == "provision":
        P.main(cfg)
    elif args.cmd == "status":
        _status(cfg)
    elif args.cmd == "guard":
        D.guard(cfg)
    elif args.cmd == "sync-up":
        T.sync_up(sess, cfg, args.src_dir, args.key)
    elif args.cmd == "sync-down":
        T.download(sess, cfg, args.key, args.dest)
    elif args.cmd == "run":
        sys.exit(R.run(cfg, args.job, args.args))
    elif args.cmd == "teardown":
        D.teardown(cfg, keep_bucket=not args.no_keep_bucket)


if __name__ == "__main__":
    main()
