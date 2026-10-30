terraform {
  # Supply the state bucket and prefix at init; never place credentials here.
  backend "gcs" {}
}
