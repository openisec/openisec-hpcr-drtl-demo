output "cloud_run_sa_email" {
  description = "Cloud Run service account email"
  value       = google_service_account.cloud_run_sa.email
}

output "cicd_sa_email" {
  description = "CI/CD service account email"
  value       = google_service_account.cicd_sa.email
}

output "db_instance_name" {
  description = "Cloud SQL instance name"
  value       = google_sql_database_instance.main.name
}

output "db_connection_name" {
  description = "Cloud SQL connection name for Cloud Run"
  value       = google_sql_database_instance.main.connection_name
}

output "db_password_secret" {
  description = "Secret Manager secret ID for DB password"
  value       = google_secret_manager_secret.db_password.secret_id
}

output "wif_provider" {
  description = "Workload Identity Federation provider"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "vpc_connector_name" {
  description = "VPC Access Connector name"
  value       = google_vpc_access_connector.connector.name
}