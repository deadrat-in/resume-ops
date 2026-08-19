# Resume Ops API

Podman-first FastAPI service for tailoring a JSON Resume to a job description while protecting immutable resume fields.

[![Documentation](https://img.shields.io/badge/Docs-.env%20Configurator%20%26%20Guide-38bdf8?style=for-the-badge&logo=github)](https://deadrat-in.github.io/resume-ops/)

## Why resume-ops? (The Ethos)

Automated ATS scanners and fast-skimming recruiters often filter out qualified engineers simply because their resume uses different terminology or buries relevant achievements.

`resume-ops` provides an AI tool on **your side of the table**:

- **Signal Over Noise**: Re-aligns your authentic accomplishments to the target job description so your true fit is immediately obvious.
- **Truth Over Fabrication**: Your contact details, job titles, companies, dates, and degrees are strictly immutable. `resume-ops` reformulates and prioritizes real experience; it **never** invents fake projects or unverified skills.
- **Privacy & Self-Hosting**: Runs in your own isolated Podman/Docker container. You retain full control over model routing—whether running 100% offline with local LLMs (vLLM, Ollama) or routing to your trusted API provider of choice.

## What It Does

The service accepts:

- an optional master resume in JSON Resume format (if omitted, falls back to the configured `MASTER_RESUME_PATH`)
- a target job description
- an optional rendering theme
- an optional callback URL for async execution

It then:

- runs a structured multi-step LLM pipeline
- keeps protected fields unchanged
- tailors only allowed sections
- validates the final output against the JSON Resume schema
- renders a PDF using `resumed`

## Tailoring Rules

The service is intentionally conservative.

- `basics` is preserved exactly as provided
- `work` keeps every job and only tailors `summary` and `highlights`
- `education` only tailors `courses`
- `skills` can be regrouped, prioritized, and rewritten, but must remain plausible from the master resume
- `projects` can be selected, omitted, reordered, and rewritten, but new projects must not be invented
- `certificates` are selection-only; certificate content is not rewritten, and the final output is capped at 18 certificates
- `interests` can be tailored if present
- `languages`, `volunteer`, `awards`, `publications`, `references`, `meta`, and other unhandled fields pass through unchanged

## API Modes

### Synchronous

If `callback_url` is omitted, `POST /api/v1/tailor` returns:

- tailored JSON resume
- base64-encoded PDF
- resolved theme

### Asynchronous

If `callback_url` is provided, `POST /api/v1/tailor` returns `202 Accepted` with a `task_id`.

The service then:

- stores the job in SQLite
- processes it in the background
- posts the final result or failure to the callback URL
- exposes status via `GET /api/v1/tasks/{task_id}`

## Endpoints

- `POST /api/v1/tailor`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/themes`
- `GET /healthz`
- `GET /readyz`

### Configuration & Environment Setup

Copy the example environment files to configure model routing, API keys, and theme settings:

1.  **Core API Config (`./.env`)**: Copy from `[./.env.example](./.env.example)`. Note: If you are using vLLM or standard OpenAI endpoints, customize the `DEFAULT_MODEL` (e.g. `ibm-granite/granite-4.1-8b`, prefixing with `openai/` if using an OpenAI key or OpenRouter proxy).
2.  **Scraper Client Config (`./job-ops/.env`)**: Copy from `[./job-ops/.env.example](./job-ops/.env.example)` and configure the scraper credentials. Ensure `RESUME_GENERATION_BACKEND=resume_ops` and `RESUME_OPS_BASE_URL=http://resume-ops:8000` are configured.

---

## Deployment & Running

### Host Volume Permissions (Podman / Rootless Container)

To run in rootless environments securely, the volume mounts in `compose.yaml` utilize the Podman `:U` volume mount suffix (configured as `:Z,U` and `:z,U`).

This flag instructs the container runtime to automatically update host directory ownership to match the UID/GID of the non-root container users (`appuser` and `node` respectively), preventing any `PermissionError: [Errno 13] Permission denied` errors when creating SQLite databases without requiring manual `chmod 777` access on the host.

> [!NOTE]
> **Docker Compatibility**: This setup has been tested using **Podman**. If you are running under rootless Docker, you may need to adjust your volume mount syntax (e.g., removing the `,U` suffix if not supported) or manually apply permissions (such as `chmod -R 777 data/` or setting ownership manually).

### Option 1: Running with Pre-built Registry Images (Recommended)

1.  Follow the **Configuration & Environment Setup** steps above.
2.  **Provide your master resume**: Copy the template from `[master-resume.json.example](./master-resume.json.example)` to `./master-resume.json` in the root `resume-ops` folder.
3.  **Launch the services**:
    ```bash
    podman compose up -d
    ```
    This will pull `ghcr.io/deadrat-in/resume-ops:latest` and `ghcr.io/deadrat-in/job-ops:latest` from the registry and launch them immediately.

Once running:

- **JobOps Web UI**: `http://localhost:3005`
- **resume-ops API**: `http://localhost:8000`

### Option 2: Running with Local Development Build

If you are developing or want to build/recompile the images locally:

```bash
git clone --recurse-submodules https://github.com/deadrat-in/resume-ops.git
cd resume-ops
# Follow the configuration steps (environment and master resume setup) as in Option 1.
podman compose up -d --build
```

_(Note: Because `compose.override.yaml` is present, it automatically compiles the images locally instead of pulling from GHCR.)_

---

## Updating to the Latest Version

### Compose (default)

If you are running the pre-built registry images via `compose.yaml`:

```bash
podman compose pull && podman compose up -d
```

This pulls the latest `ghcr.io/deadrat-in/resume-ops:latest` and `ghcr.io/deadrat-in/job-ops:latest` images from GHCR and restarts the containers in place. Your data (SQLite databases, uploaded resumes, scraped jobs) is stored in the `./data/` host volume and is **never affected** by image updates.

### Podman Quadlets (systemd)

If you are running the containers as systemd services via [Podman Quadlets](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html), pull the new images and restart the units:

```bash
# Pull the latest images
podman pull ghcr.io/deadrat-in/resume-ops:latest
podman pull ghcr.io/deadrat-in/job-ops:latest

# Restart the systemd units (adjust service names to match your .container files)
systemctl --user restart resume-ops.service job-ops.service
```

**Automatic updates (optional)**: Add `AutoUpdate=registry` to your `.container` quadlet unit files, then enable and run `podman-auto-update`:

```ini
# In your .container file:
[Container]
Image=ghcr.io/deadrat-in/resume-ops:latest
AutoUpdate=registry
```

```bash
# Enable the auto-update timer
systemctl --user enable --now podman-auto-update.timer
```

### Rootless Boot Mount Dependencies (Network / FUSE Storage)

If your volume mount (`/data`) resides on a network mount or a FUSE/mergerfs pool (e.g. `/mnt/media`), systemd user services (`systemd --user`) run early during boot and cannot resolve system-level `.mount` units. This can cause Podman to hang or time out during boot.

To prevent boot startup timeouts, add a `[Service]` block to your `.container` file:

```ini
[Service]
ExecStartPre=/usr/bin/sh -c 'while ! mountpoint -q /mnt/media; do sleep 1; done'
TimeoutStartSec=900
Restart=always
RestartSec=5
```

---

## Custom & External Themes

`resume-ops` includes pre-installed `jsonresume-theme-folio` (default) and `jsonresume-theme-stackoverflow`.

### Adding Third-Party Themes

You can install and use any JSON Resume theme from npm **without rebuilding the container image**. `resume-ops` looks for installed themes in `./data/themes` via `NODE_PATH`.

1. Install your desired theme into the mounted data directory:
   ```bash
   npm install --prefix ./data/themes jsonresume-theme-even
   ```
2. Add the theme to `ALLOWED_THEMES` in your `.env`:
   ```ini
   ALLOWED_THEMES=jsonresume-theme-folio,jsonresume-theme-stackoverflow,jsonresume-theme-even
   ```

---

## Example Request & Callback Usage

### List Available Themes

```bash
curl http://127.0.0.1:8000/api/v1/themes
```

### Synchronous Tailoring

If a `MASTER_RESUME_PATH` is configured in your `.env` (or via Docker), you can tailor your resume by simply providing the job description:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tailor \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{
  "job_description": "Looking for a product leader with AI and platform experience.",
  "theme": "jsonresume-theme-folio"
}
JSON
```

If you don't have a default `MASTER_RESUME_PATH` configured, or if you want to override it, you can provide the full JSON resume directly in the payload under `"resume"`:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tailor \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{
  "resume": {
    "basics": {
      "name": "Jane Doe",
      "email": "jane@example.com"
    }
  },
  "job_description": "Looking for a product leader with AI and platform experience."
}
JSON
```

_(Refer to `[master-resume.json.example](./master-resume.json.example)` for the full schema structure.)_

### Asynchronous Tailoring With Callback

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tailor \
  -H "Content-Type: application/json" \
  -d @- <<'JSON'
{
  "resume": {
    "basics": {
      "name": "Jane Doe",
      "email": "jane@example.com"
    }
  },
  "job_description": "Need a technical product manager for an AI platform.",
  "callback_url": "https://example.com/webhooks/resume-ready"
}
JSON
```

---

## Data Storage & Local Development

### Data Storage

By default, the SQLite database is stored under `/data`, and rendered PDFs are saved under `/data/jobs/<task_id>/output.pdf`. In the compose stack, `/data` is mapped to the local `./data/resume-ops` host directory.

### Local Development (Without Container)

Install dependencies from `pyproject.toml` and start:

```bash
uv run python -m resume_ops_api
```

### CLI Usage (Without API Server)

You can also use `resume-ops` directly from your terminal to generate tailored resumes locally:

```bash
# Via container:
podman run --rm \
  --env-file .env \
  -v "$(pwd)":"$(pwd)" \
  -w "$(pwd)" \
  resume-ops \
  resume-ops \
    --resume ./master-resume.json \
    --jd ./target-job.md \
    --output ./tailored-resume.pdf

# Or natively (requires global npm install of resumed & themes):
uv pip install -e .
npm install -g resumed @deadrat/jsonresume-theme-stackoverflow
resume-ops --resume master-resume.json --jd target-job.md --output ./tailored-resume.pdf
```

## Current Limitations

- No authentication is built in
- Background execution is single-process and intended for one API worker
- Theme support is allowlist-based, not dynamic package installation at request time
- The service relies on `resumed` being installed in the runtime environment

## License

This project is licensed under `AGPL-3.0-only`. See [LICENSE](./LICENSE).
