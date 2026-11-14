# Camera Snapshot

Publishes the latest still image from the local motionEye app on one stable,
token-protected URL:

```
http://<pi-address>:8099/snapshot.jpg?token=<token>
```

This exists because motionEye 0.44 removed `_username`/`_signature` query
authentication and HTTP Basic auth: the only way in is a 24-hour session cookie
obtained with `POST /login`. Devices like MagicMirror can send neither a login
form nor cookies, so the session is kept here, on the Pi, and the outside world
only sees a plain JPEG URL.

Images are published for `aarch64` and `amd64`, so no build happens on the
device.

## How it works

* `server.py` logs in to motionEye as `username`/`password`, stores the session
  cookie in memory and re-logs in automatically when the cookie expires
  (24 h), when motionEye restarts (its session store is in-memory and its cookie
  signing key is regenerated on every start) or after a password change — the
  signal for that is always `403 unauthorized`.
* It fetches `/picture/<camera_id>/current/` every `refresh_seconds` and keeps
  the last non-empty frame in memory. Nothing is written to disk.
* `GET /snapshot.jpg?token=...` returns that frame with `Cache-Control:
  no-store`; `GET /health?token=...` returns JSON with the frame age.
* If the frame is older than `stale_after_seconds` the endpoint answers `503`
  instead of serving an old picture, so a dead camera is visible rather than
  silently frozen.

## Options

| Option | Default | Meaning |
|---|---|---|
| `motioneye_url` | `http://127.0.0.1:8765` | motionEye address reachable from the app |
| `camera_id` | `1` | motionEye camera id |
| `username` | `admin` | motionEye account. `user` (the "normal" account) is enough: `/picture/.../current/` only requires a logged-in user, not admin |
| `password` | — | password for that account |
| `token` | — | shared secret expected in the `token` query parameter; empty means no auth at all |
| `refresh_seconds` | `1` | how often motionEye is polled |
| `stale_after_seconds` | `60` | age after which the endpoint starts answering `503` |
| `port` | `8099` | HTTP port on the host (the app uses host networking) |

Options can be edited in the app UI; changing them restarts the app.

## Consuming the URL

MagicMirror `MMM-WebcamImage`:

```js
{
  module: "MMM-WebcamImage",
  position: "top_right",
  config: {
    url: "http://192.168.3.102:8099/snapshot.jpg?token=<token>",
    refreshInterval: 1000,
    width: "400px"
  }
}
```

## Security notes

* The token is a bearer credential: anyone who has the URL can see the camera.
  Rotate it by changing the option and restarting the app.
* Only port `8099` is exposed; motionEye itself and its credentials stay local.
  Do not publish the port to the internet.
* Prefer the `user` (normal) motionEye account over `admin` for this app.
