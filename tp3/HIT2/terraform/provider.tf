terraform {
  required_version = ">= 1.3.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "bucket-tfstate-sdypp-grupo404-grupo404"
    prefix = "terraform/state/hit2"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}
