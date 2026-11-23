# Google Cloud Platform Deployment Runbook

> **Note: Documentation only, not executed.** This runbook specifies the target cloud provisioning and deployment procedures for Google Cloud Run and Cloud SQL. These steps have not yet been executed against a live GCP production project.

Complete step-by-step guide to provisioning, deploying, and verifying the Verifiable Support Agent on Google Cloud Platform.

---

## 1. Prerequisites & Environment Setup

```bash
# Set environment variables
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export SERVICE_NAME="verifiable-support-agent"
export SQL_INSTANCE="support-agent-pgvector"
export AR_REPO="support-agent-repo"
export SA_NAME="sa-support-agent"

# Authenticate & set default project
gcloud auth login
gcloud config set project $PROJECT_ID
```

---

## 2. Enable Required Google Cloud APIs

```bash
gcloud services enable \
    run.googleapis.com \
    sqladmin.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    aiplatform.googleapis.com \
    cloudtrace.googleapis.com \
    logging.googleapis.com \
    iamcredentials.googleapis.com
```

---

## 3. Create Artifact Registry Repository

```bash
gcloud artifacts repositories create $AR_REPO \
    --repository-format=docker \
    --location=$REGION \
    --description="Docker repository for Verifiable Support Agent"
```

---

## 4. Provision Cloud SQL PostgreSQL with `pgvector`

```bash
# Create the smallest cost-effective Cloud SQL instance (db-f1-micro or db-custom-1-3840)
gcloud sql instances create $SQL_INSTANCE \
    --database-version=POSTGRES_16 \
    --tier=db-custom-1-3840 \
    --region=$REGION \
    --storage-size=10GB \
    --storage-type=SSD \
    --availability-type=ZONAL

# Set secure database password
export DB_PASS=$(openssl rand -base64 18)
gcloud sql users set-password postgres \
    --instance=$SQL_INSTANCE \
    --password="$DB_PASS"

# Create application database
gcloud sql databases create support_agent_db --instance=$SQL_INSTANCE
```

---

## 5. Store Secrets in Google Secret Manager

```bash
echo -n "$DB_PASS" | gcloud secrets create db-password \
    --data-file=- \
    --replication-policy="automatic"
```

---

## 6. Configure Least-Privilege Service Account

```bash
# Create dedicated service account
gcloud iam service-accounts create $SA_NAME \
    --display-name="Verifiable Support Agent Service Account"

export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Assign strict required roles
for ROLE in \
    roles/aiplatform.user \
    roles/cloudsql.client \
    roles/secretmanager.secretAccessor \
    roles/cloudtrace.agent \
    roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="$ROLE"
done
```

---

## 7. Build, Push & Deploy to Cloud Run

```bash
# Build and tag image
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet
export IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${SERVICE_NAME}:v2.0.0"

docker build -t $IMAGE_URI -f deploy/Dockerfile .
docker push $IMAGE_URI

# Retrieve Cloud SQL instance connection name
export INSTANCE_CONN=$(gcloud sql instances describe $SQL_INSTANCE --format="value(connectionName)")

# Deploy to Cloud Run
gcloud run deploy $SERVICE_NAME \
    --image=$IMAGE_URI \
    --region=$REGION \
    --platform=managed \
    --allow-unauthenticated \
    --service-account=$SA_EMAIL \
    --min-instances=0 \
    --max-instances=2 \
    --memory=512Mi \
    --cpu=1 \
    --timeout=80s \
    --add-cloudsql-instances=$INSTANCE_CONN \
    --set-env-vars="OTEL_EXPORTER=gcp,DB_HOST=/cloudsql/${INSTANCE_CONN},DB_NAME=support_agent_db,DB_USER=postgres" \
    --set-secrets="DB_PASSWORD=db-password:latest"
```

---

## 8. Run Production Smoke Tests

```bash
export SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format="value(status.url)")
python deploy/smoke_test.py $SERVICE_URL
```

---

## 9. Cost Safety Teardown

```bash
chmod +x deploy/teardown.sh
./deploy/teardown.sh
```