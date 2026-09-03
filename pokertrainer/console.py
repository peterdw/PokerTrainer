"""Invoer/uitvoer-abstractie, zodat het spel ook zonder echte console testbaar is."""

from __future__ import annotations

from typing import Protocol


class UserIO(Protocol):
    def show(self, text: str = "") -> None: ...

    def ask(self, prompt: str) -> str: ...


class ConsoleIO:
    def show(self, text: str = "") -> None:
        print(text)

    def ask(self, prompt: str) -> str:
        try:
            return input(prompt).strip()
        except EOFError:
            return "q"


class ScriptedIO:
    """Speelt vooraf bepaalde antwoorden af (voor tests en demo's)."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)
        self.output: list[str] = []

    def show(self, text: str = "") -> None:
        self.output.append(text)

    def ask(self, prompt: str) -> str:
        self.output.append(prompt)
        if not self._answers:
            return "q"
        return self._answers.pop(0)


class QuitRequested(Exception):
    """De gebruiker wil het spel verlaten."""
