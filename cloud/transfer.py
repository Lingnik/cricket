"""Compressed dataset/artifact transfer via S3.

Local side: pack a directory to tar.zst, upload to the run bucket; download a result
tarball and unpack. SHA-256 of the compressed archive is recorded as S3 object metadata
and verified on download. The instance side uses `aws s3 cp` directly (see jobs/*.sh).
"""

import hashlib
import os
import tarfile

import zstandard as zstd

import aws_common as A


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pack(src_dir, out_path, level=10):
    """tar + zstd a directory tree. Returns (out_path, sha256)."""
    src_dir = src_dir.rstrip("/\\")
    arc = os.path.basename(src_dir)
    with open(out_path, "wb") as raw:
        with zstd.ZstdCompressor(level=level).stream_writer(raw) as zf:
            with tarfile.open(mode="w|", fileobj=zf) as tar:
                tar.add(src_dir, arcname=arc)
    return out_path, _sha256(out_path)


def unpack(archive, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    with open(archive, "rb") as raw:
        with zstd.ZstdDecompressor().stream_reader(raw) as zf:
            with tarfile.open(mode="r|", fileobj=zf) as tar:
                tar.extractall(dest_dir, filter="data")


def upload(sess, cfg, local_path, key, sha=None):
    bucket = A.ensure_bucket(sess, cfg, A.bucket_name(sess, cfg))
    extra = {"Metadata": {"sha256": sha}} if sha else {}
    sess.client("s3").upload_file(local_path, bucket, key, ExtraArgs=extra)
    size_mb = os.path.getsize(local_path) / 1e6
    print("up  %.1f MB -> s3://%s/%s" % (size_mb, bucket, key))
    return bucket, key


def download(sess, cfg, key, local_path):
    s3 = sess.client("s3")
    bucket = A.bucket_name(sess, cfg)
    head = s3.head_object(Bucket=bucket, Key=key)
    s3.download_file(bucket, key, local_path)
    want = head.get("Metadata", {}).get("sha256")
    if want:
        got = _sha256(local_path)
        if got != want:
            raise SystemExit("sha256 mismatch on %s: want %s got %s" % (key, want, got))
        print("down s3://%s/%s -> %s  [sha256 ok]" % (bucket, key, local_path))
    else:
        print("down s3://%s/%s -> %s" % (bucket, key, local_path))
    return local_path


def sync_up(sess, cfg, src_dir, key):
    """Pack a local dir and upload it. Returns the S3 key."""
    staging = os.path.join(A.CLOUD, "_artifacts")
    os.makedirs(staging, exist_ok=True)
    archive = os.path.join(staging, os.path.basename(key))
    print("packing %s ..." % src_dir)
    _, sha = pack(src_dir, archive)
    upload(sess, cfg, archive, key, sha=sha)
    return key
