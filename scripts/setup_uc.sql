-- Gate 0 Unity Catalog setup. Run on a SQL warehouse as a metastore admin.
-- Replace ${bucket} and ${role_arn} with the CloudFormation stack outputs; do not commit
-- the substituted file (it contains the AWS account ID).
--
-- Step 1: create the storage credential in Catalog Explorer or with
--   databricks storage-credentials create --json '{"name":"edip_s3","aws_iam_role":{"role_arn":"${role_arn}"}}'
-- then read its external ID with
--   databricks storage-credentials get edip_s3
-- and redeploy the stack with ExternalId set to that value.

-- Step 2: external location and catalog.
CREATE EXTERNAL LOCATION IF NOT EXISTS edip_root
  URL 's3://${bucket}/uc'
  WITH (STORAGE CREDENTIAL edip_s3)
  COMMENT 'EDIP managed storage (Gate 0)';

CREATE CATALOG IF NOT EXISTS edip
  MANAGED LOCATION 's3://${bucket}/uc/edip'
  COMMENT 'Energy Decision Intelligence Platform';

-- Schemas raw, curated, ml, eval are created by the bundle (resources/schemas.yml).
