# -----------------------------------------------------------------------------
# Lake Formation Permission Grants (Tag-Based Access Control)
# -----------------------------------------------------------------------------

# =============================================================================
# AdminRole Permissions
# =============================================================================

# Grant AdminRole ASSOCIATE and DESCRIBE on the SI LF-Tag so it can assign
# the tag to tables and views.
resource "aws_lakeformation_permissions" "admin_lf_tag" {
  principal   = aws_iam_role.admin.arn
  permissions = ["ASSOCIATE", "DESCRIBE"]

  lf_tag {
    key        = aws_lakeformation_lf_tag.si_tag.key
    values     = aws_lakeformation_lf_tag.si_tag.values
    catalog_id = local.account_id
  }

  depends_on = [
    aws_iam_role.admin,
    aws_lakeformation_lf_tag.si_tag,
  ]
}

# Grant AdminRole CREATE_TABLE and DESCRIBE on the database so it can create
# tables and views. The role gets implicit ALTER on resources it creates.
resource "aws_lakeformation_permissions" "admin_database" {
  principal   = aws_iam_role.admin.arn
  permissions = ["CREATE_TABLE", "DESCRIBE"]

  database {
    name       = aws_glue_catalog_database.lakehouse_db.name
    catalog_id = local.account_id
  }

  depends_on = [
    aws_iam_role.admin,
  ]
}

# Grant AdminRole ALL permissions (with grant option) on TABLE resources tagged
# with any SI value, covering both tables and views (views are TABLE resources
# in Lake Formation TBAC).
# resource "aws_lakeformation_permissions" "admin_tbac_table" {
#   principal                     = aws_iam_role.admin.arn
#   permissions                   = ["ALL"]
#   permissions_with_grant_option = ["ALL"]

#   lf_tag_policy {
#     resource_type = "TABLE"
#     catalog_id    = local.account_id

#     expression {
#       key    = aws_lakeformation_lf_tag.si_tag.key
#       values = aws_lakeformation_lf_tag.si_tag.values
#     }
#   }

#   depends_on = [
#     aws_iam_role.admin,
#     aws_lakeformation_lf_tag.si_tag,
#   ]
# }

resource "aws_lakeformation_permissions" "admin_all_tables" {
  principal                     = aws_iam_role.admin.arn
  permissions                   = ["ALL"]
  permissions_with_grant_option = ["ALL"]

  table {
    wildcard = true
    database_name = aws_glue_catalog_database.lakehouse_db.name
    catalog_id = local.account_id
  }

  depends_on = [
    aws_iam_role.admin,
    aws_lakeformation_lf_tag.si_tag,
  ]
}

# =============================================================================
# SIRole Permissions
# =============================================================================

# Grant SIRole DESCRIBE on the database (table-level access is handled via TBAC below).
resource "aws_lakeformation_permissions" "si_database" {
  principal   = aws_iam_role.si.arn
  permissions = ["DESCRIBE"]

  database {
    name       = aws_glue_catalog_database.lakehouse_db.name
    catalog_id = local.account_id
  }

  depends_on = [
    aws_lakeformation_lf_tag.si_tag,
    aws_iam_role.si,
  ]
}

# Grant SIRole SELECT on all TABLE resources tagged SI=true or SI=false via TBAC.
# SI users can query both the full table (SI=true) and the filtered view (SI=false).
resource "aws_lakeformation_permissions" "si_tbac_table" {
  principal   = aws_iam_role.si.arn
  permissions = ["SELECT"]

  lf_tag_policy {
    resource_type = "TABLE"
    catalog_id    = local.account_id

    expression {
      key    = aws_lakeformation_lf_tag.si_tag.key
      values = ["true", "false"]
    }
  }

  depends_on = [
    aws_lakeformation_lf_tag.si_tag,
    aws_iam_role.si,
  ]
}

# =============================================================================
# NonSIRole Permissions
# =============================================================================

# Grant NonSIRole DESCRIBE on the database.
resource "aws_lakeformation_permissions" "nonsi_database" {
  principal   = aws_iam_role.nonsi.arn
  permissions = ["DESCRIBE"]

  database {
    name       = aws_glue_catalog_database.lakehouse_db.name
    catalog_id = local.account_id
  }

  depends_on = [
    aws_lakeformation_lf_tag.si_tag,
    aws_iam_role.nonsi,
  ]
}

# Grant NonSIRole SELECT only on TABLE resources tagged SI=false via TBAC.
# NonSI users can only query the filtered view, not the raw SI-tagged table.
resource "aws_lakeformation_permissions" "nonsi_tbac_table" {
  principal   = aws_iam_role.nonsi.arn
  permissions = ["SELECT"]

  lf_tag_policy {
    resource_type = "TABLE"
    catalog_id    = local.account_id

    expression {
      key    = aws_lakeformation_lf_tag.si_tag.key
      values = ["false"]
    }
  }

  depends_on = [
    aws_lakeformation_lf_tag.si_tag,
    aws_iam_role.nonsi,
  ]
}

# =============================================================================
# LF-Tag Assignments
# =============================================================================

# Assign SI=false to the sample_data_view so we can assign tags to it later!
resource "aws_lakeformation_resource_lf_tags" "view_si_tag" {
  table {
    database_name = aws_glue_catalog_database.lakehouse_db.name
    name          = "sample_data_view"
    catalog_id    = local.account_id
  }

  lf_tag {
    key   = aws_lakeformation_lf_tag.si_tag.key
    value = "false"
  }

  depends_on = [
    aws_lakeformation_lf_tag.si_tag,
    aws_glue_catalog_database.lakehouse_db,
  ]
}
