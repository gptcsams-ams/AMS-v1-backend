from sqlalchemy.engine import make_url

# Parameters not supported by asyncpg or psycopg2 but added by some connection string generators
_UNSUPPORTED_PARAMS = {"channel_binding"}


def normalize_database_url(database_url: str, sync: bool = False) -> str:
    url = make_url(database_url)

    if url.drivername in {"postgresql", "postgres", "postgresql+asyncpg", "postgresql+psycopg2"}:
        driver = "postgresql+psycopg2" if sync else "postgresql+asyncpg"
        # Strip query params unsupported by the target driver
        cleaned = {k: v for k, v in url.query.items() if k not in _UNSUPPORTED_PARAMS}
        return url.set(drivername=driver, query=cleaned).render_as_string(hide_password=False)

    return url.render_as_string(hide_password=False)