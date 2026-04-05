from datetime import datetime

def parse_dt(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")


def parse_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes")
