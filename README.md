
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/logo-white.png">
    <img src="docs/images/logo-blue.png" alt="ArcSpec" width="320">
  </picture>
 <br>  

# Self-hosted tool to create and manage architecture and requirement specifications

User manual: [docs/manual/README.md](docs/manual/README.md)

![Project page](docs/images/readme-project.png)

## Install

```
cp .env.example .env
docker compose up -d --build
docker compose exec web python manage.py migrate
```

## Environment variables

| Variable | Value | Required |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.production`. Default: `config.settings.development`. | Yes |
| `SECRET_KEY` | Random string, at least 50 characters. | Yes |
| `ALLOWED_HOSTS` | Host names without scheme, comma-separated, `localhost` included, e.g. `arcspec.example.com,localhost`. | Yes |
| `SITE_URL` | Public address with scheme, no trailing slash, e.g. `https://arcspec.example.com`. | Yes |
| `POSTGRES_DB` | Database name. | Yes |
| `POSTGRES_USER` | Database user. | Yes |
| `POSTGRES_PASSWORD` | Database password. | Yes |
| `ENTRA_TENANT_ID` | Microsoft Entra ID tenant. Empty disables Microsoft sign-in. | No |
| `ENTRA_CLIENT_ID` | Microsoft Entra ID application ID. | No |
| `ENTRA_CLIENT_SECRET` | Microsoft Entra ID client secret. | No |
| `AUTH_CALLBACK_PREFIX` | Any URL-safe string. Redirect URI to register in Entra: `<SITE_URL>/auth/callback/<AUTH_CALLBACK_PREFIX>/microsoft/login/callback/` | Yes |
| `EMAIL_HOST` | SMTP server host name without scheme, e.g. `smtp.example.com`. | Yes |
| `EMAIL_PORT` | SMTP port, default 587. | No |
| `EMAIL_HOST_USER` | SMTP user. | Yes |
| `EMAIL_HOST_PASSWORD` | SMTP password. | Yes |
| `DEFAULT_FROM_EMAIL` | Sender address. | No |

## First administrator

```
docker compose exec web python manage.py create_admin admin@example.com
```

Creates the first administrator and prints a generated password.

## Roles

System roles:

| Role | Can |
|---|---|
| Viewer | Open projects they are a member of. |
| User | Viewer, plus create projects and templates. |
| Administrator | User, plus admin of every project, the Admin Panel, any custom template. |

Project roles:

| Role | Can |
|---|---|
| Viewer | Read, export, comment. |
| Editor | Viewer, plus edit sections, items, tags, attachments, links, attributes. |
| Admin | Editor, plus edit, archive and delete the project, manage members, restore versions. |

## Document templates

A project is created from a document template. Users create their own document templates from scratch or by duplicating another.

The built-in templates are included:

| Template | Type | Sections |
|---|---|---|
| Software Requirements Specification | Requirements | 18 |
| OWASP ASVS 5.0 | Requirements | 97 |
| arc42 Architecture Documentation | Architecture | 24 |
| Software Test Documentation | Test Cases | 34 |
| NIST SP 800-30 Risk Assessment | Risk Analysis | 29 |
| GDPR Compliance Documentation | Custom | 52 |
| NIS2 Compliance Documentation | Custom | 31 |
| EU AI Act Compliance Documentation | Custom | 46 |

## Scheduled jobs

Add these lines with `crontab -e`, replacing `/path/to/arcspec` with the directory holding `docker-compose.yml`:

```
17 2 * * * cd /path/to/arcspec && docker compose exec -T web python manage.py auto_archive_projects
47 2 * * * cd /path/to/arcspec && docker compose exec -T web python manage.py auto_delete_archived
0 7 * * 1 cd /path/to/arcspec && docker compose exec -T web python manage.py send_weekly_digest
```

## Screenshots

Dashboard:

![Dashboard](docs/images/readme-dashboard.png)

Project structure:

![Project Structure dialog](docs/images/readme-structure.png)

Templates:

![Templates page](docs/images/readme-templates.png)

PDF export:

![Pages of a PDF export](docs/images/readme-export.png)

## License

[AGPL-3.0](LICENSE)
