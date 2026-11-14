# AGENTS.md

Home Assistant **app repository**: one app that proxies a motionEye camera into
a token-protected JPEG URL. Single stdlib-only Python file, no tests, no local
build step, no package manifest.

## Layout

- `cam_snapshot/` — the app. The folder name **must** equal `slug` in
  `config.yaml`; the Supervisor discovers apps by scanning for `config.yaml`, so
  keep app files here and never add a second one at the repo root.
  - `server.py` — options loader, motionEye session poller (`Grabber`), HTTP
    server (`Handler`).
  - `config.yaml` — manifest, options, schema, `image:` (GHCR), arch list.
  - `Dockerfile` — single source of truth for the build: multi-platform
    `ghcr.io/home-assistant/base:3.24` base plus `python3`.
  - `CHANGELOG.md` — what the app store shows; update with each version bump.
- `repository.yaml` — store metadata (name, url, maintainer).
- `.github/workflows/lint.yaml` — `frenck/action-app-linter` + HA find-apps.
- `.github/workflows/build.yaml` — multi-arch build, pushes to
  `ghcr.io/igor-semenov/cam-snapshot` on `main`, PRs build without pushing.
- `deploy.sh` — dev-only upload to a real host; not used by end users.
- `secrets.env` — gitignored, mode 600; template in `secrets.env.example`.
  Never commit, print, or copy its values into tracked files.

## Local run / verification

There is no `requirements.txt`; `python3 server.py` is the whole dependency set.
`/data/options.json` only exists inside the app, so locally use env vars (the
options file wins over env; empty option values fall through to env):

```bash
cd cam_snapshot
MOTIONEYE_URL=http://127.0.0.1:8765 CAMERA_ID=1 USERNAME=admin \
PASSWORD=secret TOKEN=dev PORT=8099 python3 -u server.py
curl -s 'http://127.0.0.1:8099/health?token=dev'
# Set USERNAME/PASSWORD explicitly: opt() falls back to the *generic* env var
# name, so an inherited USERNAME (e.g. the login name) is picked up otherwise.
# Env vars only apply to direct `python3 server.py` runs: s6's /init does not
# forward `docker run -e` into the app, so the image must get /data/options.json.
python3 -m py_compile server.py   # syntax check
docker build -t cam-snapshot:test .   # same Dockerfile CI builds
```

Endpoints: `/snapshot.jpg` (alias `/snapshot`) and `/health`, both require
`?token=` when a token is configured (constant-time compare, `403` otherwise).
A frame older than `stale_after_seconds`, or no frame yet, returns `503` — this
is intentional so a dead camera is visible.

## Deploy / release

- Local test on hardware: `DEPLOY_HOST=pi ./deploy.sh` then
  `ssh pi 'ha apps rebuild local_cam_snapshot'`. `deploy.sh` injects
  `secrets.env`, uploads to `/addons/cam_snapshot` and strips `image:` so the
  Supervisor builds locally instead of pulling GHCR; the local slug is
  `local_cam_snapshot`. Option-only changes need no rebuild.
- Release: bump `version` in `cam_snapshot/config.yaml`, add a
  `CHANGELOG.md` entry, push to `main`. CI lints, builds and publishes the
  multi-arch image under the `image:` path; the first build needs the GHCR
  package switched to public in GitHub settings.
- `build.yaml` is retired: don't add one back. The base image and build args
  live in the `Dockerfile`, which must stay buildable with plain
  `docker build cam_snapshot` (the CI action passes `BUILD_ARCH` only).
- Changing `image:` means changing the published package name too; CI pushes
  `<arch>-cam-snapshot` tags and then the multi-arch manifest.

## Gotchas

- `deploy.sh` rewrites secrets in the temp copy only; putting credentials in
  `config.yaml` is pointless and leaks them.
- Its renderer splits `config.yaml` on `"\nschema:"` and expects exactly one
  `^  username:`/`password:`/`token:` line inside `options:`. Keep that section
  order, two-space indent, and one occurrence per key or deploy aborts.
- motionEye >= 0.44 dropped query/Basic auth; auth is a session cookie held in
  memory. `401`/`403` from `/picture/.../current/` means re-login, and the cookie
  dies on motionEye restart or password change — the grabber handles this, so
  don't "fix" 403s by adding credentials to the picture URL.
- `opt()` converts option names to upper-case env vars (`refresh_seconds` →
  `REFRESH_SECONDS`); any new option needs an `options:` entry, a `schema:`
  entry, and a README table row.
- `host_network: true` means `port` binds directly on the host; the app only
  needs the Alpine `python3` from the Dockerfile.
