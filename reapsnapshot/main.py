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


def loginS3Clients(ami_map):
    client_map = {}
    for region in ami_map:
        os.environ["AWS_DEFAULT_REGION"] = region
        client = boto3.client("s3")
        element = {region: client}
        client_map.update(element)
    return client_map


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


def findS3Filenames(s3_client_map, snapshot_path, snapshot_date):
    s3_filename_list = []
    try:
        with open("{}/s3_file_locations.txt".format(snapshot_path), "r") as lambda_file:
            lambda_text = lambda_file.readlines()
            for line in lambda_text:
                s3_filename_list.append(line.strip())
    except:
        print("Didn't find {}/s3_file_locations.txt; assuming positronic-asimov for S3 bucket.".format(snapshot_path))
        for region in s3_client_map:
            s3_filename_list.append("s3://positronic-asimov-{}/functions/controller-{}.zip".format(region, snapshot_date))
            s3_filename_list.append("s3://positronic-asimov-{}/functions/efs-{}.zip".format(region, snapshot_date))
            s3_filename_list.append("s3://positronic-asimov-{}/functions/rds-{}.zip".format(region, snapshot_date))
            s3_filename_list.append("s3://positronic-asimov-{}/cdk/template-production-{}.json".format(region, snapshot_date))
            s3_filename_list.append("s3://positronic-asimov-{}/cdk/template-development-{}.json".format(region, snapshot_date))
    return s3_filename_list


def deleteAMIs(client_map, ami_map):
    print("deleteAMIs entry")
    success = True
    for region in ami_map:
        try:
            print("Looking for {} in region {}:".format(ami_map[region], region))
            results = client_map[region].describe_images(ImageIds=[ami_map[region]])
            try:
                response = client_map[region].deregister_image(ImageId=ami_map[region], DryRun=False)
                if response['ResponseMetadata']['HTTPStatusCode'] == 200:
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
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
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


def deleteS3Files(s3_client_map, s3_filename_list):
    print("deleteS3Files entry")
    success = True
    for s3_file in s3_filename_list:
        # Break up an S3 URI into usable bits i.e.
        # s3://positronic-asimov-us-west-2/cdk/template-development-2022-07-12-10-44-52.json
        # --> positronic-asimov-us-west-2 --> cdk/template-development-2022-07-12-10-44-52.json
        parts = s3_file.split("s3://")
        bucket = parts[1].split("/")[0]
        start = len(bucket)+s3_file.find(bucket)+1
        key = s3_file[start:]
        print("Looking for S3 bucket: {} key: {}".format(bucket, key))
        try:
            response = s3_client_map[os.environ["AWS_DEFAULT_REGION"]].delete_object(Bucket=bucket, Key=key)
            if response['ResponseMetadata']['HTTPStatusCode'] == 204:
                print("Deleted, ok")
            else:
                print(json.dumps(response, indent=4))
        except botocore.exceptions.ClientError as err1:
            if err1.response["Error"]["Code"] == "404":
                print("Missing, ok")
            elif err1.response["Error"]["Code"] == "NoSuchBucket":
                print("Entire bucket missing, ok")
            else:
                success = False
                print("Try of delete_object {}/{} error: {}\n{}".format(bucket, key, json.dumps(err1.response, indent=4), err1))
    print("deleteS3Files exit, returning {}".format(success))
    return success


def main():

    # Reorient stdout to a string so we can capture it
    tmp_stdout = sys.stdout
    string_stdout = StringIO()
    sys.stdout = string_stdout

    os.environ["AWS_ACCESS_KEY_ID"] = env_set("INPUT_AWS_ACCESS_KEY_ID", "")
    os.environ["AWS_SECRET_ACCESS_KEY"] = env_set("INPUT_AWS_SECRET_ACCESS_KEY", "")
    os.environ["AWS_DEFAULT_REGION"] = env_set("INPUT_AWS_REGION", "us-east-2")

    snapshot_path = env_set("INPUT_SNAPSHOT_PATH", "")
    snapshot_date = env_set("INPUT_SNAPSHOT_DATE", "")

    ami_map = findAMIs(snapshot_path, snapshot_date)
    ec2_client_map = loginEC2Clients(ami_map)
    # print("Client map: \n{}".format(json.dumps(ec2_client_map, indent=4)))
    s3_client_map = loginS3Clients(ami_map)
    snap_map = findSNAPs(ec2_client_map, ami_map)
    s3_filename_list = findS3Filenames(s3_client_map, snapshot_path, snapshot_date)
    print("AMI map:\n{}".format(json.dumps(ami_map, indent=4)))
    print("SNAP map:\n{}".format(json.dumps(snap_map, indent=4)))
    print("S3 filename list:\n{}".format(json.dumps(s3_filename_list, indent=4)))
    success = False
    success = deleteAMIs(ec2_client_map, ami_map)
    if success:
        success = deleteSNAPs(ec2_client_map, snap_map)
        if success:
            success = deleteS3Files(s3_client_map, s3_filename_list)

    # Reorient stdout back to normal, dump out what it was, and return value to action
    sys.stdout = tmp_stdout
    print(string_stdout.getvalue())
    print(f"::set-output name=log::{string_stdout}")

if __name__ == "__main__":
    main()