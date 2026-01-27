# Clinomic Platform - Pilot Lab Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the Clinomic B12 Screening Platform in a pilot laboratory environment.

---

## Prerequisites

### Infrastructure Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Storage | 20 GB SSD | 50 GB SSD |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |

### Software Requirements

- Docker 24.0+
- Docker Compose v2+
- OpenSSL (for key generation)
- curl (for health checks)

### Network Requirements

- Outbound HTTPS (443) for updates
- Inbound ports: 3000 (frontend), 8001 (API)
- Stable network connection

---

## Deployment Steps

### Step 1: Clone Repository

```bash
git clone https://github.com/Dev-Abiox/emergent_fullstack.git
cd emergent_fullstack
```

### Step 2: Generate Secrets

```bash
# Make scripts executable
chmod +x scripts/generate-secrets.sh scripts/start-demo.sh

# Generate production secrets
./scripts/generate-secrets.sh .env.secrets

# Review generated secrets
cat .env.secrets
```

⚠️ **Important:** Store `.env.secrets` securely. Never commit to version control.

### Step 3: Configure Environment

Create a `.env` file for your pilot deployment:

```bash
cat > .env << 'EOF'
# Pilot Environment Configuration
APP_ENV=pilot

# Database
MONGO_URL=mongodb://mongodb:27017
DB_NAME=clinomic_pilot

# Security (load from .env.secrets)
# JWT_SECRET_KEY=<from .env.secrets>
# MASTER_ENCRYPTION_KEY=<from .env.secrets>
# AUDIT_SIGNING_KEY=<from .env.secrets>

# CORS (update with your domain)
CORS_ORIGINS=https://your-pilot-domain.com

# Frontend URL for Docker build
REACT_APP_BACKEND_URL=https://your-pilot-domain.com/api

# MFA Configuration
MFA_REQUIRED_ROLES=ADMIN,DOCTOR
MFA_GRACE_PERIOD_HOURS=24

# Demo mode DISABLED for pilot
DEMO_MODE_ENABLED=false
DEMO_USERS_ENABLED=false

# Features
AUDIT_V2_ENABLED=true
DEVICE_TRACKING_ENABLED=true
RATE_LIMIT_ENABLED=true
EOF
```

Load secrets:

```bash
# Merge secrets into environment
source .env.secrets
export JWT_SECRET_KEY MASTER_ENCRYPTION_KEY AUDIT_SIGNING_KEY
```

### Step 4: Deploy Services

```bash
# Start all services
docker-compose up -d --build

# Monitor startup
docker-compose logs -f
```

### Step 5: Verify Deployment

```bash
# Check service health
curl http://localhost:8001/api/health/ready
# Expected: {"status": "ready"}

curl http://localhost:3000/health
# Expected: healthy

# View running containers
docker-compose ps
```

---

## Initial Configuration

### Create Admin User

Since demo users are disabled in pilot mode, create your admin user via the database:

```bash
# Connect to MongoDB
docker exec -it clinomic-mongodb mongosh clinomic_pilot

# Create admin user (replace values)
db.users.insertOne({
  id: "pilot_admin",
  orgId: "ORG-PILOT-LAB",
  name: "Pilot Administrator",
  role: "ADMIN",
  passwordHash: "<bcrypt-hash-of-password>",
  isActive: true,
  createdAt: new Date().toISOString(),
  updatedAt: new Date().toISOString()
})
```

To generate a bcrypt password hash:

```bash
docker exec clinomic-backend python -c "
from passlib.context import CryptContext
pwd = CryptContext(schemes=['bcrypt'])
print(pwd.hash('your-secure-password'))
"
```

### Create Lab and Doctor Records

```javascript
// In MongoDB shell
db.labs.insertOne({
  id: "LAB-PILOT-001",
  name: "Pilot Laboratory",
  tier: "Pilot",
  orgId: "ORG-PILOT-LAB"
})

db.doctors.insertOne({
  id: "DOC-PILOT-001",
  name: "Dr. Pilot Physician",
  dept: "Hematology",
  labId: "LAB-PILOT-001",
  orgId: "ORG-PILOT-LAB"
})
```

---

## MFA Setup

MFA is required for ADMIN and DOCTOR roles in pilot mode.

### User MFA Enrollment

1. Log in with username/password
2. System returns `mfa_required: true` with pending token
3. Navigate to Settings → Security → Enable MFA
4. Scan QR code with authenticator app (Google Authenticator, Authy)
5. Enter 6-digit code to verify
6. Save backup codes securely

### Supported Authenticator Apps

- Google Authenticator
- Microsoft Authenticator
- Authy
- 1Password
- Any TOTP-compatible app

---

## SSL/TLS Configuration

For production pilots, configure TLS:

### Option 1: Reverse Proxy (Recommended)

Use nginx or Traefik as a reverse proxy with Let's Encrypt:

