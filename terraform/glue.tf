# -----------------------------------------------------------------------------
# Glue Catalog Database
# -----------------------------------------------------------------------------

resource "aws_glue_catalog_database" "lakehouse_db" {
  name       = "${local.name_prefix}_db"
  catalog_id = local.account_id

  location_uri = "s3://${aws_s3_bucket.data_lake.id}/"
}
