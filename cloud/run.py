"""Run a job on the provisioned instance over SSH, streaming logs live.

Jobs live in cloud/jobs/*.sh. They are copied to the box and executed there; all heavy
lifting (HF base download, training/inference, S3 result upload) happens remotely so the
laptop only orchestrates.
"""

import os
import time

import paramiko

import aws_common as A


def _client(st, cfg, retries=10):
    last = None
    for i in range(retries):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(st["public_ip"], username=cfg["ssh"]["user"],
                      key_filename=st["key_path"], timeout=30)
            return c
        except Exception as e:                      # noqa: BLE001 -- sshd may not be up yet
            last = e
            print("ssh not ready (%d/%d): %s" % (i + 1, retries, e))
            time.sleep(10)
    raise SystemExit("could not ssh to %s: %s" % (st["public_ip"], last))


def _exec(c, cmd):
    chan = c.get_transport().open_session()
    chan.get_pty()
    chan.exec_command(cmd)
    buf = b""
    while True:
        if chan.recv_ready():
            data = chan.recv(4096)
            buf += data
            print(data.decode(errors="replace"), end="", flush=True)
        if chan.exit_status_ready() and not chan.recv_ready():
            break
        time.sleep(0.1)
    return chan.recv_exit_status()


def put_jobs(c):
    sftp = c.open_sftp()
    try:
        c.exec_command("mkdir -p ~/cricket/jobs")
        time.sleep(1)
        jobs_dir = os.path.join(A.CLOUD, "jobs")
        for fn in os.listdir(jobs_dir):
            sftp.put(os.path.join(jobs_dir, fn), "cricket/jobs/" + fn)
        c.exec_command("chmod +x ~/cricket/jobs/*.sh")
        time.sleep(1)
    finally:
        sftp.close()


def run(cfg, job, args):
    st = A.require_state()
    c = _client(st, cfg)
    try:
        put_jobs(c)
        argline = " ".join('"%s"' % a for a in args)
        cmd = 'cd ~/cricket && RUN_BUCKET="%s" bash jobs/%s.sh %s' % (st.get("bucket", ""), job, argline)
        print("=== remote: %s ===" % cmd)
        code = _exec(c, cmd)
        print("\n=== job '%s' exited %d ===" % (job, code))
        return code
    finally:
        c.close()
