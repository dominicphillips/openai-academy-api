"""Explicit credential loading for the private, single-process collector CLI only."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
from pathlib import Path


def collector_api_key(env_file: Path | None = None) -> str:
    """An explicit file wins; never evaluate it or import other assignments."""
    if env_file is None:
        key = os.environ.get("OPENAI_API_KEY", "")
    else:
        if env_file.stat().st_size > 1048576:
            raise ValueError("Explicit env file exceeds the size limit")
        try:
            text = env_file.read_text(encoding="utf-8")
        except UnicodeError:
            raise ValueError("Explicit env file must be UTF-8") from None
        values = []
        for line in text.splitlines():
            match = re.match(r"^\s*(?:export\s+)?OPENAI_API_KEY\s*=\s*(.*)$", line)
            if match:
                try:
                    parts = shlex.split(match.group(1), comments=True, posix=True)
                except ValueError:
                    raise ValueError("Invalid OPENAI_API_KEY assignment") from None
                if len(parts) != 1:
                    raise ValueError("OPENAI_API_KEY must be one literal nonempty value")
                values.append(parts[0])
        if len(values) != 1:
            raise ValueError("Explicit env file must contain exactly one OPENAI_API_KEY")
        key = values[0]
    if not key or re.search(r"[\s$`\\]", key):
        raise ValueError("OPENAI_API_KEY must be a literal nonempty value")
    return key


def key_fingerprint(key: str) -> str:
    """Private journal identity, never a credential or a public API field."""
    return hashlib.sha256(key.encode()).hexdigest()


def collector_client(key: str):
    """Construct the SDK without ambient OpenAI routing/auth/header overrides.

    This is called only by the private CLI, before controller work starts. Restore
    the process mapping immediately; never use this constructor from the server.
    """
    removed = {
        name: os.environ.pop(name)
        for name in tuple(os.environ)
        if name.startswith(("OPENAI_", "AZURE_OPENAI_"))
    }
    try:
        from openai import DefaultHttpxClient, OpenAI

        return OpenAI(
            api_key=key,
            base_url="https://api.openai.com/v1",
            timeout=15,
            max_retries=0,
            http_client=DefaultHttpxClient(trust_env=False),
        )
    finally:
        os.environ.update(removed)
