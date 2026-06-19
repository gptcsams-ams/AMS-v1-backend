# Redis has been removed. Stub kept so any missed import gives a clear error
# rather than an AttributeError. Remove this file once all callers are gone.

def get_redis():
    raise RuntimeError(
        "Redis has been removed. "
        "Use auth_token_store.py for token operations."
    )

async def init_redis():
    pass

async def close_redis():
    pass
