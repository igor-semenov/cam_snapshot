#!/usr/bin/env python3
"""Publish the latest motionEye still image on a stable tokenized URL.

Runs as a Home Assistant add-on next to motionEye. Logs in with a session
cookie (motionEye >= 0.44 no longer accepts _username/_signature), grabs
/picture/<id>/current/ once per `refresh_seconds` and serves the last frame
at http://<host>:<port>/snapshot.jpg?token=<token>.
"""

import hmac
import http.cookiejar
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPTIONS_FILE = "/data/options.json"


def _options():
    try:
        with open(OPTIONS_FILE, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {}
    except ValueError as error:
        print(f"cannot parse {OPTIONS_FILE}: {error}", flush=True)
        return {}


OPTIONS = _options()


def opt(key, default):
    if key in OPTIONS and OPTIONS[key] not in (None, ""):
        return OPTIONS[key]
    return os.environ.get(key.upper(), default)


MOTIONEYE_URL = str(opt("motioneye_url", "http://127.0.0.1:8765")).rstrip("/")
CAMERA_ID = str(opt("camera_id", "1"))
USERNAME = str(opt("username", "admin"))
PASSWORD = str(opt("password", ""))
TOKEN = str(opt("token", ""))
REFRESH = float(opt("refresh_seconds", 1.0))
STALE_AFTER = float(opt("stale_after_seconds", 60))
PORT = int(opt("port", 8099))

LOGIN_URL = f"{MOTIONEYE_URL}/login"
PICTURE_URL = f"{MOTIONEYE_URL}/picture/{CAMERA_ID}/current/"


def log(message):
    print(f"{time.strftime('%H:%M:%S')} {message}", flush=True)


class AuthError(Exception):
    """Session is gone or credentials are rejected."""


class NoFrame(Exception):
    """Authenticated, but motion has no frame to give."""


class Grabber:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.lock = threading.Lock()
        self.frame = None
        self.frame_ts = 0.0
        self.logged_in = False
        self.next_login_at = 0.0

    def login(self):
        now = time.monotonic()
        if now < self.next_login_at:
            raise AuthError("login backoff")
        data = urllib.parse.urlencode(
            {"username": USERNAME, "password": PASSWORD}
        ).encode()
        request = urllib.request.Request(
            LOGIN_URL,
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with self.opener.open(request, timeout=10) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            self.next_login_at = now + 30
            raise AuthError(
                f"login HTTP {error.code}: {error.read()[:200]!r}"
            ) from None
        except OSError as error:
            self.next_login_at = now + 10
            raise AuthError(f"login {error}") from None
        self.logged_in = True
        self.next_login_at = 0.0
        log(f"logged in as {USERNAME}: {body.decode(errors='replace')[:120]}")

    def picture(self):
        request = urllib.request.Request(PICTURE_URL, headers={"Accept": "image/jpeg"})
        try:
            with self.opener.open(request, timeout=15) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            error.read()
            if error.code in (401, 403):
                self.logged_in = False
                raise AuthError(f"picture HTTP {error.code}") from None
            raise NoFrame(f"picture HTTP {error.code}") from None
        except OSError as error:
            raise NoFrame(str(error)) from None

    def loop(self):
        failures = 0
        auth_failures = 0
        while True:
            started = time.monotonic()
            try:
                if not self.logged_in:
                    self.login()
                data = self.picture()
                if not data:
                    raise NoFrame("empty body")
                with self.lock:
                    self.frame = data
                    self.frame_ts = time.time()
                if failures:
                    log(f"capture recovered after {failures} failed attempts")
                failures = 0
                auth_failures = 0
            except AuthError as error:
                failures += 1
                auth_failures += 1
                log(f"auth problem ({auth_failures}): {error}")
                if auth_failures > 1:
                    time.sleep(min(60, 5 * auth_failures))
                    continue
            except NoFrame as error:
                failures += 1
                if failures in (1, 10) or failures % 60 == 0:
                    log(f"no frame ({failures} attempts): {error}")
            except Exception as error:  # noqa: BLE001 - keep the loop alive
                failures += 1
                log(f"unexpected error: {error!r}")
            time.sleep(max(0.0, REFRESH - (time.monotonic() - started)))


GRABBER = Grabber()


class Handler(BaseHTTPRequestHandler):
    server_version = "cam-snapshot/1.0"
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._serve(head_only=False)

    def do_HEAD(self):
        self._serve(head_only=True)

    def log_message(self, *args):
        """Silence per-request logging: one request per second per client."""

    def _json(self, status, payload, head_only):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def _serve(self, head_only):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path not in ("/snapshot.jpg", "/snapshot", "/health"):
            self._json(404, {"error": "not found"}, head_only)
            return

        if TOKEN:
            provided = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
            if not hmac.compare_digest(provided, TOKEN):
                self._json(403, {"error": "forbidden"}, head_only)
                return

        with GRABBER.lock:
            frame, frame_ts = GRABBER.frame, GRABBER.frame_ts

        age = time.time() - frame_ts if frame_ts else None

        if path == "/health":
            self._json(
                200,
                {
                    "logged_in": GRABBER.logged_in,
                    "frame_size": len(frame) if frame else 0,
                    "frame_age_seconds": round(age, 1) if age is not None else None,
                    "stale": age is None or age > STALE_AFTER,
                    "source": PICTURE_URL,
                },
                head_only,
            )
            return

        if frame is None:
            self._json(503, {"error": "no frame yet"}, head_only)
            return
        if age is not None and age > STALE_AFTER:
            self._json(
                503,
                {"error": "stale frame", "age_seconds": round(age, 1)},
                head_only,
            )
            return

        try:
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.send_header("Cache-Control", "no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Frame-Age", f"{age:.1f}")
            self.end_headers()
            if not head_only:
                self.wfile.write(frame)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    if not PASSWORD:
        log("warning: empty password configured")
    if not TOKEN:
        log("warning: token is empty, endpoint is unauthenticated")
    log(f"source {PICTURE_URL} as '{USERNAME}', refresh {REFRESH}s")

    threading.Thread(target=GRABBER.loop, daemon=True).start()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True
    log(f"serving http://0.0.0.0:{PORT}/snapshot.jpg")
    server.serve_forever()


if __name__ == "__main__":
    main()
