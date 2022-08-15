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


def loginEC2Clients(ami_map):
    client_map = {}
    for region in ami_map:
        os.environ["AWS_DEFAULT_REGION"] = region
        client = boto3.client("ec2")
        element = {region: client}
        client_map.update(element)
    return client_map


def findAMIs(client_map, ami_name):
    ami_map = {}
    snap_map = {}
    for region in client_map:
        client = client_map[region]
        try:
            response = client.describe_images(Filters=[{'Name': 'name', 'Values': [ami_name]}])
            # print(json.dumps(response, indent=4))
            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                for image in response["Images"]:
                    # print(json.dumps(image, indent=4))
                    element = { region: image['ImageId'] }
                    ami_map.update(element)
                    # print(json.dumps(element, indent=4))
                    for blockDeviceMap in image["BlockDeviceMappings"]:
                        snap = blockDeviceMap["Ebs"]["SnapshotId"]
                        element = {region: snap}
                        snap_map.update(element)
        except:
            print("Nope, AMI {} isn't in this region, so we can't look up its snaps".format(ami_map[region]))
    return ami_map, snap_map


def deleteAMIs(client_map, ami_map):
    print("deleteAMIs entry")
    success = True
    for region in ami_map:
        try:
            print("Looking for {} in region {}:".format(ami_map[region], region))
            results = client_map[region].describe_images(ImageIds=[ami_map[region]])
            try:
                response = client_map[region].deregister_image(ImageId=ami_map[region], DryRun=False)
                if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                    print("Deleted, ok")
                else:
                    print(json.dumps(response, indent=4))
            except botocore.exceptions.ClientError as err2:
                if err2.response["Error"]["Code"] == "DryRunOperation":
                    print("Dry run, ok")
                elif err2.response["Error"]["Code"] == "InvalidAMIID.Unavailable":
                    print("Already gone, ok")
                else:
                    print("Try of deregister_image error: {}".format(err2))
                    success = False
        except botocore.exceptions.ClientError as err1:
            if err1.response["Error"]["Code"] == "InvalidAMIID.NotFound":
                print("AMI no longer present; continuing.")
            else:
                print("Try of describe_images error: {}\n{}".format(json.dumps(err1.response, indent=4), err1))
                success = False
    print("deleteAMIs exit, returning {}".format(success))
    return success


def deleteSNAPs(client_map, snap_map):
    print("deleteSNAPs entry")
    success = True
    for region in snap_map:
        try:
            print("Looking for {} in region {}:".format(snap_map[region], region))
            response = client_map[region].delete_snapshot(SnapshotId=snap_map[region], DryRun=False)
            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                print("Deleted, ok")
            else:
                print(json.dumps(response, indent=4))
        except botocore.exceptions.ClientError as err2:
            if err2.response["Error"]["Code"] == "DryRunOperation":
                print("Dry run, ok")
            elif err2.response["Error"]["Code"] == "InvalidSnapshot.NotFound":
                print("Already gone, ok")
            else:
                print("Try of delete_snapshot error: {}\n{}".format(json.dumps(err.response, indent=4), err1))
                success = False
    print("deleteSNAPs exit, returning {}".format(success))
    return success


def main():

    # Reorient stdout to a string so we can capture it
    tmp_stdout = sys.stdout
    string_stdout = StringIO()
    sys.stdout = string_stdout

    os.environ["AWS_ACCESS_KEY_ID"] = env_set("INPUT_AWS_ACCESS_KEY_ID", "")
    os.environ["AWS_SECRET_ACCESS_KEY"] = env_set("INPUT_AWS_SECRET_ACCESS_KEY", "")
    os.environ["AWS_DEFAULT_REGION"] = env_set("INPUT_AWS_REGION", "us-east-2")

    ami_name = env_set("INPUT_AMI_NAME", "")
    aws_regions = env_set("INPUT_AWS_REGIONS", "")

    regions = aws_regions.split(" ") 
    ec2_client_map = loginEC2Clients(regions)
    ami_map, snap_map = findAMIs(ec2_client_map, ami_name)
    # snap_map = findSNAPs(ec2_client_map, ami_map)
    print("AMI map:\n{}".format(json.dumps(ami_map, indent=4)))
    print("SNAP map:\n{}".format(json.dumps(snap_map, indent=4)))
    success = False
    success = deleteAMIs(ec2_client_map, ami_map)
    if success:
        success = deleteSNAPs(ec2_client_map, snap_map)

    # Reorient stdout back to normal, dump out what it was, and return value to action
    sys.stdout = tmp_stdout
    with open("reaper.log", "w") as out_file:
        out_file.write(string_stdout.getvalue())
        out_file.close()
    print(f"::set-output name=log::{string_stdout.getvalue()}")


if __name__ == "__main__":
    main()
