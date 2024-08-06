variable "region" {
  default = "us-east-1"  # Change this to your preferred region
}

provider "aws" {
  region = var.region
}

resource "aws_vpc" "batch_vpc" {
  cidr_block = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = {
    Name = "batch-vpc"
  }
}

resource "aws_subnet" "batch_subnet" {
  vpc_id     = aws_vpc.batch_vpc.id
  cidr_block = "10.0.1.0/24"
  tags = {
    Name = "batch-subnet"
  }
}

resource "aws_internet_gateway" "batch_igw" {
  vpc_id = aws_vpc.batch_vpc.id
  tags = {
    Name = "batch-igw"
  }
}

resource "aws_route_table" "batch_rt" {
  vpc_id = aws_vpc.batch_vpc.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.batch_igw.id
  }
  tags = {
    Name = "batch-rt"
  }
}

resource "aws_route_table_association" "batch_rta" {
  subnet_id      = aws_subnet.batch_subnet.id
  route_table_id = aws_route_table.batch_rt.id
}

resource "aws_security_group" "batch_sg" {
  name        = "batch-sg"
  description = "Security group for Batch jobs"
  vpc_id      = aws_vpc.batch_vpc.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = {
    Name = "batch-sg"
  }
}

resource "aws_batch_compute_environment" "batch_compute_env" {
  compute_environment_name = "heat-risk-dashboard-batch-compute-env"
  compute_resources {
    max_vcpus = 32
    security_group_ids = [aws_security_group.batch_sg.id]
    subnets = [aws_subnet.batch_subnet.id]
    type = "FARGATE"
  }
  service_role = aws_iam_role.batch_service_role.arn
  type         = "MANAGED"
  depends_on   = [aws_iam_role_policy_attachment.batch_service_role]
}

resource "aws_batch_job_queue" "batch_job_queue" {
  name     = "heat-risk-dashboard-batch-job-queue"
  state    = "ENABLED"
  priority = 1
  compute_environment_order {
    order = 0
    compute_environment = aws_batch_compute_environment.batch_compute_env.arn
  }
}

resource "aws_iam_role" "batch_service_role" {
  name = "batch-service-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "batch.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "batch_service_role" {
  role       = aws_iam_role.batch_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole"
}

resource "aws_ecr_repository" "batch_repo" {
  name                 = "batch-repo"
  image_tag_mutability = "MUTABLE"
}

resource "aws_iam_role" "batch_job_role" {
  name = "batch-job-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_policy" "batch_job_policy" {
  name        = "batch-job-execution-policy"
  path        = "/"
  description = "Policy for Batch job execution"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::heat-risk-dashboard",
          "arn:aws:s3:::heat-risk-dashboard/*",
          "*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "batch_job_policy_attachment" {
  role       = aws_iam_role.batch_job_role.name
  policy_arn = aws_iam_policy.batch_job_policy.arn
}

resource "aws_batch_job_definition" "batch_job_def" {
  name = "heat-risk-dashboard-batch-job-def"
  type = "container"
  
  container_properties = jsonencode({
    image = "${aws_ecr_repository.batch_repo.repository_url}:latest"
    resourceRequirements = [
      { type = "VCPU", value = "8" },
      { type = "MEMORY", value = "61440" }
    ]
    executionRoleArn = aws_iam_role.batch_job_role.arn
    jobRoleArn       = aws_iam_role.batch_job_role.arn
    fargatePlatformConfiguration = {
      platformVersion = "LATEST"
    }
    networkConfiguration = {
      assignPublicIp = "ENABLED"
    }
  })
  platform_capabilities = ["FARGATE"]
}

resource "aws_s3_bucket" "heat_risk_dashboard" {
  bucket = "heat-risk-dashboard"
}

resource "aws_s3_bucket_public_access_block" "heat_risk_dashboard" {
  bucket = aws_s3_bucket.heat_risk_dashboard.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "allow_public_read" {
  bucket = aws_s3_bucket.heat_risk_dashboard.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = [
          aws_s3_bucket.heat_risk_dashboard.arn,
          "${aws_s3_bucket.heat_risk_dashboard.arn}/*",
        ]
      },
    ]
  })
}

# New resources for scheduling

resource "aws_cloudwatch_event_rule" "batch_job_schedule" {
  name                = "batch-job-daily-schedule"
  description         = "Triggers Batch job daily at 12:01 AM New York time"
  schedule_expression = "cron(1 5 * * ? *)"  # 12:01 AM ET is 5:01 AM UTC
}

resource "aws_cloudwatch_event_target" "batch_job_target" {
  rule      = aws_cloudwatch_event_rule.batch_job_schedule.name
  arn       = aws_batch_job_queue.batch_job_queue.arn
  role_arn  = aws_iam_role.events_batch_role.arn

  batch_target {
    job_definition = aws_batch_job_definition.batch_job_def.arn
    job_name       = "scheduled-batch-job"
  }
}

resource "aws_iam_role" "events_batch_role" {
  name = "events-batch-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "events_batch_policy" {
  role       = aws_iam_role.events_batch_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBatchServiceEventTargetRole"
}

# Outputs for use in the build_and_push.sh script
output "region" {
  value = var.region
}

output "ecr_repository_url" {
  value = aws_ecr_repository.batch_repo.repository_url
}