# Clinomic B12 Screening Platform

A full-stack clinical decision support system for B12 deficiency screening using machine learning analysis of Complete Blood Count (CBC) parameters.

## Overview

Clinomic helps healthcare providers identify patients at risk of Vitamin B12 deficiency through automated analysis of routine CBC test results. The platform uses a two-stage CatBoost classifier to categorize patients as Normal, Borderline, or Deficient based on hematological parameters.

## Features

- **ML-Powered Screening**: Two-stage CatBoost classifier with 92% accuracy
- **Role-Based Access**: Admin, Lab Technician, and Doctor roles with appropriate permissions
- **Multi-Tenant Architecture**: Schema-based isolation for healthcare organizations
- **HIPAA-Ready Security**: PHI encryption, MFA, JWT authentication, audit logging
- **Real-Time Analysis**: Instant B12 deficiency risk assessment
- **PDF Import**: Extract CBC values from lab reports automatically
- **Consent Management**: Digital consent capture with signature support
- **Comprehensive Dashboard**: Analytics and reporting for each role

## Tech Stack

### Backend (Django v3)
- **Framework**: Django 5.0 + Django REST Framework
- **Database**: PostgreSQL 15 with django-tenants
- **Authentication**: JWT with refresh token rotation + TOTP MFA
- **Encryption**: Fernet for PHI (patient names)
- **ML Engine**: CatBoost two-stage classifier

### Frontend (React)
- **Framework**: React 18 with React Router
- **Styling**: Tailwind CSS
- **Icons**: Lucide React
- **State**: React hooks with localStorage persistence

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Docker Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/Dev-Abiox/clinomic-prod.git
cd clinomic-prod

# Start all services
docker compose -f docker-compose.v3.yml up -d

# Seed demo data
docker compose -f docker-compose.v3.yml exec backend_v3 python manage.py seed_demo_data
```

Access the application:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000/api

### Demo Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | `admin_demo` | `Demo@2024` |
| Lab Technician | `lab_demo` | `Demo@2024` |
| Doctor | `doctor_demo` | `Demo@2024` |

## Project Structure

```
clinomic-prod/
├── backend_v3/                 # Django backend
│   ├── apps/
│   │   ├── core/              # Auth, users, MFA, crypto
│   │   ├── screening/         # B12 screening & ML engine
│   │   └── analytics/         # Dashboard & reporting
│   ├── ml/models/             # CatBoost model files
│   └── clinomic/              # Django settings
├── frontend/                   # React frontend
│   ├── src/
│   │   ├── components/        # Reusable UI components
│   │   ├── views/             # Page components
│   │   ├── services/          # API services
│   │   └── types.js           # Constants & enums
│   └── public/
├── scripts/v3/                 # Setup & deployment scripts
└── docker-compose.v3.yml       # Docker orchestration
```

## User Roles & Workflows

### Admin
- View platform-wide analytics dashboard
- Manage labs and view all doctors
- Access complete patient records across organization
- Monitor screening statistics and model performance

### Lab Technician
- Register patients and enter CBC values
- Run B12 deficiency screenings
- Select referring doctor for each screening
- View doctors associated with their lab

### Doctor
- View personal dashboard with patient statistics
- Perform screenings (auto-assigned to their account)
- Access their patient records and screening history
- View recent screening results

## API Endpoints

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Login with credentials |
| `/api/auth/refresh` | POST | Refresh access token |
| `/api/auth/logout` | POST | Revoke refresh token |
| `/api/auth/me` | GET | Get current user info |

### Screening
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/screening/classify` | POST | Run B12 classification |
| `/api/consent/record` | POST | Record patient consent |
| `/api/consent/status` | GET | Check consent status |

### Analytics
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analytics/summary` | GET | Dashboard statistics |
| `/api/analytics/labs` | GET | Lab statistics |
| `/api/analytics/doctors` | GET | Doctor statistics |
| `/api/analytics/cases` | GET | Patient records |

## Development

### Backend Development

```bash
cd backend_v3

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Run migrations
python manage.py migrate_schemas --shared

# Seed data
python manage.py seed_demo_data

# Start server
python manage.py runserver
```

### Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm start
```

## Environment Variables

Key environment variables (see `.env.example` for full list):

```env
# Django
DJANGO_SECRET_KEY=your-secret-key
DEBUG=False

# Database
POSTGRES_HOST=localhost
POSTGRES_DB=clinomic
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password

# JWT Authentication
JWT_SECRET_KEY=your-jwt-secret
JWT_REFRESH_SECRET_KEY=your-refresh-secret

# PHI Encryption
MASTER_ENCRYPTION_KEY=your-fernet-key

# Frontend
REACT_APP_API_URL=http://localhost:8000/api
```

## Security Features

- **JWT with Rotation**: Short-lived access tokens with rotating refresh tokens
- **MFA Support**: TOTP-based two-factor authentication
- **PHI Encryption**: Fernet encryption for patient names (fail-closed design)
- **Audit Logging**: Immutable hash-chain audit trail
- **Tenant Isolation**: Schema-level data separation
- **CORS Protection**: Configurable allowed origins
- **Input Validation**: Comprehensive request validation

## ML Model

The B12 screening uses a two-stage CatBoost classifier:

1. **Stage 1**: Normal vs Abnormal classification
2. **Stage 2**: Borderline vs Deficient classification (for abnormal cases)

Key CBC parameters analyzed:
- Hemoglobin (Hb)
- Red Blood Cell Count (RBC)
- Mean Corpuscular Volume (MCV)
- Mean Corpuscular Hemoglobin (MCH)
- Red Cell Distribution Width (RDW)
- And other hematological indices

## Scripts

```bash
# Setup development environment
./scripts/v3/setup.sh

# Start services
./scripts/v3/start.sh

# Create admin user
./scripts/v3/create-admin.sh
```

## Testing

```bash
# Backend tests
cd backend_v3
pytest --cov=apps

# Frontend tests
cd frontend
npm test
```

## License

Proprietary - Clinomic Healthcare Solutions

## Support

For support and inquiries, contact: support@clinomic.health
