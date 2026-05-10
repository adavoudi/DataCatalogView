# -----------------------------------------------------------------------------
# Lake Formation Configuration
# -----------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

# Configure Lake Formation data lake settings — set Terraform executor as admin
resource "aws_lakeformation_data_lake_settings" "admin" {
  catalog_id = local.account_id

  admins = [
    data.aws_caller_identity.current.arn  
  ]
}

# Register the data lake S3 bucket with Lake Formation
resource "aws_lakeformation_resource" "data_lake" {
  arn = aws_s3_bucket.data_lake.arn

  # Use the IAM role/user that Lake Formation assumes to access the data
  # use_service_linked_role = true
}

# Create LF-Tag: SI with values "true" and "false"
resource "aws_lakeformation_lf_tag" "si_tag" {
  catalog_id = local.account_id
  key        = "SI"
  values     = ["true", "false"]

  depends_on = [aws_lakeformation_data_lake_settings.admin]
}
