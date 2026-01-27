# Clinomic B12 Screening Platform
## Investor Demo & Pilot Lab Deployment Package

**Version:** 2.0 (Milestone 4 Complete)  
**Date:** July 2025  
**Status:** Investor Demo Ready | Pilot Lab Ready

---

## Quick Start - One Click Demo

### Option 1: Local Development (Current Environment)
```bash
# Services are already running
# Frontend: http://localhost:3000
# Backend:  http://localhost:8001
# API Docs: http://localhost:8001/docs
```

### Option 2: Docker Deployment
```bash
# Generate secrets and start
./scripts/start-demo.sh

# Or manually:
./scripts/generate-secrets.sh
docker-compose up -d --build
```

---

## Demo Credentials

| Role | Username | Password | Access Level |
|------|----------|----------|--------------|
| **Admin** | admin | admin | Full system access, analytics, audit |
| **Lab Tech** | lab | lab | Screening, patient records |
| **Doctor** | doctor | doctor | Screening, patient records |

---

## Demo Walkthrough Script

### 1. Login & Security Features (2 min)

1. Navigate to **http://localhost:3000**
2. Login with `admin / admin`
3. Show **Settings → Security** tab
   - Point out MFA setup capability
   - Show backup codes feature
   - Highlight "MFA Required" for clinical roles

### 2. Seed Demo Data (1 min)

Before showcasing analytics, seed the demo database:

```bash
# Via API (or use the admin dashboard)
curl -X POST http://localhost:8001/api/admin/demo/seed \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json"
```

This creates:
- 3 Labs (Central Pathology, City Hospital, Regional Diagnostic)
- 5 Doctors across specialties
- 10 Patients with screening results
- Mixed risk classifications (Normal, Borderline, Deficient)

### 3. Analytics Dashboard (2 min)

1. Navigate to **Dashboard** (Admin view)
2. Show key metrics:
   - Total screenings performed
   - Risk distribution breakdown
   - Lab and doctor utilization

### 4. B12 Screening Workflow (3 min)

1. Login as `lab / lab`
2. Go to **Screening** workspace
3. Demo the workflow:
   - Enter patient info (ID, Name, Age, Sex)
   - **NEW:** Consent capture modal appears automatically
   - Show consent recording with witness name
   - Enter CBC values or upload PDF
   - Run screening → Show results panel
   - Point out:
     - Risk classification (Normal/Borderline/Deficient)
     - Probability scores
     - Clinical interpretation
     - Model version tracking

### 5. Audit & Compliance (2 min)

1. Login as `admin / admin`
2. Go to **Settings → System** tab
3. Show:
   - System health status (all green)
   - Audit log integrity verification
   - Chain verification status

### 6. Security Highlights (1 min)

Key talking points:
- ✅ JWT authentication with refresh token rotation
- ✅ MFA (TOTP) for clinical roles
- ✅ PHI encryption (patient names encrypted at rest)
- ✅ Immutable audit logging with hash chains
- ✅ Role-based access control (RBAC)
- ✅ Multi-tenant organization isolation
- ✅ No hardcoded secrets (environment-based)

---

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     CLINOMIC PLATFORM                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐ │
│  │   FRONTEND   │────▶│   BACKEND    │────▶│   DATABASE   │ │
│  │   React 18   │     │   FastAPI    │     │   MongoDB    │ │
│  │   Port 3000  │     │   Port 8001  │     │   Port 27017 │ │
│  └──────────────┘     └──────────────┘     └──────────────┘ │
│         │                    │                    │          │
│         │                    ▼                    │          │
│         │           ┌──────────────┐              │          │
│         │           │  ML ENGINE   │              │          │
│         │           │  CatBoost    │              │          │
│         │           │  B12 v1.0    │              │          │
│         │           └──────────────┘              │          │
│         │                                         │          │
│         ▼                                         ▼          │
│  ┌─────────────────────────────────────────────────────────┐│
│  │                    SECURITY LAYER                        ││
│  │  • JWT Access/Refresh Tokens  • MFA (TOTP)              ││
│  │  • PHI Encryption (Fernet)    • RBAC                    ││
│  │  • Immutable Audit Logs       • Rate Limiting           ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## API Endpoints Summary

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Login (MFA-aware) |
| POST | `/api/auth/mfa/verify` | Complete MFA challenge |
| POST | `/api/auth/refresh` | Refresh tokens |
| POST | `/api/auth/logout` | Logout |

### MFA Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/mfa/status` | Get MFA status |
| POST | `/api/mfa/setup` | Initialize MFA |
| POST | `/api/mfa/verify-setup` | Complete MFA setup |
| POST | `/api/mfa/disable` | Disable MFA |

### Clinical Operations
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/screening/predict` | B12 screening |
| POST | `/api/lis/parse-pdf` | Parse CBC from PDF |
| POST | `/api/consent/record` | Record patient consent |
| GET | `/api/consent/status/{id}` | Check consent status |

### Analytics
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/analytics/summary` | Dashboard stats |
| GET | `/api/analytics/labs` | List labs |
| GET | `/api/analytics/doctors` | List doctors |
| GET | `/api/analytics/cases` | List screenings |

### Admin
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/demo/seed` | Seed demo data |
| GET | `/api/admin/audit/v2/summary` | Audit summary |
| GET | `/api/admin/audit/v2/verify` | Verify chain |
| GET | `/api/admin/system/health` | System health |

---

## Compliance & Security Features

### Implemented (Milestone 4)

| Feature | Status | Description |
|---------|--------|-------------|
| JWT Authentication | ✅ | Access + refresh tokens with rotation |
| MFA (TOTP) | ✅ | RFC 6238 compliant, backup codes |
| PHI Encryption | ✅ | Fernet encryption for patient names |
| Immutable Audit | ✅ | Hash-chained, HMAC-signed logs |
| Consent Management | ✅ | Patient consent capture & tracking |
| RBAC | ✅ | Role-based access control |
| Multi-Tenant | ✅ | Organization-level isolation |
| Rate Limiting | ✅ | IP, user, and org-level limits |
| Security Headers | ✅ | HSTS, CSP, X-Frame-Options |

### Roadmap (Future Milestones)

| Feature | Priority | Target |
|---------|----------|--------|
| External Audit Storage | High | Milestone 5 |
| Adverse Event Reporting | High | Milestone 5 |
| Model Performance Monitoring | Medium | Milestone 6 |
| SaMD Documentation | Medium | Milestone 6 |

---

## Deployment Options

### 1. Demo/Development
```bash
docker-compose up -d
```

### 2. Pilot Lab
```bash
# Generate production secrets
./scripts/generate-secrets.sh .env.secrets
source .env.secrets

# Set pilot configuration
export APP_ENV=pilot
export DEMO_USERS_ENABLED=false

# Deploy
docker-compose -f docker-compose.prod.yml up -d
```

### 3. Cloud Deployment
- **AWS**: ECS/Fargate + DocumentDB
- **GCP**: Cloud Run + MongoDB Atlas
- **Azure**: Container Apps + Cosmos DB

---

## Contact Information

**Clinomic Labs**  
- Technical: engineering@clinomic.io  
- Sales: sales@clinomic.io  
- Support: support@clinomic.io

**Repository**: https://github.com/Dev-Abiox/emergent_fullstack

---

*This platform is designed for clinical decision support and is not intended as a standalone diagnostic tool.*
