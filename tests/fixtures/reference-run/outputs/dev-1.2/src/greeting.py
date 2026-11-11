from src.names import clean


def greet(name: str) -> str:
    """Приветствие по имени (FR-1); пустое имя — гость (FR-2)."""
    return f"Привет, {clean(name) or 'гость'}!"
