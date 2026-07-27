# Environment Status — 2026-07-26

## Local

- Git repository initialized and tracking `origin/main`.
- Node.js and npm available; use `npm.cmd` under the current Windows PowerShell policy.
- Python virtual environment created for the FastAPI backend.
- GitHub CLI 2.96.0 available from the ignored local `work/` tool directory.
- Frontend lint and production build pass.
- Backend tests pass.
- Production dependency audit reports zero known vulnerabilities.
- Development-only lint dependencies still report upstream advisories; the
  available major upgrade currently breaks `eslint-config-next`, so it is not
  forced into the project.
- No likely embedded secrets found in the tracked project files.

## Connected services

- GitHub: authenticated as `lssdashuaige-hue`.
- Repository: `https://github.com/lssdashuaige-hue/program`.
- Supabase: connector authenticated; organization `lssdashuaige-hue's Org` is connected.
- Supabase PAS project: `PAS` (`qhynfdiiicebnjfukwaw`) is active and healthy in Singapore.
- Database: the initial PAS schema is applied with RLS enabled on all public tables.
- Database security advisor: no findings.
- Vercel: connected, no PAS deployment created.
- Render: no PAS service created.
- Cloudflare: no PAS domain or DNS configuration created.

## Cost and safety

- The PAS Supabase project is on the Free plan at `$0/month`.
- Two unused Supabase projects were permanently deleted before PAS was created.
- Local environment files contain only the project URL and publishable key and remain ignored by Git.
