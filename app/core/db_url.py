from sqlalchemy.engine import make_url

# These query params are not accepted by asyncpg or psycopg via the URL
_UNSUPPORTED_PARAMS = {"channel_binding", "sslmode"}


def normalize_database_url(database_url: str, sync: bool = False) -> str:
    url = make_url(database_url)

    if url.drivername in {"postgresql", "postgres", "postgresql+asyncpg", "postgresql+psycopg"}:
        driver = "postgresql+psycopg" if sync else "postgresql+asyncpg"
        cleaned = {k: v for k, v in url.query.items() if k not in _UNSUPPORTED_PARAMS}
        return url.set(drivername=driver, query=cleaned).render_as_string(hide_password=False)

    return url.render_as_string(hide_password=False)


def requires_ssl(database_url: str) -> bool:
    """Return True if the original URL requested SSL."""
    url = make_url(database_url)
    return url.query.get("sslmode") in ("require", "verify-ca", "verify-full")