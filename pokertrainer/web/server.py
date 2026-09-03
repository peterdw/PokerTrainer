"""HTTP-server voor de browserversie, uitsluitend met de standaardbibliotheek.

- Statische bestanden (``static/``) vormen de gebruikersinterface.
- ``/api/...`` levert lesinhoud en bestuurt spelsessies (JSON).
- ``/api/sessions/<id>/stream`` is een Server-Sent Events-stroom: de browser
  ontvangt elke spelgebeurtenis zodra de motor haar publiceert.

Patroon: Facade. ``TrainerBackend`` verbergt sessies en lesinhoud achter een
paar eenvoudige aanroepen, zodat de request-handler alleen HTTP hoeft te kennen.
"""

from __future__ import annotations

import json
import mimetypes
import random
import re
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from ..evaluation import HandEvaluator
from ..quiz import QuizGenerator
from .content import build_content, ranking_quiz_json
from .session import TABLE_PRESETS, SessionBusy, WebSession

STATIC_DIR = Path(__file__).parent / "static"
MAX_SESSIONS = 25


class HttpError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class TrainerBackend:
    """Facade voor de HTTP-laag: lesinhoud en de actieve sessies."""

    def __init__(self) -> None:
        self._content = build_content()
        self._quiz = QuizGenerator(random.Random(), HandEvaluator())
        self._sessions: dict[str, WebSession] = {}
        self._lock = threading.Lock()

    def content(self) -> dict:
        return self._content

    def ranking_quiz(self) -> dict:
        with self._lock:
            return ranking_quiz_json(self._quiz)

    def create_session(self, player_name: str) -> WebSession:
        session = WebSession(player_name)
        with self._lock:
            self._prune()
            self._sessions[session.id] = session
        return session

    def session(self, session_id: str) -> WebSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise HttpError(HTTPStatus.NOT_FOUND, "Onbekende sessie; start opnieuw vanuit het menu.")
        return session

    def _prune(self) -> None:
        """Ruimt afgelopen sessies op zodra het er te veel worden."""
        if len(self._sessions) < MAX_SESSIONS:
            return
        for session_id, session in list(self._sessions.items()):
            if session.finished:
                del self._sessions[session_id]
        while len(self._sessions) >= MAX_SESSIONS:
            oldest_id = next(iter(self._sessions))
            self._sessions.pop(oldest_id).quit()


class TrainerHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], backend: TrainerBackend) -> None:
        super().__init__(address, RequestHandler)
        self.backend = backend


Route = tuple[str, "re.Pattern[str]", str]


