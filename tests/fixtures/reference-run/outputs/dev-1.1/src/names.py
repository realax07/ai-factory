def clean(name: str) -> str:
    """Имя без пробелов по краям."""
    return (name or "").strip()
