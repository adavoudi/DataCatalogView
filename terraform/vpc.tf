# -----------------------------------------------------------------------------
# Availability Zones
# -----------------------------------------------------------------------------

data "aws_availability_zones" "available" {
  state = "available"
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------

resource "aws_vpc" "redshift" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true

  tags = {
    Name = "${local.name_prefix}-redshift-vpc"
  }
}

# -----------------------------------------------------------------------------
# Subnet (AZ 0)
# -----------------------------------------------------------------------------

resource "aws_subnet" "redshift" {
  vpc_id            = aws_vpc.redshift.id
  cidr_block        = var.subnet_cidr
  availability_zone = data.aws_availability_zones.available.names[0]

  tags = {
    Name = "${local.name_prefix}-redshift-subnet-0"
  }
}

# -----------------------------------------------------------------------------
# Subnet (AZ 1) — Redshift Serverless requires subnets in at least 2 AZs
# -----------------------------------------------------------------------------

resource "aws_subnet" "redshift_b" {
  vpc_id            = aws_vpc.redshift.id
  cidr_block        = var.subnet_cidr_b
  availability_zone = data.aws_availability_zones.available.names[1]

  tags = {
    Name = "${local.name_prefix}-redshift-subnet-1"
  }
}

# -----------------------------------------------------------------------------
# Internet Gateway
# -----------------------------------------------------------------------------

resource "aws_internet_gateway" "redshift" {
  vpc_id = aws_vpc.redshift.id

  tags = {
    Name = "${local.name_prefix}-redshift-igw"
  }
}

# -----------------------------------------------------------------------------
# Route Table
# -----------------------------------------------------------------------------

resource "aws_route_table" "redshift" {
  vpc_id = aws_vpc.redshift.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.redshift.id
  }

  tags = {
    Name = "${local.name_prefix}-redshift-rt"
  }
}

resource "aws_route_table_association" "redshift_a" {
  subnet_id      = aws_subnet.redshift.id
  route_table_id = aws_route_table.redshift.id
}

resource "aws_route_table_association" "redshift_b" {
  subnet_id      = aws_subnet.redshift_b.id
  route_table_id = aws_route_table.redshift.id
}

# -----------------------------------------------------------------------------
# Security Group
# -----------------------------------------------------------------------------

resource "aws_security_group" "redshift" {
  name        = "${local.name_prefix}-redshift-sg"
  description = "Allow Redshift Serverless inbound traffic from VPC and all outbound traffic"
  vpc_id      = aws_vpc.redshift.id

  ingress {
    description = "Redshift port - open to internet (dev/test only)"
    from_port   = 5439
    to_port     = 5439
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${local.name_prefix}-redshift-sg"
  }
}
