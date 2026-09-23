# Resend API Key（手動で値を設定する）
resource "google_secret_manager_secret" "resend_api_key" {
  secret_id = "resend-api-key-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }
}

# Vertex AI / Gemini（ADC経由のため不要だが、将来のAPI Key方式に備えて）
resource "google_secret_manager_secret" "session_secret" {
  secret_id = "session-secret-${var.environment}"
  project   = var.project_id

  replication {
    auto {}
  }
}

resource "random_password" "session_secret" {
  length  = 64
  special = false
}

resource "google_secret_manager_secret_version" "session_secret" {
  secret      = google_secret_manager_secret.session_secret.id
  secret_data = random_password.session_secret.result
}
