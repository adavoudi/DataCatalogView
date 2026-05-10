# -----------------------------------------------------------------------------
# AdminRole - Full database write access and SI tag management
# -----------------------------------------------------------------------------

resource "aws_iam_role" "admin" {
  name = "${local.name_prefix}_AdminRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Required for SECURITY DEFINER views: Glue assumes this role at query
        # time to resolve the view on behalf of the definer (AdminRole).
        Sid    = "AllowGlueAssumeRoleForViewDefiner"
        Effect = "Allow"
        Principal = {
          Service = "glue.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      },
      {
        # Allows IAM principals in this account (e.g. the Python scripts via STS)
        # to assume AdminRole.
        Sid    = "AllowIAMPrincipalsAssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${local.account_id}:root"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# iam:PassRole scoped to this role only, for Glue and Lake Formation
resource "aws_iam_role_policy" "admin_pass_role" {
  name = "${local.name_prefix}_admin-pass-role"
  role = aws_iam_role.admin.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DataCatalogViewDefinerPassRole1"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = aws_iam_role.admin.arn
        Condition = {
          StringEquals = {
            "iam:PassedToService" = [
              "glue.amazonaws.com",
              "lakeformation.amazonaws.com"
            ]
          }
        }
      }
    ]
  })
}

# Athena execution permissions scoped to the provisioned workgroup
resource "aws_iam_role_policy" "admin_athena" {
  name = "${local.name_prefix}_admin-athena"
  role = aws_iam_role.admin.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "athena:StartQueryExecution",
          "athena:StopQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:GetWorkGroup",
          "athena:BatchGetQueryExecution"
        ]
        Resource = "arn:aws:athena:${local.region}:${local.account_id}:workgroup/${local.name_prefix}_workgroup"
      }
    ]
  })
}

# S3 read/write on data lake and query results buckets
resource "aws_iam_role_policy" "admin_s3" {
  name = "${local.name_prefix}_admin-s3"
  role = aws_iam_role.admin.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/*",
          aws_s3_bucket.query_results.arn,
          "${aws_s3_bucket.query_results.arn}/*"
        ]
      }
    ]
  })
}

# Lake Formation permissions scoped to what AdminRole actually needs:
# - GetDataAccess: required by Athena/Glue to read LF-governed data
# - AddLFTagsToResource / RemoveLFTagsFromResource: assign/revoke SI tags on tables and columns
# - GetResourceLFTags: verify tag assignments
# - ListLFTags / GetLFTag: enumerate available tags
resource "aws_iam_role_policy" "admin_lakeformation" {
  name = "${local.name_prefix}_admin-lakeformation"
  role = aws_iam_role.admin.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lakeformation:GetDataAccess",
          "lakeformation:AddLFTagsToResource",
          "lakeformation:RemoveLFTagsFromResource",
          "lakeformation:GetResourceLFTags",
          "lakeformation:ListLFTags",
          "lakeformation:GetLFTag",
          "lakeformation:SearchTablesByLFTags",
          "lakeformation:SearchDatabasesByLFTags"
        ]
        Resource = "*"
      }
    ]
  })
}

# Glue catalog permissions scoped to table/view management in the lakehouse database
resource "aws_iam_role_policy" "admin_glue" {
  name = "${local.name_prefix}_admin-glue"
  role = aws_iam_role.admin.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:GetTable",
          "glue:GetTables",
          "glue:CreateTable",
          "glue:UpdateTable",
          "glue:DeleteTable",
          "glue:GetPartition",
          "glue:GetPartitions",
          "glue:BatchCreatePartition",
          "glue:BatchDeletePartition"
        ]
        Resource = [
          "arn:aws:glue:${local.region}:${local.account_id}:catalog",
          "arn:aws:glue:${local.region}:${local.account_id}:database/${aws_glue_catalog_database.lakehouse_db.name}",
          "arn:aws:glue:${local.region}:${local.account_id}:table/${aws_glue_catalog_database.lakehouse_db.name}/*"
        ]
      }
    ]
  })
}
