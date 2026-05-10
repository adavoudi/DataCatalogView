variable "project_prefix" {
  description = "Prefix used for naming all resources"
  type        = string
  default     = "dcv"
}

variable "aws_region" {
  description = "AWS region for resource deployment"
  type        = string
  default     = "eu-central-1"
}
