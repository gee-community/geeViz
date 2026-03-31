# geeViz MCP Server — Remote Deployment

Deploy the geeViz MCP server as an HTTP service for use with Databricks AI,
Vertex AI, or any MCP-compatible client.

## Architecture

```
Databricks AI Playground ──→
Vertex AI Agent Builder  ──→  geeViz MCP (HTTP)  ──→  Google Earth Engine
Any MCP client           ──→  (Cloud Run / Databricks App)
```

The server uses a single GEE **service account** for all requests. Each
deployment is one Python process serving HTTP on port 8080 with sandbox
mode enabled.

## Prerequisites

1. A Google Cloud project with Earth Engine API enabled
2. A GEE-registered service account with a JSON key file
3. Docker (for Cloud Run) or Databricks CLI (for Databricks Apps)

### Create a GEE service account

```bash
# Create the service account
gcloud iam service-accounts create geeviz-mcp \
    --display-name="geeViz MCP Server"

# Create a key file
gcloud iam service-accounts keys create ee-sa-key.json \
    --iam-account=geeviz-mcp@YOUR_PROJECT.iam.gserviceaccount.com

# Register the service account with Earth Engine
# Visit: https://signup.earthengine.google.com/#!/service_accounts
# Or use: earthengine set_project YOUR_PROJECT
```

---

## Option A: Google Cloud Run

### Build and deploy

```bash
cd /path/to/geeViz

# Build and deploy in one step
gcloud builds submit \
    --config=mcp/deploy/cloudbuild.yaml \
    --substitutions=_GEE_PROJECT=your-project-id

# Or manually:
gcloud run deploy geeviz-mcp \
    --source=. \
    --dockerfile=mcp/deploy/Dockerfile \
    --region=us-central1 \
    --port=8080 \
    --memory=2Gi \
    --set-env-vars="MCP_TRANSPORT=streamable-http,MCP_HOST=0.0.0.0,MCP_PORT=8080,GEE_PROJECT=your-project-id" \
    --set-secrets="GEE_SERVICE_ACCOUNT_KEY=/secrets/ee-sa-key:latest"
```

### Store the service account key as a Cloud Secret

```bash
gcloud secrets create ee-sa-key --data-file=ee-sa-key.json
gcloud secrets add-iam-policy-binding ee-sa-key \
    --member="serviceAccount:YOUR_PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

### Connect from Databricks or Vertex AI

Your MCP endpoint will be:
```
https://geeviz-mcp-HASH-uc.a.run.app/mcp
```

### Authentication for Cloud Run

By default, Cloud Run requires authentication. Options:

- **Allow unauthenticated** (for testing): `--allow-unauthenticated`
- **IAM-based** (recommended): Grant `roles/run.invoker` to specific
  users/service accounts. Clients send a Google identity token as
  `Authorization: Bearer <token>`.
- **API Gateway** (enterprise): Put Cloud Endpoints or API Gateway in
  front for API key or OAuth validation.

---

## Option B: Databricks Apps

### Deploy

```bash
cd /path/to/geeViz

# Authenticate to Databricks
databricks auth login --host https://your-workspace.cloud.databricks.com

# Deploy the app
databricks apps deploy geeviz-mcp \
    --source-code-path . \
    --config-file mcp/deploy/app.yaml
```

### Configure GEE credentials

Upload your service account key to DBFS or use Databricks Secrets:

```bash
# Option 1: DBFS
databricks fs cp ee-sa-key.json dbfs:/secrets/ee-sa-key.json

# Option 2: Databricks Secrets (recommended)
databricks secrets create-scope geeviz
databricks secrets put-secret geeviz ee-sa-key --binary-file ee-sa-key.json
```

Update `app.yaml` to reference the key path.

### Connect from Databricks AI Playground

1. Open **Databricks AI Playground**
2. Click **Tools** dropdown
3. Select **Add custom MCP server**
4. Enter your app's endpoint: `https://<app-url>/mcp`

---

## Option C: Any Docker host

```bash
# Build
docker build -t geeviz-mcp -f mcp/deploy/Dockerfile .

# Run with service account key mounted
docker run -p 8080:8080 \
    -v /path/to/ee-sa-key.json:/secrets/ee-sa-key.json:ro \
    -e GEE_SERVICE_ACCOUNT_KEY=/secrets/ee-sa-key.json \
    -e GEE_PROJECT=your-project-id \
    geeviz-mcp
```

MCP endpoint: `http://localhost:8080/mcp`

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_TRANSPORT` | `stdio` | Set to `streamable-http` for HTTP mode |
| `MCP_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` for containers) |
| `MCP_PORT` | `8000` | HTTP port |
| `MCP_PATH` | `/mcp` | HTTP endpoint path |
| `GEE_SERVICE_ACCOUNT_KEY` | *(none)* | Path to GEE service account JSON key file |
| `GEE_SERVICE_ACCOUNT_KEY_JSON` | *(none)* | Inline JSON key string (for container secrets) |
| `GEE_PROJECT` | *(none)* | GEE project ID for billing/quotas |
| `GOOGLE_APPLICATION_CREDENTIALS` | *(none)* | Standard ADC key file path (alternative to `GEE_SERVICE_ACCOUNT_KEY`) |

## Security

The server runs with `--sandbox` by default in HTTP mode, which blocks:
- `open()`, `os`, `sys`, `eval`, `exec`, `subprocess`
- All file system access except `save_file()` to the outputs directory

For production, also:
- Use HTTPS (Cloud Run provides this automatically)
- Restrict network access via IAM, VPC, or API keys
- Monitor with Cloud Logging / Databricks audit logs
