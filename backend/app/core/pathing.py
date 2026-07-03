def normalize_base_path(value: str | None) -> str:
    if not value or value == "/":
        return ""

    trimmed = value.strip()
    if not trimmed:
        return ""

    if not trimmed.startswith("/"):
        trimmed = f"/{trimmed}"

    return trimmed.rstrip("/")


def build_api_prefix(base_path: str | None) -> str:
    return f"{normalize_base_path(base_path)}/api/v1"
