# Clinomic B12 Screening Platform
## Technical Due Diligence Summary

**Version:** 2.0 (Investor & Pilot Ready)  
**Date:** July 2025  
**Classification:** Confidential  

---

## Executive Summary

The Clinomic B12 Screening Platform is a Clinical Decision Support (CDS) system designed to screen for Vitamin B12 deficiency using Complete Blood Count (CBC) data. The platform has completed **Milestone 3: Investor & Pilot Hardening**, achieving production-grade security, compliance foundations, and deployment readiness.

### Key Achievements

| Milestone | Status | Description |
|-----------|--------|-------------|
| MVP Core | ✅ Complete | B12 screening with hierarchical ML model |
| Authentication | ✅ Complete | JWT access/refresh with rotation & revocation |
| **MFA** | ✅ Complete | TOTP-based multi-factor authentication |
| **Secrets Management** | ✅ Complete | No hardcoded secrets, env-based configuration |
| **Immutable Audit** | ✅ Complete | Hash-chained, HMAC-signed audit logs |
| **Containerization** | ✅ Complete | Docker-ready with compose files |
| **CI/CD Pipeline** | ✅ Complete | GitHub Actions with security scans |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    USERS                             │
│         (Lab Technicians, Doctors, Admins)          │
└───────────────────────┬─────────────────────────────┘
                        │ HTTPS
                        ▼
┌─────────────────────────────────────────────────────┐
│              React Frontend (3000)                   │
│     • Role-based UI • Token refresh • MFA flow      │
└───────────────────────┬─────────────────────────────┘
                        │ REST API
                        ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI Backend (8001)                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Auth/MFA    │ │ Screening   │ │ Analytics   │   │
│  │ Module      │ │ Engine      │ │ & Audit     │   │
│  └─────────────┘ └─────────────┘ └─────────────┘   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Secrets Mgr │ │ Crypto      │ │ Rate Limit  │   │
│  └─────────────┘ └─────────────┘ └─────────────┘   │
└───────────────────────┬─────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  MongoDB    │ │ B12 ML      │ │ File        │
│  Database   │ │ Engine v1.0 │ │ Storage     │
└─────────────┘ └─────────────┘ └─────────────┘
```

---

## Security Posture

### Authentication & Authorization

| Feature | Implementation | Status |
|---------|---------------|--------|
| Password Hashing | bcrypt with auto-cost | ✅ Production |
| Access Tokens | JWT HS256, 60min expiry | ✅ Production |
| Refresh Tokens | JWT HS256, 30day, fingerprinted | ✅ Production |
| Token Rotation | New token on refresh, old revoked | ✅ Production |
| **MFA (TOTP)** | RFC 6238 compliant, QR setup | ✅ Production |
| **MFA Backup Codes** | 10 single-use codes, hashed storage | ✅ Production |
| Role-Based Access | ADMIN, LAB, DOCTOR roles | ✅ Production |
| Multi-Tenant Isolation | Organization-level data separation | ✅ Production |

### Data Protection

| Feature | Implementation | Status |
|---------|---------------|--------|
| PHI Encryption | Fernet symmetric encryption | ✅ Production |
| **Secrets Management** | Environment-based, no hardcoding | ✅ Production |
| **Key Generation** | Cryptographically secure, auto-generated | ✅ Production |
| Transport Security | HTTPS required (TLS 1.2+) | ✅ Production |
| Security Headers | HSTS, CSP, X-Frame-Options, etc. | ✅ Production |

### Audit & Compliance

| Feature | Implementation | Status |
|---------|---------------|--------|
| Event Logging | All security events logged | ✅ Production |
| **Hash Chain** | SHA256 linked entries | ✅ Production |
| **HMAC Signing** | Tamper-evident signatures | ✅ Production |
| **Checkpoints** | Periodic merkle root validation | ✅ Production |
| Export Capability | JSON export with verification | ✅ Production |

---

## ML Model Governance

### Model Specifications

| Attribute | Value |
|-----------|-------|
| Model Name | B12 Clinical Engine |
| Version | 1.0.0 |
| Architecture | Hierarchical CatBoost + Clinical Rules |
| Stages | Stage 1: Normal vs Abnormal, Stage 2: Borderline vs Deficient |
| Input Features | 12 CBC parameters + Age + Sex |
| Output Classes | Normal (1), Borderline (2), Deficient (3) |

### Reproducibility Controls

- **Model Artifact Hash**: SHA256 of serialized model files
- **Request Hash**: SHA256 of input parameters
- **Response Hash**: SHA256 of prediction output
- **Screening Hash**: Combined hash for full lineage

---

## Deployment Architecture

### Container Configuration

```yaml
Services:
  - mongodb: MongoDB 7.0 with persistence
  - backend: Python 3.11 + FastAPI
  - frontend: React 18 + nginx

Networks:
  - Internal (backend ↔ database)
  - External (frontend ↔ users)

Volumes:
  - mongodb_data (persistent)
