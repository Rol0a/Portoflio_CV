"""Run the data-retention sweep once and report what it deleted.

The backend normally does this on a timer (app/main.py's lifespan task), so
this script is for the cases where that isn't what you want:

    # inspect current state without deleting anything
    docker compose exec backend python -m scripts.purge_retention --dry-run

    # force a sweep now
    docker compose exec backend python -m scripts.purge_retention

    # or from cron, with RETENTION_PURGE_ENABLED=false in .env
    0 4 * * *  docker compose exec -T backend python -m scripts.purge_retention

Retention windows live in app/services/retention_service.py, not here — this
is only an entry point.
"""

import argparse
import asyncio

from app.database import async_session_factory, engine
from app.services import retention_service


def _format_age(days: float | None) -> str:
    return "empty" if days is None else f"{days:.1f}d old"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the oldest row in each governed table without deleting anything",
    )
    args = parser.parse_args()

    try:
        async with async_session_factory() as db:
            before = await retention_service.oldest_row_ages(db)
            print("oldest row per table:")
            for table, age in before.items():
                print(f"  {table:20} {_format_age(age)}")

            if args.dry_run:
                print("\n--dry-run: nothing deleted")
                return

            deleted = await retention_service.purge_all(db)
            total = sum(deleted.values())
            print(f"\ndeleted {total} row(s):")
            for table, count in deleted.items():
                print(f"  {table:20} {count}")

            if total:
                after = await retention_service.oldest_row_ages(db)
                print("\noldest row per table after purge:")
                for table, age in after.items():
                    print(f"  {table:20} {_format_age(age)}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
