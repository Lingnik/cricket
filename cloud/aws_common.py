"""Shared AWS + state helpers for the cricket cloud GPU workflow.

Local-side orchestration, run on the Windows laptop via boto3. Every created resource
is tagged with the project tag so `teardown`/`guard` can find and remove it reliably.
No secrets live here -- credentials come from the standard boto3 chain (env / ~/.aws / SSO).

Run the CLI from the repo root with the deps injected, e.g.:
    uv run --with "boto3,zstandard,paramiko" python cloud/cli.py provision
"""

import json
import os
import tomllib
import urllib.request

import boto3

CLOUD = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(CLOUD)
STATE = os.path.join(CLOUD, ".state.json")


def load_config():
    with open(os.path.join(CLOUD, "config.toml"), "rb") as fh:
        return tomllib.load(fh)


def session(cfg):
    a = cfg["aws"]
    kw = {"region_name": a["region"]}
    if a.get("profile"):
        kw["profile_name"] = a["profile"]
    return boto3.Session(**kw)


def account_id(sess):
    return sess.client("sts").get_caller_identity()["Account"]


def tag_specs(cfg, name, resource_type):
    return [{"ResourceType": resource_type, "Tags": [
        {"Key": "Project", "Value": cfg["aws"]["project_tag"]},
        {"Key": "Name", "Value": name},
        {"Key": "ManagedBy", "Value": "cricket-cloud"},
    ]}]


def my_ip():
    """Public IP of this machine, for a tight SSH ingress rule."""
    return urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10).read().decode().strip()


def resolve_ami(sess, cfg):
    a = cfg["aws"]
    if a.get("ami_id"):
        return a["ami_id"]
    return sess.client("ssm").get_parameter(Name=a["ami_ssm_param"])["Parameter"]["Value"]


def bucket_name(sess, cfg):
    b = cfg["aws"].get("bucket")
    if b:
        return b
    return "cricket-cloud-%s-%s" % (account_id(sess), cfg["aws"]["region"])


def ensure_bucket(sess, cfg, name):
    s3 = sess.client("s3")
    region = cfg["aws"]["region"]
    existing = [b["Name"] for b in s3.list_buckets()["Buckets"]]
    if name in existing:
        return name
    kw = {"Bucket": name}
    if region != "us-east-1":                       # us-east-1 rejects an explicit constraint
        kw["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**kw)
    s3.get_waiter("bucket_exists").wait(Bucket=name)
    s3.put_bucket_tagging(Bucket=name, Tagging={"TagSet": [
        {"Key": "Project", "Value": cfg["aws"]["project_tag"]},
        {"Key": "ManagedBy", "Value": "cricket-cloud"}]})
    return name


def load_state():
    return json.load(open(STATE)) if os.path.exists(STATE) else {}


def save_state(st):
    json.dump(st, open(STATE, "w"), indent=2)


def clear_state():
    if os.path.exists(STATE):
        os.remove(STATE)


def require_state():
    st = load_state()
    if not st.get("instance_id"):
        raise SystemExit("no active instance in cloud/.state.json -- run `provision` first")
    return st
