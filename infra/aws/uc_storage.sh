#!/usr/bin/env bash
# EDIP Gate 0 storage for Unity Catalog, via the AWS CLI.
# CloudFormation is denied by the account's organization policy (AWS Free plan), so this
# script creates the same resources directly and can be re-run safely.
#
#   infra/aws/uc_storage.sh up [EXTERNAL_ID]   create or update bucket and role
#   infra/aws/uc_storage.sh down               delete role; bucket kept unless --purge
#   infra/aws/uc_storage.sh down --purge       also delete every object version and the bucket
#
# Prints the bucket name and role ARN; never writes them to the repo.
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ROLE=edip-uc-storage
# Databricks-published Unity Catalog master role for AWS commercial regions.
UC_MASTER_ROLE="${UC_MASTER_ROLE:-arn:aws:iam::414351767826:role/unity-catalog-prod-UCMasterRole-14S5ZJVKOTYTL}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="edip-uc-${ACCOUNT}-${REGION}"
ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/${ROLE}"
TAGS='Key=project,Value=edip'

trust_policy() {
  local ext="$1"
  cat <<EOF
{"Version":"2012-10-17","Statement":[
 {"Sid":"UnityCatalogMaster","Effect":"Allow","Principal":{"AWS":"${UC_MASTER_ROLE}"},
  "Action":"sts:AssumeRole","Condition":{"StringEquals":{"sts:ExternalId":"${ext}"}}},
 {"Sid":"SelfAssume","Effect":"Allow","Principal":{"AWS":"arn:aws:iam::${ACCOUNT}:root"},
  "Action":"sts:AssumeRole","Condition":{"ArnEquals":{"aws:PrincipalArn":"${ROLE_ARN}"},
  "StringEquals":{"sts:ExternalId":"${ext}"}}}]}
EOF
}

access_policy() {
  cat <<EOF
{"Version":"2012-10-17","Statement":[
 {"Sid":"ObjectAccess","Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],
  "Resource":"arn:aws:s3:::${BUCKET}/*"},
 {"Sid":"BucketAccess","Effect":"Allow","Action":["s3:ListBucket","s3:GetBucketLocation",
  "s3:GetLifecycleConfiguration","s3:PutLifecycleConfiguration"],"Resource":"arn:aws:s3:::${BUCKET}"},
 {"Sid":"SelfAssume","Effect":"Allow","Action":"sts:AssumeRole","Resource":"${ROLE_ARN}"}]}
EOF
}

up() {
  local ext="${1:-pending}"
  if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
    if [ "$REGION" = us-east-1 ]; then
      aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null
    else
      aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
        --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
    fi
  fi
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-ownership-controls --bucket "$BUCKET" \
    --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'
  aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
  aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" --lifecycle-configuration \
    '{"Rules":[{"ID":"expire-noncurrent-versions","Status":"Enabled","Filter":{},
      "NoncurrentVersionExpiration":{"NoncurrentDays":30}},
     {"ID":"abort-incomplete-uploads","Status":"Enabled","Filter":{},
      "AbortIncompleteMultipartUpload":{"DaysAfterInitiation":1}}]}'
  aws s3api put-bucket-policy --bucket "$BUCKET" --policy \
    "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"DenyInsecureTransport\",\"Effect\":\"Deny\",
      \"Principal\":\"*\",\"Action\":\"s3:*\",\"Resource\":[\"arn:aws:s3:::${BUCKET}\",
      \"arn:aws:s3:::${BUCKET}/*\"],\"Condition\":{\"Bool\":{\"aws:SecureTransport\":\"false\"}}}]}"
  aws s3api put-bucket-tagging --bucket "$BUCKET" --tagging "TagSet=[{$TAGS}]"

  if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
    aws iam update-assume-role-policy --role-name "$ROLE" --policy-document "$(trust_policy "$ext")"
  else
    aws iam create-role --role-name "$ROLE" --tags "$TAGS" \
      --assume-role-policy-document "$(trust_policy "$ext")" >/dev/null
  fi
  aws iam put-role-policy --role-name "$ROLE" --policy-name edip-uc-bucket-access \
    --policy-document "$(access_policy)"
  echo "bucket:   $BUCKET"
  echo "role_arn: $ROLE_ARN"
  echo "external_id: $ext"
}

down() {
  aws iam delete-role-policy --role-name "$ROLE" --policy-name edip-uc-bucket-access 2>/dev/null || true
  aws iam delete-role --role-name "$ROLE" 2>/dev/null || true
  echo "role deleted"
  if [ "${1:-}" = "--purge" ]; then
    python3 - "$BUCKET" <<'PY'
import json, subprocess, sys
bucket = sys.argv[1]
while True:
    out = subprocess.run(["aws", "s3api", "list-object-versions", "--bucket", bucket,
                          "--max-items", "1000", "--output", "json"],
                         check=True, capture_output=True, text=True).stdout
    data = json.loads(out or "{}")
    objs = [{"Key": o["Key"], "VersionId": o["VersionId"]}
            for o in data.get("Versions", []) + data.get("DeleteMarkers", [])]
    if not objs:
        break
    subprocess.run(["aws", "s3api", "delete-objects", "--bucket", bucket, "--delete",
                    json.dumps({"Objects": objs, "Quiet": True})], check=True)
PY
    aws s3api delete-bucket --bucket "$BUCKET"
    echo "bucket deleted"
  else
    echo "bucket kept: run 'down --purge' at Gate 7 after exports"
  fi
}

case "${1:-}" in
  up) up "${2:-pending}" ;;
  down) down "${2:-}" ;;
  *) echo "usage: $0 up [EXTERNAL_ID] | down [--purge]" >&2; exit 2 ;;
esac
