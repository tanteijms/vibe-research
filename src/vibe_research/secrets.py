from __future__ import annotations

from pathlib import Path


def load_secret_file(path: str | Path = "secrets.txt") -> dict[str, str]:
    """Parse local secrets without printing them."""

    secret_path = Path(path)
    if not secret_path.exists():
        return {}

    secrets: dict[str, str] = {}
    first_api_key: str | None = None
    first_base_url: str | None = None
    for raw_line in secret_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            clean_key = key.strip()
            clean_value = value.strip().strip("'\"")
            secrets[clean_key] = clean_value
            if clean_key == "OPENAI_API_KEY" and clean_value.startswith("sk-"):
                first_api_key = first_api_key or clean_value
            if clean_key == "OPENAI_BASE_URL" and clean_value.startswith(("http://", "https://")):
                first_base_url = first_base_url or clean_value
        else:
            clean_value = line.strip("'\"")
            if clean_value.startswith("sk-"):
                first_api_key = first_api_key or clean_value
            elif clean_value.startswith(("http://", "https://")):
                first_base_url = first_base_url or clean_value

    if first_api_key and "OPENAI_API_KEY" not in secrets:
        secrets["OPENAI_API_KEY"] = first_api_key
    if first_base_url and "OPENAI_BASE_URL" not in secrets:
        secrets["OPENAI_BASE_URL"] = first_base_url
    return secrets