class RequestHandler(BaseHTTPRequestHandler):
    server_version = "PokerTrainer/1.0"
    server: TrainerHTTPServer  # type: ignore[assignment]

    ROUTES: list[Route] = [
        ("GET", re.compile(r"/api/content"), "content"),
        ("GET", re.compile(r"/api/quiz/ranking"), "ranking_quiz"),
        ("POST", re.compile(r"/api/sessions"), "create_session"),
        ("GET", re.compile(r"/api/sessions/(?P<sid>[0-9a-f]{32})/stream"), "stream"),
        ("POST", re.compile(r"/api/sessions/(?P<sid>[0-9a-f]{32})/table"), "start_table"),
        ("POST", re.compile(r"/api/sessions/(?P<sid>[0-9a-f]{32})/action"), "action"),
        ("POST", re.compile(r"/api/sessions/(?P<sid>[0-9a-f]{32})/advice"), "advice"),
        ("POST", re.compile(r"/api/sessions/(?P<sid>[0-9a-f]{32})/speed"), "speed"),
        ("POST", re.compile(r"/api/sessions/(?P<sid>[0-9a-f]{32})/quit"), "quit"),
    ]

    @property
    def backend(self) -> TrainerBackend:
        return self.server.backend

    # --- HTTP-werkwoorden ---------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - naam vereist door BaseHTTPRequestHandler
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        """Alleen fouten loggen; het spelverloop zelf is geen serverruis waard."""
        if isinstance(code, int) and code >= 400:
            super().log_request(code, size)

    # --- routering ----------------------------------------------------------
    def _dispatch(self, method: str) -> None:
        parts = urlsplit(self.path)
        try:
            for route_method, pattern, name in self.ROUTES:
                match = pattern.fullmatch(parts.path)
                if match is None:
                    continue
                if route_method != method:
                    raise HttpError(HTTPStatus.METHOD_NOT_ALLOWED, f"{method} is hier niet toegestaan.")
                handler: Callable[[dict[str, str], dict[str, list[str]]], None] = getattr(self, f"_route_{name}")
                handler(match.groupdict(), parse_qs(parts.query))
                return
            if method == "GET":
                self._static(parts.path)
                return
            raise HttpError(HTTPStatus.NOT_FOUND, "Onbekend pad.")
        except HttpError as error:
            self._json({"error": error.message}, error.status)
        except SessionBusy as error:
            self._json({"error": str(error)}, HTTPStatus.CONFLICT)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # de browser heeft de verbinding gesloten

    # --- hulpmiddelen -------------------------------------------------------
    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            raise HttpError(HTTPStatus.BAD_REQUEST, "Ongeldige JSON.") from error
        if not isinstance(data, dict):
            raise HttpError(HTTPStatus.BAD_REQUEST, "Een JSON-object werd verwacht.")
        return data

    def _static(self, path: str) -> None:
        relative = "index.html" if path in ("", "/") else path.removeprefix("/static/").lstrip("/")
        if path not in ("", "/") and not path.startswith("/static/"):
            raise HttpError(HTTPStatus.NOT_FOUND, "Onbekend pad.")
        root = STATIC_DIR.resolve()
        target = (root / relative).resolve()
        if root not in target.parents or not target.is_file():
            raise HttpError(HTTPStatus.NOT_FOUND, "Bestand niet gevonden.")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/javascript", "application/json"):
            content_type += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # --- routes -------------------------------------------------------------
    def _route_content(self, params: dict[str, str], query: dict[str, list[str]]) -> None:
        self._json(self.backend.content())

    def _route_ranking_quiz(self, params: dict[str, str], query: dict[str, list[str]]) -> None:
        self._json(self.backend.ranking_quiz())

    def _route_create_session(self, params: dict[str, str], query: dict[str, list[str]]) -> None:
        body = self._body()
        name = str(body.get("name", ""))[:24]
        session = self.backend.create_session(name)
        self._json({"id": session.id, "name": session.player_name}, HTTPStatus.CREATED)

    def _route_start_table(self, params: dict[str, str], query: dict[str, list[str]]) -> None:
        session = self.backend.session(params["sid"])
        body = self._body()
        lesson = str(body.get("lesson", ""))
        if lesson not in TABLE_PRESETS:
            raise HttpError(HTTPStatus.BAD_REQUEST, f"Onbekende tafel: {lesson!r}.")
        try:
            speed = float(body.get("speed", 1.0))
        except (TypeError, ValueError) as error:
            raise HttpError(HTTPStatus.BAD_REQUEST, "Ongeldig tempo.") from error
        session.start_table(lesson, speed)
        self._json({"ok": True})

    def _route_action(self, params: dict[str, str], query: dict[str, list[str]]) -> None:
        session = self.backend.session(params["sid"])
        session.act(self._body())
        self._json({"ok": True})

    def _route_advice(self, params: dict[str, str], query: dict[str, list[str]]) -> None:
        session = self.backend.session(params["sid"])
        self._json(session.advice())

    def _route_speed(self, params: dict[str, str], query: dict[str, list[str]]) -> None:
        session = self.backend.session(params["sid"])
        try:
            session.set_speed(float(self._body().get("speed", 1.0)))
        except (TypeError, ValueError) as error:
            raise HttpError(HTTPStatus.BAD_REQUEST, "Ongeldig tempo.") from error
        self._json({"ok": True})

    def _route_quit(self, params: dict[str, str], query: dict[str, list[str]]) -> None:
        session = self.backend.session(params["sid"])
        session.quit()
        self._json({"ok": True})

    def _route_stream(self, params: dict[str, str], query: dict[str, list[str]]) -> None:
        session = self.backend.session(params["sid"])
        last_seen = self.headers.get("Last-Event-ID") or (query.get("since") or ["-1"])[0]
        try:
            cursor = int(last_seen) + 1
        except ValueError:
            cursor = 0
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        while True:
            events = session.events_since(cursor, timeout=15.0)
            if not events:
                self.wfile.write(b": ping\n\n")
            for event in events:
                data = json.dumps(event, ensure_ascii=False)
                self.wfile.write(f"id: {event['id']}\ndata: {data}\n\n".encode("utf-8"))
                cursor = event["id"] + 1
            self.wfile.flush()


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    server = TrainerHTTPServer((host, port), TrainerBackend())
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"♠ ♥ ♦ ♣  Poker Trainer draait op {url}   (Ctrl+C om te stoppen)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTot de volgende keer. Veel succes aan de tafels!")
    finally:
        server.server_close()
