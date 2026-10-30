mock_provider "google" {}

variables {
  project_id        = "test-project-123"
  region            = "asia-southeast1"
  state_bucket_name = "example-private-state-123"
}

run "reject_other_region" {
  command = plan
  variables {
    region = "us-central1"
  }
  expect_failures = [var.region]
}

run "reject_invalid_project" {
  command = plan
  variables {
    project_id = "Invalid_Project"
  }
  expect_failures = [var.project_id]
}

run "reject_reserved_bucket" {
  command = plan
  variables {
    state_bucket_name = "google-private-state"
  }
  expect_failures = [var.state_bucket_name]
}

run "reject_dotted_bucket" {
  command = plan
  variables {
    state_bucket_name = "private.state.example"
  }
  expect_failures = [var.state_bucket_name]
}
