"""Concurrent load test for rate limiting and per-user context state.

Example:
    python tests/load_test.py --users 100 --requests-per-user 20 --workers 16
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.rate_limiter import UserRateLimiter
from modules.user_context import UserContextStore


@dataclass
class LoadResult:
    completed: int = 0
    rejected: int = 0
    errors: int = 0


def run_load_test(users: int, requests_per_user: int, workers: int) -> dict[str, float | int]:
    """Run concurrent state operations and return aggregate metrics."""
    if users < 1 or requests_per_user < 1 or workers < 1:
        raise ValueError("users, requests_per_user, and workers must be positive")

    started_at = time.perf_counter()
    result = LoadResult()
    context_store = UserContextStore(max_turns=6, max_chars=6000)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as database_file:
        database_path = database_file.name

    limiter = UserRateLimiter(
        db_path=database_path,
        requests_per_minute=requests_per_user + 1,
        tokens_per_minute=requests_per_user * 100 + 1,
    )

    def run_user(user_id: int) -> tuple[int, int, int]:
        completed = 0
        rejected = 0
        errors = 0
        try:
            for request_number in range(requests_per_user):
                allowed, _reason = limiter.check_request_allowed(user_id)
                tokens = 100
                tokens_allowed, _token_reason = limiter.check_tokens_allowed(user_id, tokens)
                if not allowed or not tokens_allowed:
                    rejected += 1
                    continue
                limiter.record_request(user_id, tokens)
                context_store.add_turn(user_id, f"question-{request_number}", "answer")
                completed += 1
        except Exception:
            errors += 1
        return completed, rejected, errors

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(run_user, user_id) for user_id in range(users)]
            for future in as_completed(futures):
                completed, rejected, errors = future.result()
                result.completed += completed
                result.rejected += rejected
                result.errors += errors
    finally:
        try:
            os.unlink(database_path)
        except OSError:
            pass

    elapsed_seconds = time.perf_counter() - started_at
    total_operations = users * requests_per_user
    return {
        "users": users,
        "requests_per_user": requests_per_user,
        "workers": workers,
        "total_operations": total_operations,
        "completed": result.completed,
        "rejected": result.rejected,
        "errors": result.errors,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "operations_per_second": round(total_operations / elapsed_seconds, 2),
    }


def main() -> int:
    """Parse load-test options and print results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--requests-per-user", type=int, default=20)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    metrics = run_load_test(args.users, args.requests_per_user, args.workers)
    for name, value in metrics.items():
        print(f"{name}: {value}")
    return 0 if metrics["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
