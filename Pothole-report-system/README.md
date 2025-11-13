# Pothole Report System

A simple Flask web application that lets citizens report potholes and municipal staff verify and manage repairs. This repository includes the application code, static assets, templates, and a MySQL-compatible database schema focused on storing users, reports, and verification records.

**Contents**
- `app.py` — Flask application entrypoint.
- `config.py` — configuration for the app (DB, secrets, etc.).
- `database/schema.sql` — full SQL schema (tables, views, procedure, trigger) and sample data.
- `templates/` and `static/` — frontend templates, JS, and CSS.

**Tech stack**: Python + Flask, MySQL-compatible database, S3-style object storage for images.

**Quick summary**
This project provides a straightforward flow: users register/login, submit pothole reports with optional images and geolocation, municipal users verify or reject reports, and credits are awarded to citizens for verified/completed reports. The database enforces referential integrity, provides views for dashboards, and contains server-side automation for credit awards.

**Getting Started**
1. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

2. Create the database and schema (MySQL):

```sql
-- from your mysql client
SOURCE database/schema.sql;
```

3. Configure connection settings in `config.py` or environment variables and run the app:

```powershell
$env:FLASK_APP = 'app.py'; flask run
```

**Database (Detailed)**
The schema in `database/schema.sql` is the heart of the project. Key points:

- `pothole_db` is created and used by the schema.

- `custom_user` table:
	- Holds users with an integer primary key (`id`) and an application UUID (`user_id` VARCHAR(36)).
	- Fields: `username`, `email`, `phone_number`, `password_hash`, `credits`, `is_staff`, `created_at`.
	- Unique constraints and indexes on `user_id`, `username`, and `email` for fast lookups and uniqueness enforcement.

- `pothole_report` table:
	- Stores each report with `report_id` (UUID) and `user_id` referencing `custom_user.user_id` (`ON DELETE CASCADE`).
	- Media and storage references: `image_url`, `s3_bucket_path` (images stored in S3-like object storage).
	- Geolocation: `latitude` (DECIMAL(10,8)) and `longitude` (DECIMAL(11,8)); composite index on `(latitude, longitude)` for coarse spatial queries.
	- Status/severity as ENUMs: `severity` in `('LOW','MEDIUM','HIGH','CRITICAL')`, `status` in `('PENDING','VERIFIED','REJECTED','IN_PROGRESS','COMPLETED')`.
	- Indexes on `status`, `severity`, `created_at`, and `user_id` to support common access patterns and analytics.

- `municipal_verification` table:
	- Links to `pothole_report.report_id` and records verification actions, notes, verification status, and estimated repair dates.

**Automation & Analytics**
- Views:
	- `report_summary` aggregates per-user counts, completed reports, total credits, and last report date — useful for user dashboards.
	- `status_analytics` groups counts and average credits by `status`, `severity`, and date for trend analysis.

- Stored procedure:
	- `AwardCredits(p_user_id, p_credits, p_reason)` to increment user credits server-side.

- Trigger:
	- `update_credits_on_status_change` automatically awards credits when report status changes to `VERIFIED` (+10) or `COMPLETED` (+5), keeping reward logic consistent and centralized.

**Design notes & recommendations**
- The schema separates application UUIDs (`user_id`, `report_id`) from internal integer PKs for flexibility and safer external references.
- For advanced geospatial queries, consider switching to spatial types (e.g., `POINT`) with spatial indexes for accurate radius searches and routing.
- Use migration tooling (Flask-Migrate/Alembic or plain SQL migration scripts) for schema evolution in production.
- Keep password handling to hashed values only (the schema stores `password_hash`), and ensure the application uses a secure hashing algorithm (e.g., Argon2 or PBKDF2 with sufficient iterations).

**Example queries**

- Recent pending reports:

```sql
SELECT * FROM pothole_report WHERE status = 'PENDING' ORDER BY created_at DESC LIMIT 20;
```

- Summary for a user (using the view):

```sql
SELECT * FROM report_summary WHERE username = 'john_doe';
```

**Future improvements**
- Add audit/version tables to track report edits and status history.
- Integrate spatial indexes for precise location queries.
- Add background workers for image processing and S3 uploads.
- Add automated tests for DB migrations and stored routines.

---
