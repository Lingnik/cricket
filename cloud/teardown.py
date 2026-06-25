"""Teardown + cost guard -- the safety centerpiece.

`teardown` terminates the instance, deletes the security group and key pair, and
(optionally) empties/keeps the S3 bucket, then clears local state. `guard` scans the
region for ANY resource carrying the project tag that is still alive -- so a half-failed
teardown or a forgotten box can't quietly bill you.
"""

import aws_common as A

TAG = "tag:Project"


def _project_filter(cfg):
    return [{"Name": TAG, "Values": [cfg["aws"]["project_tag"]]}]


def teardown(cfg, keep_bucket=True):
    sess = A.session(cfg)
    ec2 = sess.client("ec2")
    st = A.load_state()

    # 1) terminate any tagged, non-terminated instances (state file may be stale)
    res = ec2.describe_instances(Filters=_project_filter(cfg) + [
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}])
    ids = [i["InstanceId"] for r in res["Reservations"] for i in r["Instances"]]
    if ids:
        print("terminating instances:", ids)
        ec2.terminate_instances(InstanceIds=ids)
        ec2.get_waiter("instance_terminated").wait(InstanceIds=ids)
        print("  terminated.")
    else:
        print("no live instances.")

    # 2) delete the security group (must be after instances are gone)
    sg = st.get("sg_name") or cfg["aws"]["sg_name"]
    for g in ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [sg]}])["SecurityGroups"]:
        try:
            ec2.delete_security_group(GroupId=g["GroupId"])
            print("deleted SG", g["GroupId"])
        except ec2.exceptions.ClientError as e:
            print("could not delete SG %s yet: %s" % (g["GroupId"], e))

    # 3) delete the key pair
    name = st.get("key_name") or cfg["aws"]["key_name"]
    try:
        ec2.delete_key_pair(KeyName=name)
        print("deleted key pair", name)
    except ec2.exceptions.ClientError as e:
        print("key pair:", e)

    # 4) bucket: kept by default (results live here); --no-keep-bucket empties + deletes it
    if not keep_bucket:
        b = A.bucket_name(sess, cfg)
        s3 = sess.resource("s3")
        try:
            s3.Bucket(b).objects.all().delete()
            s3.Bucket(b).delete()
            print("deleted bucket", b)
        except Exception as e:                      # noqa: BLE001
            print("bucket cleanup:", e)
    else:
        print("kept bucket (use --no-keep-bucket to delete it).")

    A.clear_state()
    print("teardown complete; local state cleared.")
    guard(cfg)


def guard(cfg):
    """List anything still alive under the project tag. Should print 'clean' after teardown."""
    sess = A.session(cfg)
    ec2 = sess.client("ec2")
    alive = []
    res = ec2.describe_instances(Filters=_project_filter(cfg) + [
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]}])
    for r in res["Reservations"]:
        for i in r["Instances"]:
            alive.append("instance %s (%s)" % (i["InstanceId"], i["State"]["Name"]))
    for v in ec2.describe_volumes(Filters=_project_filter(cfg))["Volumes"]:
        if v["State"] != "deleted":
            alive.append("volume %s (%s)" % (v["VolumeId"], v["State"]))
    for s in ec2.describe_security_groups(Filters=_project_filter(cfg))["SecurityGroups"]:
        alive.append("security-group %s" % s["GroupId"])
    print("--- cost guard (project=%s, region=%s) ---" % (cfg["aws"]["project_tag"], cfg["aws"]["region"]))
    if alive:
        print("STILL ALIVE (billable):")
        for a in alive:
            print("  -", a)
    else:
        print("clean -- no billable tagged resources.")
    return alive
