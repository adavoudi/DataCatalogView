# -----------------------------------------------------------------------------
# Redshift Serverless Namespace
# -----------------------------------------------------------------------------

resource "aws_redshiftserverless_namespace" "main" {
  namespace_name        = "${local.name_prefix}-namespace"
  manage_admin_password = true
  iam_roles             = [aws_iam_role.redshift_spectrum.arn]
}

# -----------------------------------------------------------------------------
# Redshift Serverless Workgroup
# -----------------------------------------------------------------------------

resource "aws_redshiftserverless_workgroup" "main" {
  workgroup_name     = "${local.name_prefix}-workgroup"
  namespace_name     = aws_redshiftserverless_namespace.main.namespace_name
  subnet_ids         = [aws_subnet.redshift.id, aws_subnet.redshift_b.id]
  security_group_ids = [aws_security_group.redshift.id]
  publicly_accessible = true
  base_capacity      = var.redshift_base_capacity
  max_capacity       = var.redshift_max_capacity
}
