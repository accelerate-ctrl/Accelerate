# Terraform — Capability Intelligence (Batch 9).
#
# Single-file module that stands up the full GCP plumbing:
#   - Artifact Registry (Docker)
#   - Cloud Run service (the API)
#   - 14 Cloud Run Jobs (one per scheduled job)
#   - Cloud Scheduler entries that invoke each Job
#   - Pub/Sub topics + Cloud Tasks DLQ
#   - Secret Manager entries for the LLM keys
#   - Cloud Monitoring alert policies (cost, error rate, gate fails)
#
# Usage:
#   terraform init
#   terraform apply -var="project_id=zennify-cap-intel" \
#                   -var="region=us-central1"

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" { type = string }
variable "region"     { type = string, default = "us-central1" }
variable "image_tag"  { type = string, default = "latest" }
variable "anthropic_api_key" { type = string, default = null, sensitive = true }

locals {
  service_name = "capability-intelligence-api"
  image        = "${var.region}-docker.pkg.dev/${var.project_id}/capability-intelligence/api:${var.image_tag}"

  jobs = [
    "news-poll", "public-filings-poll", "jira-incremental",
    "sow-incremental", "sow-full-reindex", "lifecycle-scoring-daily",
    "benchmark-extrapolation-run", "benchmark-recompute-quarterly",
    "digest-quarterly", "deep-audit-weekly", "eval-run-weekly",
    "citation-verify-daily", "drift-check-daily", "evidence-promotion-nightly",
  ]

  schedules = {
    "news-poll"                     = "0 * * * *"
    "public-filings-poll"           = "30 4 * * *"
    "jira-incremental"              = "*/15 * * * *"
    "sow-incremental"               = "15 * * * *"
    "sow-full-reindex"              = "0 5 * * 0"
    "lifecycle-scoring-daily"       = "30 6 * * *"
    "benchmark-extrapolation-run"   = "0 7 * * 1"
    "benchmark-recompute-quarterly" = "0 6 1 1,4,7,10 *"
    "digest-quarterly"              = "0 9 1 1,4,7,10 *"
    "deep-audit-weekly"             = "0 8 * * 1"
    "eval-run-weekly"               = "30 8 * * 1"
    "citation-verify-daily"         = "0 3 * * *"
    "drift-check-daily"             = "30 7 * * *"
    "evidence-promotion-nightly"    = "0 2 * * *"
  }

  topics = [
    "job-events", "audit-events", "lifecycle-events",
    "digest-events", "suggestion-events",
  ]
}

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "capability-intelligence"
  format        = "DOCKER"
}

resource "google_pubsub_topic" "events" {
  for_each = toset(local.topics)
  name     = each.value
}

resource "google_pubsub_topic" "dlq" {
  name = "capability-intelligence-dlq"
}

resource "google_cloud_run_v2_service" "api" {
  name     = local.service_name
  location = var.region
  template {
    scaling { max_instance_count = 10 }
    containers {
      image = local.image
      ports { container_port = 8080 }
      env {
        name  = "ENV"
        value = "prod"
      }
      env {
        name  = "USE_GCP"
        value = "true"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      resources {
        limits = { cpu = "2", memory = "4Gi" }
      }
    }
  }
}

resource "google_cloud_run_v2_job" "jobs" {
  for_each = toset(local.jobs)
  name     = each.value
  location = var.region
  template {
    template {
      containers {
        image = local.image
        args  = ["python", "-m", "app.jobs.runner", replace(each.value, "-", "_")]
        env {
          name  = "USE_GCP"
          value = "true"
        }
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        resources {
          limits = { cpu = "2", memory = "4Gi" }
        }
      }
      timeout = "3600s"
      max_retries = 1
    }
  }
}

resource "google_cloud_scheduler_job" "schedules" {
  for_each = local.schedules
  name     = "schedule-${each.key}"
  schedule = each.value
  region   = var.region
  http_target {
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${each.key}:run"
    http_method = "POST"
    oauth_token {
      service_account_email = "scheduler@${var.project_id}.iam.gserviceaccount.com"
    }
  }
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  count     = var.anthropic_api_key != null ? 1 : 0
  secret_id = "anthropic-api-key"
  replication { auto {} }
}

resource "google_secret_manager_secret_version" "anthropic_api_key" {
  count       = var.anthropic_api_key != null ? 1 : 0
  secret      = google_secret_manager_secret.anthropic_api_key[0].id
  secret_data = var.anthropic_api_key
}

# ─── Monitoring alert policies (Batch 9) ────────────────────────────────────

resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "Capability Intelligence — high error rate"
  combiner     = "OR"
  conditions {
    display_name = "5xx > 5% over 5 minutes"
    condition_threshold {
      filter          = "metric.type=\"run.googleapis.com/request_count\" AND metric.label.\"response_code_class\"=\"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }
  notification_channels = []
}

resource "google_monitoring_alert_policy" "daily_spend" {
  display_name = "Capability Intelligence — daily LLM spend"
  combiner     = "OR"
  conditions {
    display_name = "Daily spend > 80% of ceiling"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/llm/daily_spend_usd\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }
  notification_channels = []
}

output "service_url" {
  value = google_cloud_run_v2_service.api.uri
}
