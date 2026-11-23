#!/usr/bin/env bash
# ==============================================================================
# deploy/teardown.sh
# Automated Cost Safety Teardown Script
# Safely terminates all billable GCP resources to eliminate idle cloud spend.
# ==============================================================================

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project)}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="verifiable-support-agent"
SQL_INSTANCE="support-agent-pgvector"
AR_REPO="support-agent-repo"

echo "=================================================================="
echo "⚠️  TEARDOWN: Deleting Billable GCP Resources for Project: $PROJECT_ID"
echo "=================================================================="

# 1. Delete Cloud Run Service
echo "Deleting Cloud Run service: $SERVICE_NAME..."
gcloud run services delete "$SERVICE_NAME" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --quiet || echo "Cloud Run service already deleted."

# 2. Delete Cloud SQL Instance (Primary Cost Driver)
echo "Deleting Cloud SQL instance: $SQL_INSTANCE..."
gcloud sql instances delete "$SQL_INSTANCE" \
    --project="$PROJECT_ID" \
    --quiet || echo "Cloud SQL instance already deleted."

# 3. Clean up Artifact Registry images (optional)
echo "Cleaning up Artifact Registry images..."
gcloud artifacts repositories delete "$AR_REPO" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --quiet || echo "Artifact Registry repo already deleted."

echo "=================================================================="
echo "✅ Teardown complete. All billable resources stopped or deleted."
echo "=================================================================="