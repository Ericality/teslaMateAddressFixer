# TeslaMate Address Fixer

[![Docker Pulls](https://img.shields.io/docker/pulls/ericality/teslamate-fixer)](https://hub.docker.com/r/ericality/teslamate-fixer)
[![Platforms](https://img.shields.io/badge/platform-linux%2Famd64%20%7C%20linux%2Farm64-blue)](https://hub.docker.com/r/ericality/teslamate-fixer/tags)

A cron-based Docker service that automatically fills in missing Chinese addresses in [TeslaMate](https://github.com/teslamate-org/teslamate) driving records using the Baidu Maps reverse geocoding API .

## Features

- Automatically detects and fixes driving records with empty `start_address` or `end_address`
- Calls Baidu Maps API for POI-enriched reverse geocoding  
- Configurable cron schedule via environment variables
- Support for both Docker Compose and Kubernetes deployments
- Multi-architecture image (`linux/amd64` + `linux/arm64`)
- Deduplication of address records by coordinate proximity
- Dry-run friendly: limit how many records are processed per run

## How It Works

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  PostgreSQL  │────▶│  Address     │────▶│  Baidu Maps  │
│  (TeslaMate) │     │  Fixer       │     │  Reverse Geo │
│              │◀────│  (cron job)  │◀────│  API         │
└──────────────┘     └──────────────┘     └──────────────┘
```

1. Query TeslaMate's `drives` table for records where `start_address_id` or `end_address_id` is NULL
2. Look up the GPS coordinates from the linked `positions` table
3. Call Baidu Maps reverse geocoding API with the coordinates
4. Insert or reuse an address record in the `addresses` table
5. Update the `drives` record with the resolved address

## Quick Start

### Prerequisites

- A running TeslaMate instance (PostgreSQL database accessible)
- A Baidu Maps API key (AK + SK) — [apply here](https://lbsyun.baidu.com/apiconsole/key)

### Docker Compose (standalone)

```bash
# Clone the repository
git clone https://github.com/Ericality/teslaMateAddressFixer.git
cd teslaMateAddressFixer

# Create a .env file with your credentials
cat > .env << 'EOF'
BAIDU_MAP_AK=your_baidu_ak
BAIDU_MAP_SK=your_baidu_sk
TESLAMATE_DB_PASSWORD=your_db_password
EOF

# Start the fixer (requires teslamate Docker network)
docker compose -f deploy/docker-compose.example.yaml up -d
```

### Pull Pre-built Image

Skip the build step and use the pre-built multi-arch image:

```bash
docker pull ericality/teslamate-fixer:latest
```

## Configuration

All settings are passed as environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| **Database** | | |
| `DB_HOST` | `database` | PostgreSQL host (Docker service name or IP) |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_NAME` | `teslamate` | Database name |
| `DB_USER` | `teslamate` | Database user |
| `DB_PASS` | (required) | Database password |
| **Baidu Maps** | | |
| `BAIDU_AK` | (required) | Baidu Maps API Key |
| `BAIDU_SK` | (required) | Baidu Maps Secret Key |
| **Fixing Behavior** | | |
| `DAYS_TO_FIX` | `7` | Only fix records from the last N days |
| `BATCH_SIZE` | `2` | Commit to DB after every N address writes |
| `LIMIT_PER_RUN` | *(unlimited)* | Max drives to process per cron tick |
| `API_DELAY` | `1.0` | Delay between Baidu API calls (seconds) |
| **Scheduling** | | |
| `CRON_SCHEDULE` | `0 2 * * *` | Cron expression (dynamic, overrides the static cronjob file) |
| `RUN_ON_STARTUP` | `true` | Run an immediate fix on container start |
| **Logging** | | |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `LOG_FILE` | `/var/log/teslamate/fixer.log` | Log file path |
| **Other** | | |
| `TZ` | *(UTC)* | Timezone (e.g., `Asia/Shanghai`) |

## Deployment

### Docker Compose

```yaml
# deploy/docker-compose.example.yaml
services:
  teslamate-fixer:
    build: .
    container_name: teslamate-address-fixer
    restart: unless-stopped
    environment:
      - DB_HOST=database
      - DB_PORT=5432
      - DB_NAME=teslamate
      - DB_USER=teslamate
      - DB_PASS=${TESLAMATE_DB_PASSWORD}
      - BAIDU_AK=${BAIDU_MAP_AK}
      - BAIDU_SK=${BAIDU_MAP_SK}
      - CRON_SCHEDULE=0 * * * *
      - RUN_ON_STARTUP=true
      - TZ=Asia/Shanghai
    volumes:
      - ./logs:/var/log/teslamate
    networks:
      - teslamate

networks:
  teslamate:
    external: true
```

### Kubernetes

```bash
# Create secrets for sensitive credentials
kubectl create secret generic teslamate-fixer-secret \
  --from-literal=DB_PASS='your_password' \
  --from-literal=BAIDU_AK='your_ak' \
  --from-literal=BAIDU_SK='your_sk' \
  -n teslamate

# Deploy
kubectl apply -f deploy/k8s.yaml
```

See `deploy/k8s.yaml` for the complete Deployment + ConfigMap + Secret manifest.

## Building from Source

```bash
# Build for your local architecture
docker build -t teslamate-address-fixer .

# Build and push multi-platform image
docker buildx build --platform linux/amd64,linux/arm64 \
  -t your-registry/teslamate-fixer:latest --push .
```

## Project Structure

```
.
├── teslamate_fixer.py          # Main application
├── start.sh                    # Container entrypoint (DB/API checks, cron setup)
├── cronjob                     # Static cron definition (fallback)
├── Dockerfile                  # Multi-stage-safe Dockerfile
├── requirements.txt            # Python dependencies
├── config.py                   # Legacy config module
├── deploy/
│   ├── docker-compose.example.yaml   # Standalone Docker Compose example
│   └── k8s.yaml                      # Kubernetes manifest (ConfigMap + Secret)
├── .env.example                # Environment variable template
└── .gitignore
```

## License

MIT