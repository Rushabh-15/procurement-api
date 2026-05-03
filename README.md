# Procurement API — Django + DRF

## What this is
A backend REST API simulating a real Source-to-Pay (S2P) procurement workflow.
Built to demonstrate Django, DRF, JWT auth, and business logic structuring.

## Tech stack
- Python 3.11 · Django 6.0 · Django REST Framework
- SimpleJWT (stateless authentication)
- spaCy (NLP invoice parsing)
- SQLite (dev) · PostgreSQL-ready

## Key features
- Full supplier and purchase order CRUD with JWT-locked endpoints
- PO status workflow: DRAFT → APPROVED → CLOSED
- 3-way match engine (PO + GRN + Invoice) with atomic transactions
- NLP invoice parser with per-field confidence scoring
- Overdue invoice detection
- Custom permissions, filtering, search, and pagination
- 14 unit and integration tests

## Setup
git clone https://github.com/Rushabh-15/procurement-api.git
cd procurement-api
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

## Run tests
python manage.py test procurement --verbosity=2

## Core API endpoints
POST   /auth/token/                        — obtain JWT
GET    /api/suppliers/                     — list suppliers (paginated)
POST   /api/purchase-orders/{id}/approve/  — approve a draft PO
POST   /api/grns/                          — record goods receipt
POST   /api/invoices/                      — create invoice + auto 3-way match
POST   /api/invoices/{id}/match/           — manually trigger match
GET    /api/invoices/overdue/              — all overdue invoices
POST   /api/invoices/parse/               — extract fields from raw invoice text

## Architecture decisions

### Services layer
Business logic (3-way match, NLP parsing, overdue detection) lives in `services.py`,
not in views. Reasons: independently testable, reusable from Celery tasks, keeps
views thin and readable.

### NLP pipeline design
Each field extractor is a separate private function (_extract_vendor, _extract_amount,
etc.). This follows the Single Responsibility Principle — improving one extractor
doesn't risk breaking others. spaCy's nlp.pipe() is used for batch processing to
avoid per-call model loading overhead.

### Why PostgreSQL over SQLite
Full ACID transactions (required for atomic 3-way match), concurrent connections,
JSONB support, and production parity with AWS RDS.

### Authentication
JWT (stateless) over sessions (stateful). Stateless auth scales horizontally without
sticky sessions or shared session storage. Access tokens expire in 60 minutes;
refresh tokens in 7 days with rotation enabled.