from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode


def build_signed_media_url(path: str, secret: str, expires_minutes: int = 30) -> str:
    exp = int((datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)).timestamp())
    token = f"{hash((path, secret, exp)) & 0xFFFFFFFF:x}"
    return f"{path}?{urlencode({'exp': exp, 'sig': token})}"
