output "account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "AWS region where resources are deployed"
  value       = var.aws_region
}

output "data_lake_bucket_name" {
  description = "Name of the data lake S3 bucket"
  value       = aws_s3_bucket.data_lake.id
}

output "query_results_bucket_name" {
  description = "Name of the Athena query results S3 bucket"
  value       = aws_s3_bucket.query_results.id
}

output "database_name" {
  description = "Name of the Glue catalog database"
  value       = aws_glue_catalog_database.lakehouse_db.name
}

output "workgroup_name" {
  description = "Name of the Athena workgroup"
  value       = aws_athena_workgroup.lakehouse.name
}

output "admin_role_arn" {
  description = "ARN of the AdminRole IAM role"
  value       = aws_iam_role.admin.arn
}

output "si_role_arn" {
  description = "ARN of the SIRole IAM role"
  value       = aws_iam_role.si.arn
}

output "nonsi_role_arn" {
  description = "ARN of the NonSIRole IAM role"
  value       = aws_iam_role.nonsi.arn
}
