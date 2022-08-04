import os


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


def main():
  # snapshot_path:
  #   description: "Path to snapshot to reap"
  #   required: true
  #   default: "artifacts/snapshots/SNAPSHOT-2021-08-01-19-23-28"
  # aws_profile:
  #   description: 'AWS profile'
  #   required: true
  #   default: 'aws-acm-dev10'
  # aws_access_key_id:
  #   description: 'AWS access key ID'
  #   required: true
  #   default: ''
  # aws_secret_access_key:
  #   description: 'AWS secret access key'
  #   required: true
  #   default: ''

  snapshot_path = env_set("snapshot_path","")
  aws_profile = env_set("aws_profile","")

  my_output = f"snapshot_path: {my_input}; aws_profile: {aws_profile}"

  print(f"::set-output name=myOutput::{my_output}")


if __name__ == "__main__":
  main()
