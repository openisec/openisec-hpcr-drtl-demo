variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "openisec-demo-488314"
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "asia-northeast1"
}

variable "environment" {
  description = "Environment name (dev, stg, prd)"
  type        = string
  default     = "demo"

  validation {
    condition     = contains(["dev", "stg", "demo"], var.environment)
    error_message = "environment must be dev, stg, or demo."
  }
}

variable "db_tier" {
  description = "Cloud SQL instance tier"
  type        = string
  default     = "db-g1-small"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "openisec"
}

variable "vpc_network_id" {
  description = "VPC network ID for private IP"
  type        = string
  default     = null
}