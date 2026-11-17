"""The generator's id formats: candidates C001.., sectors S001.. (numbers start at 1)."""


def candidate_id(n: int) -> str:
    return f"C{n:03d}"


def sector_id(n: int) -> str:
    return f"S{n:03d}"
