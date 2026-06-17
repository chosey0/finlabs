from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from rich_inquirer import ConfirmPrompt, SelectPrompt, TextPrompt

T = TypeVar("T")


def choose(prompt: str, *, choices: Sequence[tuple[str, T]]) -> T:
    labels = [label for label, _value in choices]
    selected = SelectPrompt(prompt, choices=labels).ask()
    if selected is None:
        raise KeyboardInterrupt
    for label, value in choices:
        if label == selected:
            return value
    raise ValueError(f"unknown selection: {selected}")


def text(prompt: str, default: str = "") -> str:
    message = f"{prompt} ({default})" if default else prompt
    value = TextPrompt(message).ask()
    if value is None:
        raise KeyboardInterrupt
    result = str(value)
    return result if result else default


def secret(prompt: str) -> str:
    value = TextPrompt(prompt, password=True).ask()
    if value is None:
        raise KeyboardInterrupt
    return str(value)


def confirm(prompt: str, *, default: bool = True) -> bool:
    value = ConfirmPrompt(prompt, default=default).ask()
    if value is None:
        raise KeyboardInterrupt
    return bool(value)
