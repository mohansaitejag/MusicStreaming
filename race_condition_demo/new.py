import argparse
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from mysql.connector.errors import PoolError


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from backend.db.connection import get_connection


DEFAULT_SONG_ID = 31
DEFAULT_THREADS = 100
DEFAULT_WORKERS = 10
DEFAULT_USER_IDS = [1, 2, 3, 4, 5]


def get_connection_with_retry(max_attempts=100, delay=0.05):
    for attempt in range(max_attempts):
        try:
            return get_connection()
        except PoolError:
            if attempt == max_attempts - 1:
                raise
            time.sleep(delay)


def fetch_all(query, params=()):
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def fetch_one(query, params=()):
    rows = fetch_all(query, params)
    return rows[0] if rows else None


def print_state(song_id, label):
    song = fetch_one(
        """
        SELECT *
        FROM songs
        WHERE song_id = %s
        """,
        (song_id,),
    )
    history = fetch_all(
        """
        SELECT *
        FROM user_history
        WHERE song_id = %s
        ORDER BY user_id
        """,
        (song_id,),
    )
    summary = fetch_one(
        """
        SELECT COUNT(*) AS history_rows, COALESCE(SUM(listening_count), 0) AS total_listens
        FROM user_history
        WHERE song_id = %s
        """,
        (song_id,),
    ) or {"history_rows": 0, "total_listens": 0}

    print(f"\n=== {label} ===")
    print("songs:")
    print(song)
    print("user_history:")
    for row in history:
        print(row)
    print("summary:")
    print(summary)

    return {
        "song": song,
        "history": history,
        "summary": summary,
    }


def unsafe_play_song(user_id, song_id):
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()

            cur.execute(
                """
                SELECT num_plays, num_likes, num_downloads
                FROM songs
                WHERE song_id = %s
                """,
                (song_id,),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False, "song not found"

            num_plays, num_likes, num_downloads = row
            time.sleep(random.uniform(0.01, 0.05))

            cur.execute(
                """
                INSERT INTO user_history(user_id, song_id, listening_time, listening_count)
                VALUES(%s, %s, NOW(), 1)
                ON DUPLICATE KEY UPDATE listening_count = listening_count + 1, listening_time = NOW()
                """,
                (user_id, song_id),
            )

            new_num_plays = num_plays + 1
            new_popularity = (new_num_plays * 0.6) + (num_likes * 0.3) + (num_downloads * 0.1)
            cur.execute(
                """
                UPDATE songs
                SET num_plays = %s,
                    popularity_score = %s
                WHERE song_id = %s
                """,
                (new_num_plays, new_popularity, song_id),
            )

            conn.commit()
            return True, None
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            cur.close()
    finally:
        conn.close()


def locked_play_song(user_id, song_id):
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()

            cur.execute(
                """
                SELECT num_plays, num_likes, num_downloads
                FROM songs
                WHERE song_id = %s
                FOR UPDATE
                """,
                (song_id,),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False, "song not found"

            num_plays, num_likes, num_downloads = row
            time.sleep(random.uniform(0.01, 0.05))

            cur.execute(
                """
                INSERT INTO user_history(user_id, song_id, listening_time, listening_count)
                VALUES(%s, %s, NOW(), 1)
                ON DUPLICATE KEY UPDATE listening_count = listening_count + 1, listening_time = NOW()
                """,
                (user_id, song_id),
            )

            new_num_plays = num_plays + 1
            new_popularity = (new_num_plays * 0.6) + (num_likes * 0.3) + (num_downloads * 0.1)
            cur.execute(
                """
                UPDATE songs
                SET num_plays = %s,
                    popularity_score = %s
                WHERE song_id = %s
                """,
                (new_num_plays, new_popularity, song_id),
            )

            conn.commit()
            return True, None
        except Exception as exc:
            conn.rollback()
            return False, str(exc)
        finally:
            cur.close()
    finally:
        conn.close()


def run_threads(worker, song_id, total_threads, user_ids, max_workers):
    failures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = []
        for index in range(total_threads):
            user_id = user_ids[index % len(user_ids)]
            futures.append(executor.submit(worker, user_id, song_id))

        for future in as_completed(futures):
            ok, error = future.result()
            if not ok:
                failures.append(error)

    return failures


def main():
    parser = argparse.ArgumentParser(description="Show race behavior with and without row locks.")
    parser.add_argument("--song-id", type=int, default=DEFAULT_SONG_ID)
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--mode", choices=["unsafe", "locked"], default="unsafe")
    args = parser.parse_args()

    worker = unsafe_play_song if args.mode == "unsafe" else locked_play_song

    before = print_state(args.song_id, "before")
    failures = run_threads(worker, args.song_id, args.threads, DEFAULT_USER_IDS, args.workers)
    after = print_state(args.song_id, f"after {args.mode} run")

    before_song = before["song"] or {}
    after_song = after["song"] or {}
    before_summary = before["summary"] or {}
    after_summary = after["summary"] or {}

    expected_num_plays = int(before_song.get("num_plays") or 0) + args.threads
    expected_total_listens = int(before_summary.get("total_listens") or 0) + args.threads
    actual_num_plays = int(after_song.get("num_plays") or 0)
    actual_total_listens = int(after_summary.get("total_listens") or 0)

    print("\n=== run info ===")
    print({
        "mode": args.mode,
        "song_id": args.song_id,
        "threads": args.threads,
        "workers": args.workers,
        "failures": len(failures),
    })

    print("\n=== expected vs actual ===")
    print({
        "expected_num_plays": expected_num_plays,
        "actual_num_plays": actual_num_plays,
        "num_plays_delta": actual_num_plays - expected_num_plays,
        "expected_total_listens": expected_total_listens,
        "actual_total_listens": actual_total_listens,
        "total_listens_delta": actual_total_listens - expected_total_listens,
    })

    if failures:
        print("sample failures:")
        for message in failures[:10]:
            print(message)


if __name__ == "__main__":
    main()