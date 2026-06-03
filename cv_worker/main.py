import asyncio

from cv_worker.scheduler import run_scheduler


async def main() -> None:
    await run_scheduler()


if __name__ == "__main__":
    asyncio.run(main())
