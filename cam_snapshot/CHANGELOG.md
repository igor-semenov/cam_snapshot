<!-- https://contributors.home-assistant.io/apps/guides/presentation/#changelog -->
## 1.0.0

- Initial public release.
- Publishes the latest motionEye frame at `/snapshot.jpg?token=...`, with
  `/health` reporting frame age and a `503` for stale frames.
- Automatic re-login on motionEye restarts and password changes.
- Prebuilt `aarch64` and `amd64` images published to GHCR.
