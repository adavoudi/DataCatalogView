variable "project_prefix" {
  description = "Prefix used for naming all resources"
  type        = string
  default     = "dcv"
}

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR block for the Redshift VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "subnet_cidr" {
  description = "CIDR block for the Redshift subnet (AZ 0)"
  type        = string
  default     = "10.0.1.0/24"
}

variable "subnet_cidr_b" {
  description = "CIDR block for the Redshift subnet (AZ 1)"
  type        = string
  default     = "10.0.2.0/24"
}

variable "redshift_base_capacity" {
  description = "Base RPU capacity for the Redshift Serverless Workgroup (minimum: 8)"
  type        = number
  default     = 8
}

variable "redshift_max_capacity" {
  description = "Maximum RPU capacity for the Redshift Serverless Workgroup — set equal to base_capacity to disable auto-scaling and cap costs at ~$2.88/hour"
  type        = number
  default     = 8
}