```nginx
# /etc/nginx/sites-available/clinomic
server {
    listen 443 ssl http2;
    server_name your-pilot-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-pilot-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-pilot-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }

    location /api/ {
        proxy_pass http://localhost:8001/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Option 2: Docker with TLS

Use the production compose file with proxy profile:

```bash
docker-compose -f docker-compose.prod.yml --profile with-proxy up -d
```

---

## Backup & Recovery

### Database Backup

```bash
# Create backup
docker exec clinomic-mongodb mongodump \
  --db clinomic_pilot \
  --out /data/backup/$(date +%Y%m%d)

# Copy backup to host
docker cp clinomic-mongodb:/data/backup ./backups/
```

### Scheduled Backups

Add to crontab:

```bash
# Daily backup at 2 AM
0 2 * * * /path/to/clinomic/scripts/backup.sh >> /var/log/clinomic-backup.log 2>&1
```

### Recovery

```bash
# Restore from backup
docker exec clinomic-mongodb mongorestore \
  --db clinomic_pilot \
  /data/backup/20250701/clinomic_pilot
```

---

## Monitoring

### Health Checks

| Endpoint | Purpose | Expected Response |
|----------|---------|-------------------|
| `/api/health/live` | Liveness probe | `{"status": "live"}` |
| `/api/health/ready` | Readiness probe | `{"status": "ready"}` |
| `/api/admin/system/health` | Full system health | Component status |

### Log Monitoring

```bash
# View all logs
docker-compose logs -f

# Backend only
docker-compose logs -f backend

# Filter errors
docker-compose logs backend 2>&1 | grep -i error
```

### Audit Log Review

```bash
# Export audit logs (requires admin auth)
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8001/api/admin/audit/v2/export" \
  -o audit_export.json

# Verify chain integrity
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8001/api/admin/audit/v2/verify"
```

---

## Troubleshooting

### Common Issues

#### Services Won't Start

```bash
# Check Docker status
docker-compose ps

# Check logs
docker-compose logs backend

# Common fix: restart services
docker-compose restart
```

#### Database Connection Failed

```bash
# Verify MongoDB is running
docker exec clinomic-mongodb mongosh --eval "db.adminCommand('ping')"

# Check connection string
echo $MONGO_URL
```

#### MFA Not Working

- Verify system time is synchronized (NTP)
- Check that authenticator app time is correct
- Try using a backup code
- Regenerate MFA setup if needed

#### Model Files Missing

```bash
# Verify model files exist
docker exec clinomic-backend ls -la b12_clinical_engine_v1.0/

# Should see:
# - stage1_normal_vs_abnormal.pkl
# - stage2_borderline_vs_deficient.pkl
# - thresholds.json
# - version.json
```

---

## Security Checklist

- [ ] Generated unique secrets (not using defaults)
- [ ] Demo users disabled (`DEMO_USERS_ENABLED=false`)
- [ ] MFA enabled for admin/doctor roles
- [ ] TLS configured for all connections
- [ ] Firewall configured (only required ports open)
- [ ] Backup strategy implemented and tested
- [ ] Audit logs being captured
- [ ] Admin passwords changed from defaults
- [ ] Rate limiting enabled
- [ ] CORS configured for specific domains

---

## Support

### Log Collection for Support

```bash
# Collect diagnostic information
mkdir -p /tmp/clinomic-diag
docker-compose logs > /tmp/clinomic-diag/logs.txt
docker-compose ps > /tmp/clinomic-diag/services.txt
curl http://localhost:8001/api/health/ready > /tmp/clinomic-diag/health.json 2>/dev/null
tar -czf clinomic-diag-$(date +%Y%m%d).tar.gz -C /tmp clinomic-diag
```

### Contact

- **Technical Support:** support@clinomic.io
- **Documentation:** https://docs.clinomic.io
- **Repository:** https://github.com/Dev-Abiox/emergent_fullstack

---

## Appendix: Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `APP_ENV` | Yes | dev | Environment: dev/demo/pilot/prod |
| `MONGO_URL` | Yes | - | MongoDB connection string |
| `DB_NAME` | Yes | - | Database name |
| `JWT_SECRET_KEY` | Yes | - | JWT signing key (min 32 chars) |
| `MASTER_ENCRYPTION_KEY` | Yes | - | Fernet encryption key |
| `AUDIT_SIGNING_KEY` | Yes | - | HMAC signing key for audit |
| `CORS_ORIGINS` | Yes | * | Allowed origins (comma-separated) |
| `MFA_REQUIRED_ROLES` | No | ADMIN,DOCTOR | Roles requiring MFA |
| `DEMO_MODE_ENABLED` | No | false | Enable demo features |
| `DEMO_USERS_ENABLED` | No | false | Allow demo user login |
| `RATE_LIMIT_ENABLED` | No | true | Enable rate limiting |
| `AUDIT_V2_ENABLED` | No | true | Use immutable audit system |
