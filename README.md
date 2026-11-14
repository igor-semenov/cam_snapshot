# Camera Snapshot

A Home Assistant app that republishes the latest motionEye still image on one
stable, token-protected JPEG URL — for dashboards and devices that cannot log
in to motionEye or hold a session cookie.

[![Open your Home Assistant instance and show the app store with a specific repository URL pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Figor-semenov%2Fcam_snapshot)

## Apps

### [Camera Snapshot](./cam_snapshot)

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

Keeps a motionEye session alive, polls `/picture/<camera_id>/current/` and
serves the newest frame at:

```
http://<host>:8099/snapshot.jpg?token=<token>
```

It answers `503` when the frame is stale instead of serving an old picture.
Full documentation: [`cam_snapshot/README.md`](./cam_snapshot/README.md).

## Install

1. Add this repository to the app store (badge above, or **Settings → Apps →
   Install app → ⋮ → Repositories** with
   `https://github.com/igor-semenov/cam_snapshot`).
2. Install **Camera Snapshot**.
3. Set `password` for the motionEye account and a strong `token`.
4. Fetch `http://<host>:8099/snapshot.jpg?token=<token>`.

Prebuilt `aarch64` and `amd64` images are published to GHCR; nothing is
compiled on the device.

## Development

Layout:

```
cam_snapshot/            the app (config.yaml, Dockerfile, server.py)
.github/workflows/       lint + multi-arch image build
repository.yaml          app-store repository metadata
deploy.sh                push a local build to a Home Assistant host
```

Run the server locally; it reads `/data/options.json` inside the app and falls
back to environment variables (upper-cased option names) outside of it:

```bash
cd cam_snapshot
MOTIONEYE_URL=http://127.0.0.1:8765 USERNAME=admin PASSWORD=secret \
TOKEN=dev PORT=8099 python3 -u server.py
curl -s 'http://127.0.0.1:8099/health?token=dev'
```

Deploy a work-in-progress version to a real host (needs an SSH alias and the
`ha` CLI there):

```bash
cp secrets.env.example secrets.env   # fill in once; gitignored
DEPLOY_HOST=pi ./deploy.sh
ssh pi 'ha apps rebuild local_cam_snapshot'
```

`deploy.sh` uploads to `/addons/cam_snapshot`, injects the credentials from
`secrets.env` and drops the `image:` key so the Supervisor builds locally.
Changing only options needs no rebuild; editing `server.py` does.

Release: bump `version` in `cam_snapshot/config.yaml`, add a `CHANGELOG.md`
entry, push to `main`. CI lints the app and publishes the multi-arch image
tagged with that version; make the GHCR package public after the first build.

## License

MIT — see [LICENSE](./LICENSE).

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
