"""Provision a GPU instance: key pair + security group (SSH from your IP only) + the
instance (spot by default, on-demand fallback). Writes cloud/.state.json for the other
commands. Reuses an existing key/SG by name so re-running is safe.
"""

import os
import stat
import time

import aws_common as A


def _ensure_key(ec2, cfg):
    name = cfg["aws"]["key_name"]
    key_path = os.path.join(A.ROOT, cfg["ssh"]["key_path"])
    existing = ec2.describe_key_pairs(Filters=[{"Name": "key-name", "Values": [name]}])["KeyPairs"]
    if existing and os.path.exists(key_path):
        return name, key_path
    if existing:                                    # key exists in AWS but we lost the .pem
        ec2.delete_key_pair(KeyName=name)
    kp = ec2.create_key_pair(KeyName=name, KeyType="rsa",
                             TagSpecifications=A.tag_specs(cfg, name, "key-pair"))
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    with open(key_path, "w") as fh:
        fh.write(kp["KeyMaterial"])
    try:
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)   # 600; no-op-ish on Windows
    except OSError:
        pass
    print("created key pair %s -> %s" % (name, key_path))
    return name, key_path


def _ensure_sg(ec2, cfg):
    name = cfg["aws"]["sg_name"]
    found = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": [name]}])["SecurityGroups"]
    sg_id = found[0]["GroupId"] if found else ec2.create_security_group(
        GroupName=name, Description="cricket-cloud SSH",
        TagSpecifications=A.tag_specs(cfg, name, "security-group"))["GroupId"]
    cidr = A.my_ip() + "/32"
    try:
        ec2.authorize_security_group_ingress(GroupId=sg_id, IpPermissions=[{
            "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
            "IpRanges": [{"CidrIp": cidr, "Description": "ssh from operator"}]}])
        print("SG %s: allow ssh from %s" % (sg_id, cidr))
    except ec2.exceptions.ClientError as e:
        if "InvalidPermission.Duplicate" not in str(e):
            raise
    return sg_id


def main(cfg):
    sess = A.session(cfg)
    ec2 = sess.client("ec2")
    a = cfg["aws"]
    key_name, key_path = _ensure_key(ec2, cfg)
    sg_id = _ensure_sg(ec2, cfg)
    ami = A.resolve_ami(sess, cfg)
    print("AMI %s | instance %s | spot=%s" % (ami, a["instance_type"], a["use_spot"]))

    run_args = dict(
        ImageId=ami, InstanceType=a["instance_type"], KeyName=key_name,
        SecurityGroupIds=[sg_id], MinCount=1, MaxCount=1,
        BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {
            "VolumeSize": a["ebs_gb"], "VolumeType": "gp3", "DeleteOnTermination": True}}],
        TagSpecifications=A.tag_specs(cfg, "cricket-gpu", "instance"))
    if a["use_spot"]:
        run_args["InstanceMarketOptions"] = {"MarketType": "spot",
                                             "SpotOptions": {"SpotInstanceType": "one-time"}}
    try:
        inst = ec2.run_instances(**run_args)["Instances"][0]
    except ec2.exceptions.ClientError as e:
        if a["use_spot"] and ("InsufficientInstanceCapacity" in str(e) or "capacity" in str(e).lower()):
            print("spot unavailable -> retrying on-demand")
            run_args.pop("InstanceMarketOptions", None)
            inst = ec2.run_instances(**run_args)["Instances"][0]
        else:
            raise

    iid = inst["InstanceId"]
    print("launched %s -- waiting for running + status checks..." % iid)
    ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
    ec2.get_waiter("instance_status_ok").wait(InstanceIds=[iid])
    desc = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
    ip = desc.get("PublicIpAddress", "")

    st = {"instance_id": iid, "public_ip": ip, "sg_id": sg_id, "sg_name": a["sg_name"],
          "key_name": key_name, "key_path": key_path, "region": a["region"],
          "bucket": A.bucket_name(sess, cfg), "spot": a["use_spot"],
          "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    A.save_state(st)
    print("READY  %s  ip=%s  bucket=%s" % (iid, ip, st["bucket"]))
    print("  ssh -i %s %s@%s" % (key_path, cfg["ssh"]["user"], ip))
    return st
