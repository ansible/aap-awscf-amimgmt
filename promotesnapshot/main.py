import os
import boto3
import botocore.exceptions
import json
import glob
from io import StringIO
import sys


def env_set(env_var, default):
    if env_var in os.environ:
        return os.environ[env_var]
    elif os.path.exists(env_var) and os.path.getsize(env_var) > 0:
        with open(env_var, "r") as env_file:
            var = env_file.read().strip()
            env_file.close()
        return var
    else:
        return default

def whoami():
    client = boto3.client('sts')
    response = client.get_caller_identity()["Account"]
    return response

def findAMIs(snapshot_path, snapshot_date):
    ami_map = {}
    try:
        with open("{}/aws-ami-regions_SNAPSHOT-{}.json".format(snapshot_path, snapshot_date), "r") as ami_file:
            ami_text = ami_file.read()
            ami_map = json.loads(ami_text)
    except:
        print("Didn't find {}/aws-ami-regions_SNAPSHOT-{}.json; checking by name".format(snapshot_path, snapshot_date))
        filenamesList = glob.glob("{}/aws-ami*.json".format(snapshot_path))
        try:
            with open("{}".format(filenamesList[0]), "r") as ami_file:
                ami_text = ami_file.read()
                ami_map = json.loads(ami_text)
            print("...and succeeded")
        except:
            print("Didn't find regions when looking at the first file name in {}.".format(json.dumps(filenamesList)))
    return ami_map


def loginEC2Clients(ami_map):
    client_map = {}
    for region in ami_map:
        os.environ["AWS_DEFAULT_REGION"] = region
        client = boto3.client("ec2")
        element = {region: client}
        client_map.update(element)
    return client_map


def loginS3Client(region):
    os.environ["AWS_DEFAULT_REGION"] = region
    client = boto3.client("s3")
    return client


def findSNAPs(client_map, ami_map):
    snap_map = {}
    for region in ami_map:
        client = client_map[region]
        try:
            response = client.describe_images(ImageIds=[ami_map[region]])
            for image in response["Images"]:
                for blockDeviceMap in image["BlockDeviceMappings"]:
                    snap = blockDeviceMap["Ebs"]["SnapshotId"]
                    element = {region: snap}
                    snap_map.update(element)
        except:
            print("Nope, AMI {} isn't in this region, so we can't look up its snaps".format(ami_map[region]))
    return snap_map


def retagAMIs(client_map, ami_map, new_tag):
    print("retagAMIs entry, retagging to {}".format(new_tag))
    success = True
    for region in ami_map:
        try:
            print("Looking for {} in region {}:".format(ami_map[region], region))
            results = client_map[region].describe_images(ImageIds=[ami_map[region]])
            try:
                response = client_map[region].create_tags(DryRun=False,
                    Resources=[ ami_map[region] ], Tags=[ { 'Key': 'aap-awscf-promotion', 'Value': 'deployed' }, ])
                if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                    print("Updated, ok")
                else:
                    print(json.dumps(response, indent=4))
            except botocore.exceptions.ClientError as err2:
              if err2.response["Error"]["Code"] == "DryRunOperation":
                print("Dry run, ok")
              else:
                print("Try of create_tag error: {}".format(err2))
                success = False
        except botocore.exceptions.ClientError as err1:
            if err1.response["Error"]["Code"] == "InvalidAMIID.NotFound":
                print("AMI no longer present; continuing.")
            else:
                print("Try of describe_images error: {}\n{}".format(json.dumps(err1.response, indent=4), err1))
                success = False
    print("retagAMIs exit, returning {}".format(success))
    return success


def retagSNAPs(client_map, snap_map, new_tag):
    print("retagSNAPS entry, retagging to {}".format(new_tag))
    success = True
    for region in snap_map:
        try:
            print("Looking for {} in region {}:".format(snap_map[region], region))
            response = client_map[region].create_tags(DryRun=False,
                Resources=[ snap_map[region] ], Tags=[ { 'Key': 'aap-awscf-promotion', 'Value': 'deployed' }, ])
            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                print("Updated, ok")
            else:
                print(json.dumps(response, indent=4))
        except botocore.exceptions.ClientError as err2:
            if err2.response["Error"]["Code"] == "DryRunOperation":
                print("Dry run, ok")
            elif err2.response["Error"]["Code"] == "InvalidSnapshot.NotFound":
                print("Seems to be gone, guessing ok")
            else:
                print("Try of create_tags error: {}\n{}".format(json.dumps(err.response, indent=4), err1))
                success = False
    print("retagSNAPs exit, returning {}".format(success))
    return success


def main():

    # Reorient stdout to a string so we can capture it
    tmp_stdout = sys.stdout
    string_stdout = StringIO()
    sys.stdout = string_stdout

    # Prime the stdout pump - we seem to lose the first line otherwise
    print()

    os.environ["AWS_ACCESS_KEY_ID"] = env_set("INPUT_AWS_ACCESS_KEY_ID", "")
    os.environ["AWS_SECRET_ACCESS_KEY"] = env_set("INPUT_AWS_SECRET_ACCESS_KEY", "")
    os.environ["AWS_DEFAULT_REGION"] = env_set("INPUT_AWS_REGION", "us-east-2")

    snapshot_path = env_set("INPUT_SNAPSHOT_PATH", "")
    snapshot_date = env_set("INPUT_SNAPSHOT_DATE", "")
    log_filename = env_set("INPUT_LOG_FILENAME", "promotion.log")

    aws_account_id = whoami()
    ami_map = findAMIs(snapshot_path, snapshot_date)
    ec2_client_map = loginEC2Clients(ami_map)
    # print("Client map: \n{}".format(json.dumps(ec2_client_map, indent=4)))
    s3_client = loginS3Client(os.environ["AWS_DEFAULT_REGION"])
    snap_map = findSNAPs(ec2_client_map, ami_map)
    print("AWS account ID:\n{}".format(json.dumps(aws_account_id, indent=4)))
    print("AMI map:\n{}".format(json.dumps(ami_map, indent=4)))
    print("SNAP map:\n{}".format(json.dumps(snap_map, indent=4)))
    success = False
    success = retagAMIs(ec2_client_map, ami_map, "deployed")
    if success:
        success = retagSNAPs(ec2_client_map, snap_map, "deployed")
    # Reorient stdout back to normal, dump out what it was, and return value to action
    sys.stdout = tmp_stdout
    with open(log_filename, "w") as out_file:
        out_file.write(string_stdout.getvalue())
        out_file.close()
    print(f"::set-output name=log::{string_stdout.getvalue()}")
    exit(not success)


if __name__ == "__main__":
    main()
