provider "aws" {
  region  = var.aws_region
  profile = "default"

  default_tags {
    tags = {
      Project     = var.project_prefix
      ManagedBy   = "terraform"
      Environment = "dev"
    }
  }
}

locals {
  name_prefix = var.project_prefix
  account_id  = data.aws_caller_identity.current.account_id
  region      = var.aws_region
}
