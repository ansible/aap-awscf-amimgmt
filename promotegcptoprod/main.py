import os
import json
from io import StringIO
import sys
import base64
import subprocess


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


def copyAssets(snapshot_path, snapshot_date, prod_store_path):
    return_code = False
    resource_map = {}
    image_name = ""
    for dirname in next(os.walk(snapshot_path))[1]:
        object_storage = ""
        account_copied_to = ""
        account_destined_for = ""
        try:
            full_path="{}/{}/gcp-machine-image-manifest.json".format(snapshot_path,dirname)
            with open(full_path, "r") as a_file:
                resource_text = a_file.read()
                resource_map = json.loads(resource_text)
                image_name = resource_map["builds"][0]["artifact_id"]
            # print("full_path: {}".format(full_path))
        except:
            try:
                full_path="{}/{}/gcp-machine-image-manifest_{}.json".format(snapshot_path,dirname,snapshot_date)
                with open(full_path, "r") as a_file:
                    resource_text = a_file.read()
                    resource_map = json.loads(resource_text)
                    image_name = resource_map["builds"][0]["artifact_id"]
                # print("full_path: {}".format(full_path))
            except:
                print("Didn't find the image created in {}/{}!".format(snapshot_path,dirname))
        try:
            full_path="{}/{}/gcp_project_id.txt".format(snapshot_path,dirname)
            with open(full_path, "r") as a_file:
                account_copied_to = a_file.read().strip()
            # print("    sub-build {} account copied to: {}".format(dirname,account_copied_to))
        except:
            account_copied_to = 'gc-ansible-cloud'
            print("Didn't find the gcp project stuff for sub-build {}, assuming '{}'".format(dirname,account_copied_to))
        try:
            full_path="{}/{}/destination_project_id.txt".format(snapshot_path,dirname)
            with open(full_path, "r") as a_file:
                account_destined_for = a_file.read().strip()
            # print("account destined for: {}".format(account_destined_for))
        except:
            print("Didn't find the destination gcp project ID for sub-build {}, assuming {}".format(dirname,account_copied_to))
            account_destined_for = account_copied_to
        try:
            full_path="{}/{}/object-storage.out".format(snapshot_path,dirname)
            with open(full_path, "r") as a_file:
                object_storage = a_file.read().strip()
            # print("account destined for: {}".format(account_destined_for))
        except:
            print("No object storage exists for sub-build {}.".format(dirname));
        if (account_destined_for != account_copied_to) & (image_name != ""):
            print("Copying sub-build {} image {} to {} since account_destined_for is {} and account_copied_to is {}.".format(dirname,image_name, account_destined_for,account_copied_to,account_destined_for))
            print("gcloud compute --project={} images create {} --source-image={} --source-image-project={}".format(account_destined_for, image_name, image_name, account_copied_to))
            process = subprocess.run(["gcloud", 
                "compute", 
                "--project={}".format(account_destined_for), 
                "images", 
                "create", 
                "{}".format(image_name), 
                "--source-image={}".format(image_name), 
                "--source-image-project={}".format(account_copied_to)],
                capture_output=True, 
                text=True)
            if (process.stdout != ''): print(process.stdout)
            if (process.stderr != ''): print(process.stderr)
        if (account_destined_for != account_copied_to) & (object_storage != ""):
            print("Copying sub-build {} zip   {} to {}".format(dirname,object_storage, account_destined_for))
            head, tail = os.path.split(object_storage)
            print("gsutil cp {} gs://{}/{}".format(object_storage, prod_store_path, tail))
            process = subprocess.run(["gsutil", "cp", "{}".format(object_storage), "gs://{}/{}".format(prod_store_path, tail)], capture_output=True, text=True)
            if (process.stdout != ''): print(process.stdout)
            if (process.stderr != ''): print(process.stderr)


        return_code = True
    return return_code


def main():

    # Reorient stdout to a string so we can capture it
    tmp_stdout = sys.stdout
    string_stdout = StringIO()
    sys.stdout = string_stdout

    # Prime the stdout pump - we seem to lose the first line otherwise
    print()

    snapshot_path = env_set("INPUT_SNAPSHOT_PATH", "")
    snapshot_date = env_set("INPUT_SNAPSHOT_DATE", "")
    log_filename = env_set("INPUT_LOG_FILENAME", "promotegcptoprod.log")
    prod_store_path = env_set("INPUT_GCP_PROD_STORAGE_PATH", "aap-aoc-code-assets")
    gcloud_path = env_set("INPUT_GCLOUD_PATH", "/opt/hostedtoolcache/gcloud/411.0.0/x64/bin/gcloud")

    process = subprocess.run(["{}".format(gcloud_path), "auth", "list"], capture_output=True, text=True)
    if (process.stdout != ''): print(process.stdout)
    if (process.stderr != ''): print(process.stderr)
    success = copyAssets(snapshot_path, snapshot_date, prod_store_path)

    # Reorient stdout back to normal, dump out what it was, and return value to action
    sys.stdout = tmp_stdout
    with open(log_filename, "a") as out_file:
        out_file.write(string_stdout.getvalue())
        out_file.close()
    exit(not success)


if __name__ == "__main__":
    main()
