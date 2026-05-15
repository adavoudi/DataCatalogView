# -----------------------------------------------------------------------------
# RedshiftSpectrumRole - Catalog resolution and data access for Redshift Spectrum
# -----------------------------------------------------------------------------

resource "aws_iam_role" "redshift_spectrum" {
  name = "${local.name_prefix}_RedshiftSpectrumRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "redshift.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "redshift_spectrum_glue" {
  name = "${local.name_prefix}_redshift-spectrum-glue"
  role = aws_iam_role.redshift_spectrum.id

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
          "glue:GetPartition",
          "glue:GetPartitions",
          "glue:UpdateTable"
        ]
        Resource = [
          "arn:aws:glue:${local.region}:${local.account_id}:catalog",
          "arn:aws:glue:${local.region}:${local.account_id}:database/${aws_glue_catalog_database.lakehouse_db.name}",
          "arn:aws:glue:${local.region}:${local.account_id}:table/${aws_glue_catalog_database.lakehouse_db.name}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "lakeformation:GetDataAccess"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "redshift_spectrum_s3" {
  name = "${local.name_prefix}_redshift-spectrum-s3"
  role = aws_iam_role.redshift_spectrum.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          aws_s3_bucket.data_lake.arn,
          "${aws_s3_bucket.data_lake.arn}/*"
        ]
      }
    ]
  })
}
