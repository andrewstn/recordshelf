# Record Shelf

A production full-stack social platform for vinyl collectors to catalog collections, build profile shelves, discover records, and connect with other collectors.

Live: [record-shelf.com](https://record-shelf.com)

Record Shelf was built to create a more visual and social way for vinyl collectors to showcase collections online.

## Features

- Custom profile shelves with drag-and-drop record placement
- Collection and wishlist management
- Community profiles and following system
- Discogs and Spotify powered record discovery
- Authentication with email verification and password reset
- Cloudflare R2 media uploads
- Analytics and monitoring with PostHog and Sentry

## Screenshots

![Landing Page Screenshot](docs/landing.png)
![Profile Shelf Screenshot](docs/profile.png)
![Record Modal Screenshot](docs/modal.png)

## Architecture

Frontend:

- Django templates
- Tailwind CSS

Backend:

- Django 6
- PostgreSQL-compatible database configured with `DATABASE_URL`

Infrastructure:

- Railway
- Cloudflare DNS
- Cloudflare R2
- Gunicorn
- WhiteNoise

Observability:

- PostHog
- Sentry

External APIs:

- Discogs
- Spotify
- Resend

## Tech Stack

- Python / Django 6
- Django templates for server-rendered pages
- Tailwind CSS 4, built with the Tailwind CLI
- PostgreSQL-compatible database
- WhiteNoise for compressed static file serving
- Gunicorn for production WSGI serving
- Pillow for image upload processing
- Django Storages and boto3 for S3-compatible media storage
- PostHog for product analytics
- Sentry for error monitoring

## Cloud Infrastructure and External Services

Infrastructure is configured through managed cloud services and environment-based deployment configuration. The production app is deployed on Railway and exposed through Cloudflare at `record-shelf.com`.

Cloud and third-party services configured by the app:

- **Domain:** `record-shelf.com`
- **Application hosting:** Railway
- **Database:** PostgreSQL-compatible database provided through `DATABASE_URL`
- **Media storage:** Cloudflare R2, configured through the S3-compatible `django-storages` backend
- **Email delivery:** Resend, via the custom `users.email_backend.ResendEmailBackend`
- **Analytics:** PostHog
- **Error monitoring:** Sentry
- **Record metadata:** Discogs API
- **Album matching:** Spotify Web API using the client credentials flow
- **Static assets:** Served by the Django app with WhiteNoise

Production media uploads are stored in Cloudflare R2 when `DEBUG=False`. Local development stores media files under `media/`.

## CI/CD

GitHub Actions runs the project pipeline on pull requests and pushes to `main`.

The CI job:

- Installs Python and Node dependencies
- Builds Tailwind CSS
- Runs Django system checks
- Checks for missing migrations
- Verifies static asset collection
- Runs the Django test suite

On pushes to `main`, the deploy job runs after CI succeeds and deploys to Railway with `railway up --ci`.

Required GitHub Actions secrets for deployment:

- `RAILWAY_TOKEN`: Railway project token scoped to the production environment
- `RAILWAY_SERVICE`: Optional Railway service name, useful if the Railway project has multiple services

## Local Development Setup

### Prerequisites

- Python 3.12 or newer
- Node.js and npm
- A local PostgreSQL database, or a SQLite `DATABASE_URL` for lightweight local work
- API credentials for Discogs and, optionally, Spotify

### 1. Clone and enter the project

```bash
git clone <repo-url>
cd record-store
```

### 2. Create a Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
npm install
```

### 4. Configure environment variables

Create a local `.env` file from the example:

```bash
cp .env.example .env
```

For local development, set at least:

```env
DEBUG=True
SECRET_KEY=django-insecure-local-development-only
ALLOWED_HOSTS=127.0.0.1,localhost
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
DATABASE_URL=sqlite:///db.sqlite3
DATABASE_SSL_REQUIRE=False
DISCOGS_API_TOKEN=
```

Use PostgreSQL locally instead of SQLite by setting `DATABASE_URL` to a Postgres connection string, for example:

```env
DATABASE_URL=postgres://USER:PASSWORD@localhost:5432/record_shelf
```

Optional integrations:

```env
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
POSTHOG_PROJECT_TOKEN=
SENTRY_DSN=
RESEND_API_KEY=
```

When `DEBUG=True`, profile images and other uploaded media are stored locally in `media/`, so Cloudflare R2 variables are not required.

### 5. Run database migrations

```bash
python3 manage.py migrate
```

Create an admin user if needed:

```bash
python3 manage.py createsuperuser
```

Optional seed data can be loaded after creating at least one user:

```bash
python3 manage.py seed
```

### 6. Build CSS

```bash
npm run build:css
```

Run this again after changing `assets/css/tailwind.css` or template classes that affect generated styles.

### 7. Start the development server

```bash
python3 manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Environment Variables

### Django and Security

- `SECRET_KEY`: Django secret key. Required when `DEBUG=False`.
- `DEBUG`: `True` for local development, `False` for production.
- `ALLOWED_HOSTS`: Comma-separated hostnames allowed by Django.
- `CSRF_TRUSTED_ORIGINS`: Comma-separated trusted origins, including scheme.
- `SECURE_HSTS_SECONDS`: HSTS max-age in seconds.
- `SECURE_HSTS_INCLUDE_SUBDOMAINS`: Enables HSTS for subdomains.
- `SECURE_HSTS_PRELOAD`: Enables HSTS preload behavior.
- `SECURE_REFERRER_POLICY`: Referrer policy. Defaults to `same-origin`.

### Database and Cache

- `DATABASE_URL`: Database connection URL consumed by `dj-database-url`.
- `DATABASE_SSL_REQUIRE`: `True` in production, usually `False` locally.
- `DJANGO_CACHE_BACKEND`: Optional Django cache backend.
- `DJANGO_CACHE_LOCATION`: Optional cache location/name.

### External APIs

- `DISCOGS_API_TOKEN`: Required for Discogs search and record metadata.
- `SPOTIFY_CLIENT_ID`: Optional Spotify client ID.
- `SPOTIFY_CLIENT_SECRET`: Optional Spotify client secret.

### Email

- `EMAIL_BACKEND`: Defaults to `users.email_backend.ResendEmailBackend`.
- `DEFAULT_FROM_EMAIL`: Default sender address.
- `SUPPORT_EMAIL`: Public support address.
- `HELLO_EMAIL`: General contact address.
- `RESEND_API_KEY`: Resend API key.
- `RESEND_API_URL`: Resend API endpoint.
- `RESEND_FROM_EMAIL`: Sender address used by Resend.
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`: SMTP settings if using a standard SMTP backend.

### Cloudflare R2 Media Storage

Required in production when `DEBUG=False`:

- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `R2_ENDPOINT_URL`
- `R2_PUBLIC_DOMAIN`

Optional locally:

- `MEDIA_URL`: Defaults to `/media/` in development.

### Observability

- `POSTHOG_PROJECT_TOKEN`: Enables PostHog analytics.
- `POSTHOG_HOST`: Defaults to `https://us.i.posthog.com`.
- `POSTHOG_DISABLED`: Set to `true` to disable PostHog.
- `SENTRY_DSN`: Enables Sentry error monitoring when present.

## Common Commands

```bash
python3 manage.py runserver
python3 manage.py test
python3 manage.py makemigrations
python3 manage.py migrate
python3 manage.py createsuperuser
python3 manage.py seed
npm run build:css
```

## Production Notes

For production, configure:

- `DEBUG=False`
- A strong `SECRET_KEY`
- `ALLOWED_HOSTS=record-shelf.com,www.record-shelf.com`
- `CSRF_TRUSTED_ORIGINS=https://record-shelf.com,https://www.record-shelf.com`
- A production `DATABASE_URL` with SSL enabled
- Cloudflare R2 credentials and public domain
- Resend, PostHog, and Sentry credentials as needed

Before deployment, run:

```bash
npm run build:css
python3 manage.py collectstatic
python3 manage.py migrate
```

The production process should run the Django WSGI app with Gunicorn, for example:

```bash
gunicorn config.wsgi:application
```