```

### Environment Profiles

| Profile | Purpose | Demo Users | MFA Required |
|---------|---------|------------|---------------|
| `dev` | Development | ✅ Enabled | No |
| `demo` | Investor demo | ✅ Enabled | No |
| `pilot` | Lab pilot | ❌ Disabled | Recommended |
| `prod` | Production | ❌ Disabled | Required |

### CI/CD Pipeline

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  Push   │───▶│  Lint   │───▶│  Test   │───▶│  Build  │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
                                                  │
                    ┌─────────────────────────────┘
                    ▼
              ┌───────────┐    ┌───────────┐
              │  Security │───▶│  Deploy   │
              │   Scan    │    │  (manual) │
              └───────────┘    └───────────┘
```

**Pipeline Features:**
- Python linting (flake8)
- Security scanning (Bandit, Safety)
- Frontend build verification
- Docker image building
- Container vulnerability scanning (Trivy)

---

## API Summary

### Core Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/auth/login` | POST | No | User authentication (MFA-aware) |
| `/api/auth/mfa/verify` | POST | No | Complete MFA verification |
| `/api/auth/refresh` | POST | No | Token refresh |
| `/api/screening/predict` | POST | Yes | B12 deficiency screening |
| `/api/analytics/summary` | GET | Yes | Dashboard statistics |
| `/api/health/ready` | GET | No | Readiness probe |

### MFA Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/mfa/setup` | POST | Yes | Initialize MFA enrollment |
| `/api/mfa/verify-setup` | POST | Yes | Complete MFA setup |
| `/api/mfa/status` | GET | Yes | Get MFA status |
| `/api/mfa/disable` | POST | Yes | Disable MFA (requires code) |

### Admin Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/admin/audit/v2/summary` | GET | Admin | Audit log summary |
| `/api/admin/audit/v2/verify` | GET | Admin | Chain integrity check |
| `/api/admin/audit/v2/export` | GET | Admin | Export for archival |
| `/api/admin/system/health` | GET | Admin | System health check |

---

## Technical Metrics

### Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Prediction Latency | < 100ms | Single screening |
| API Response Time | < 200ms | 95th percentile |
| Token Validation | < 10ms | JWT decode |
| Database Queries | < 50ms | Indexed operations |

### Scalability

| Aspect | Current | Capability |
|--------|---------|------------|
| Concurrent Users | 100+ | Tested |
| Screenings/Day | 10,000+ | Estimated |
| Data Retention | Unlimited | MongoDB |
| Horizontal Scaling | Supported | Stateless backend |

---

## Compliance Readiness

### CDS/SaMD Alignment

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Audit Trail | ✅ Ready | Immutable hash-chained logs |
| Data Lineage | ✅ Ready | Request/Response/Model hashing |
| Model Versioning | ✅ Ready | Version + artifact hash stored |
| Access Control | ✅ Ready | RBAC + org isolation |
| PHI Protection | ✅ Ready | Fernet encryption |
| MFA | ✅ Ready | TOTP implementation |

### Remaining for Full Compliance

- [ ] Consent management workflow
- [ ] Adverse event reporting
- [ ] External immutable storage (AWS QLDB/S3 Glacier)
- [ ] Formal SaMD documentation
- [ ] Penetration testing

---

## Demo Credentials

**For Investor Demo Environment Only**

| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin |
| Lab Tech | lab | lab |
| Doctor | doctor | doctor |

⚠️ Demo credentials are disabled in pilot and production environments.

---

## Quick Start

### One-Click Demo

```bash
# Generate secrets and start demo
./scripts/start-demo.sh

# Access points:
# - Frontend: http://localhost:3000
# - Backend API: http://localhost:8001
# - API Docs: http://localhost:8001/docs
```

### Production Deployment

```bash
# 1. Generate production secrets
./scripts/generate-secrets.sh .env.prod

# 2. Configure environment
export $(cat .env.prod | grep -v '#' | xargs)
export APP_ENV=prod
export DEMO_USERS_ENABLED=false

# 3. Deploy with production compose
docker-compose -f docker-compose.prod.yml up -d
```

---

## Risk Assessment

### Addressed Risks (Milestone 3)

| Risk | Mitigation | Status |
|------|------------|--------|
| Credential theft | MFA required for sensitive roles | ✅ Mitigated |
| Secret exposure | Environment-based, no hardcoding | ✅ Mitigated |
| Audit tampering | Hash-chain + HMAC signing | ✅ Mitigated |
| Session hijacking | Device fingerprinting + anomaly detection | ✅ Mitigated |

### Outstanding Risks

| Risk | Priority | Mitigation Plan |
|------|----------|------------------|
| Advanced persistent threats | Medium | WAF + IDS (Milestone 4) |
| Database breach | Medium | Encryption at rest (Milestone 4) |
| Zero-day vulnerabilities | Low | Regular security updates |

---

## Contact & Support

**Technical Lead:** Clinomic Engineering Team  
**Repository:** https://github.com/Dev-Abiox/emergent_fullstack.git  
**Documentation:** See `/docs` directory  

---

*This document is for investor due diligence purposes. Technical specifications subject to change.*
