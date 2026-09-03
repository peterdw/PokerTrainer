"""De browserlaag: adapters, presenter, sessie en HTTP-server."""

import json
import threading
import time
import urllib.request

from pokertrainer.web.server import TrainerBackend, TrainerHTTPServer
from pokertrainer.web.session import WebSession


def _drain(session, cursor, on_event, timeout=60.0):
    """Leest gebeurtenissen tot ``on_event`` True teruggeeft; geeft de nieuwe cursor terug."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event in session.events_since(cursor, timeout=1.0):
            cursor = event["id"] + 1
            if on_event(event):
                return cursor
    raise AssertionError("Verwachte gebeurtenis bleef uit.")


def test_practice_table_runs_ten_hands_with_a_folding_human():
    session = WebSession("Tester", seed=11)
    session.start_table("oefenen", speed=0)  # geen pauzes
    seen = {"decisions": 0, "finished": None, "bot_cards_leaked": False}
    revealed_this_hand: set[str] = set()

    def on_event(event):
        if event["type"] == "hand_started":
            revealed_this_hand.clear()
        if event["type"] == "showdown":
            revealed_this_hand.add(event["player"])
        for seat in event.get("state", {}).get("seats", []):
            if not seat["is_human"] and seat["cards"] and seat["name"] not in revealed_this_hand:
                seen["bot_cards_leaked"] = True
        if event["type"] == "decision":
            seen["decisions"] += 1
            assert event["legal"]["max_raise_to"] >= event["legal"]["min_raise_to"]
            assert "advice" in event, "de oefentafel geeft automatisch advies"
            session.act({"type": "fold"})
        if event["type"] == "lesson_finished":
            seen["finished"] = event
            return True
        return False

    _drain(session, 0, on_event)
    assert seen["decisions"] >= 10
    assert seen["finished"]["hands"] == 10
    assert seen["finished"]["outcome"] == "finished"
    assert not seen["bot_cards_leaked"]
    assert not session.running


def test_quit_ends_the_table_and_advice_is_only_available_on_turn():
    session = WebSession("Tester", seed=3)
    session.start_table("toernooi", speed=0)
    events = {}

    def until_decision(event):
        if event["type"] == "table_started":
            events["table"] = event
        return event["type"] == "decision"

    cursor = _drain(session, 0, until_decision)
    assert events["table"]["auto_advice"] is False
    assert len(events["table"]["state"]["seats"]) == 6

    advice = session.advice()
    assert advice["action"]["type"] in {"fold", "check", "call", "bet", "raise", "all-in"}
    assert advice["lines"]

    session.quit()
    _drain(session, cursor, lambda e: e["type"] == "lesson_finished" and e["outcome"] == "quit")
    session._thread.join(timeout=5)
    assert not session.running


def test_http_api_serves_content_and_streams_events():
    server = TrainerHTTPServer(("127.0.0.1", 0), TrainerBackend())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    try:
        content = call("/api/content")
        assert [lesson["key"] for lesson in content["lessons"]] == ["rangschikking", "regels", "oefenen", "toernooi"]
        assert len(content["ranking"]["categories"]) == 10
        quiz = call("/api/quiz/ranking")
        assert len(quiz["questions"]) == 6 and len(quiz["showdowns"]) == 4

        with urllib.request.urlopen(base + "/", timeout=10) as response:
            assert b"Poker Trainer" in response.read()

        created = call("/api/sessions", {"name": "Rots"})
        assert created["name"] == "Rots (jij)", "een botnaam wordt ontdubbeld"
        session_id = created["id"]
        call(f"/api/sessions/{session_id}/table", {"lesson": "oefenen", "speed": 0})

        with urllib.request.urlopen(base + f"/api/sessions/{session_id}/stream", timeout=30) as stream:
            first = stream.readline().decode("utf-8")
            assert first.startswith("id: 0")
            payload = json.loads(stream.readline().decode("utf-8").removeprefix("data: "))
            assert payload["type"] == "table_started"
        call(f"/api/sessions/{session_id}/quit", {})
    finally:
        server.shutdown()
        server.server_close()
