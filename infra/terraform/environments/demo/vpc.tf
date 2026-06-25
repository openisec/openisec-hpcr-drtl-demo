# VPC Network
resource "google_compute_network" "vpc" {
  name                    = "openisec-vpc-${var.environment}"
  auto_create_subnetworks = false
  project                 = var.project_id
}

resource "google_compute_subnetwork" "subnet" {
  name          = "openisec-subnet-${var.environment}"
  ip_cidr_range = "10.0.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id
  project       = var.project_id
}

# Private Services Access (Cloud SQL private IP用)
resource "google_compute_global_address" "private_ip_range" {
  name          = "openisec-private-ip-${var.environment}"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
  project       = var.project_id
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range.name]
}

# VPC Access Connector (Cloud Run → Cloud SQL private IP)
resource "google_vpc_access_connector" "connector" {
  name          = "openisec-connector-${var.environment}"
  region        = var.region
  project       = var.project_id
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.8.0.0/28"
  min_instances = 2
  max_instances = 3
}