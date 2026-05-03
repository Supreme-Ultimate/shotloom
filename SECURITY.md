# Security Policy

## Supported Versions

This project is currently pre-1.0. Security fixes are applied to the default branch.

## Reporting A Vulnerability

Please report vulnerabilities privately to the project maintainer instead of opening a public issue. Include:

- Affected version or commit
- Reproduction steps
- Impact assessment
- Suggested fix, if available

## Deployment Security Checklist

Before running in production:

- Replace `SECRET_KEY` with a random value of at least 32 characters.
- Replace `POSTGRES_PASSWORD` with a strong password.
- Keep `DASHSCOPE_API_KEY` out of git, logs, screenshots, and client-side code.
- Set `ENV=production`.
- Set `COOKIE_SECURE=true` when serving over HTTPS.
- Restrict `CORS_ORIGINS` to trusted origins only.
- Put the service behind HTTPS and a reverse proxy/firewall.
- Back up Postgres volumes and uploaded videos according to your retention policy.
- Avoid exposing backend, Postgres, or Redis ports directly to the public internet.

## User Content

The app processes uploaded videos and generated analysis. Treat uploads, thumbnails, clips, reports, and logs as private user data.

## Prompt Configs

Prompt profiles can contain private domain logic. Do not commit production-only prompt profiles if they are sensitive.
