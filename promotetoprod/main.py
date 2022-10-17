import os
import boto3
import json
from io import StringIO
import sys
import base64


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


def moveS3s(snapshot_path, snapshot_date, dev_region, prod_region, prod_bucket):
    return_code = False
    dev_session = boto3.Session(profile_name="dev", region_name=dev_region)
    prod_session = boto3.Session(profile_name="prod", region_name=prod_region)
    resource_map = {}
    try:
        with open("{}/resources-{}.json".format(snapshot_path, snapshot_date), "r") as s3_file:
            resource_text = s3_file.read()
            resource_map = json.loads(resource_text)
        s3_files = resource_map["s3_files"]
        dev_client = dev_session.client("s3")
        prod_client = prod_session.client("s3")
        for entry in s3_files:
            if "{}/".format(dev_region) in entry:
                # Break up an S3 URI into usable bits i.e.
                # s3://positronic-asimov-us-west-2/cdk/template-development-2022-07-12-10-44-52.json
                #   bucket --> positronic-asimov-us-west-2
                #      obj --> cdk/template-development-2022-07-12-10-44-52.json
                parts = entry.split("s3://")
                bucket = parts[1].split("/")[0]
                start = len(bucket) + entry.find(bucket) + 1
                obj = entry[start:]
                file = obj.split("/")[1]
                dev_client.download_file(bucket, obj, file)
                print("Downloaded {} from {}".format(obj, bucket))
                prod_client.upload_file(file, prod_bucket, obj)
                print("Uploaded {} to {}".format(obj, prod_bucket))
        return_code = True
    except:
        print("Didn't find {}/resources-{}.json!".format(snapshot_path, snapshot_date))
    return return_code


def loginS3Client():
    client = boto3.client("s3")
    return client


def main():

    # Reorient stdout to a string so we can capture it
    tmp_stdout = sys.stdout
    string_stdout = StringIO()
    sys.stdout = string_stdout

    # Assumes a credentials file has been laid down thusly
    os.environ["AWS_SHARED_CREDENTIALS_FILE"] = "{}/.aws/credentials".format(os.getcwd())

    # Prime the stdout pump - we seem to lose the first line otherwise
    print()

    snapshot_path = env_set("INPUT_SNAPSHOT_PATH", "")
    snapshot_date = env_set("INPUT_SNAPSHOT_DATE", "")
    log_filename = env_set("INPUT_LOG_FILENAME", "prod-promote.log")
    dev_region = env_set("INPUT_AWS_DEV_ENDPOINT_REGION", "us-east-2")
    prod_region = env_set("INPUT_AWS_PROD_ENDPOINT_REGION", "us-east-2")
    prod_s3_bucket = env_set("INPUT_AWS_PROD_S3_BUCKET", "aap-aoc-code-assets")
    aws_creds_text = base64.b64decode(os.environ["INPUT_AWS_SHARED_CREDS_BASE64"]).decode("utf-8")
    creds_path = "{}/.aws".format(os.getcwd())
    os.mkdir(creds_path)
    creds_file = "{}/credentials".format(creds_path)
    with open(creds_file, "w") as out_file:
        out_file.write(aws_creds_text)
        out_file.close()

    success = moveS3s(snapshot_path, snapshot_date, dev_region, prod_region, prod_s3_bucket)

    # Reorient stdout back to normal, dump out what it was, and return value to action
    sys.stdout = tmp_stdout
    with open(log_filename, "a") as out_file:
        out_file.write(string_stdout.getvalue())
        out_file.close()
    exit(not success)


if __name__ == "__main__":
    main()
