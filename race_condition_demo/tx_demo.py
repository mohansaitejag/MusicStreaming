import argparse
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from mysql.connector.errors import DatabaseError, IntegrityError, PoolError


ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


from backend.db.connection import get_connection


DEFAULT_WORKERS = 10
DEFAULT_THREADS = 20
DEFAULT_USER_ID = 1
DEFAULT_SONG_ID = 31
DEFAULT_MONEY_AMOUNT = 1.0
DEFAULT_BUY_AMOUNT = 29.0
MAX_TX_RETRIES = 5
RETRY_DELAY_SECONDS = 0.15
LOCK_WAIT_TIMEOUT_SECONDS = 50


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


def print_rows(title, rows):
    print(f"\n=== {title} ===")
    for row in rows:
        print(row)


def parse_ids(value):
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def is_retryable_lock_error(error_text):
    # 1205: Lock wait timeout exceeded, 1213: Deadlock found
    return ("1205" in error_text) or ("1213" in error_text)


def run_threads(worker, items, max_workers):
    failures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(worker, *item) for item in items]
        for future in as_completed(futures):
            ok, error = future.result()
            if not ok:
                failures.append(error)
    return failures


def money_state(user_id):
    return fetch_one("SELECT * FROM users WHERE user_id = %s", (user_id,))


def buy_state(user_ids, song_ids):
    users = fetch_all(
        f"SELECT * FROM users WHERE user_id IN ({','.join(['%s'] * len(user_ids))}) ORDER BY user_id",
        tuple(user_ids),
    ) if user_ids else []
    songs = fetch_all(
        f"SELECT * FROM songs WHERE song_id IN ({','.join(['%s'] * len(song_ids))}) ORDER BY song_id",
        tuple(song_ids),
    ) if song_ids else []
    sales = fetch_all(
        f"SELECT * FROM song_sales WHERE song_id IN ({','.join(['%s'] * len(song_ids))}) ORDER BY sale_id",
        tuple(song_ids),
    ) if song_ids else []
    transactions = fetch_all(
        f"SELECT * FROM artist_transactions WHERE song_id IN ({','.join(['%s'] * len(song_ids))}) ORDER BY transaction_id",
        tuple(song_ids),
    ) if song_ids else []
    return users, songs, sales, transactions


def ensure_demo_earnings_table():
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS artist_demo_earnings (
                    artist_id INT PRIMARY KEY,
                    earned_amount DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (artist_id) REFERENCES artist(artist_id)
                ) ENGINE=InnoDB
                """
            )
            conn.commit()
        finally:
            cur.close()
    finally:
        conn.close()


def reset_demo_earnings_for_song(song_id):
    ensure_demo_earnings_table()
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()
            cur.execute("SELECT artist_id FROM make_song WHERE song_id = %s", (song_id,))
            artist_ids = [int(row[0]) for row in cur.fetchall()]
            for artist_id in artist_ids:
                cur.execute(
                    """
                    INSERT INTO artist_demo_earnings(artist_id, earned_amount)
                    VALUES(%s, 0.00)
                    ON DUPLICATE KEY UPDATE earned_amount = 0.00
                    """,
                    (artist_id,),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()


def fetch_demo_earnings_for_song(song_id):
    ensure_demo_earnings_table()
    return fetch_all(
        """
        SELECT ade.artist_id, a.artist_name, ade.earned_amount, ade.updated_at
        FROM artist_demo_earnings ade
        JOIN artist a ON a.artist_id = ade.artist_id
        JOIN make_song ms ON ms.artist_id = ade.artist_id
        WHERE ms.song_id = %s
        ORDER BY ade.artist_id
        """,
        (song_id,),
    )


def unsafe_add_money(user_id, amount):
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()
            cur.execute("SELECT wallet_balance FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False, "user not found"

            balance = float(row[0])
            time.sleep(random.uniform(0.01, 0.05))
            cur.execute(
                "UPDATE users SET wallet_balance = %s WHERE user_id = %s",
                (balance + amount, user_id),
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


def locked_add_money(user_id, amount):
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()
            cur.execute("SELECT wallet_balance FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return False, "user not found"

            balance = float(row[0])
            time.sleep(random.uniform(0.01, 0.05))
            cur.execute(
                "UPDATE users SET wallet_balance = %s WHERE user_id = %s",
                (balance + amount, user_id),
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


def unsafe_buy_song(user_id, song_id, price, track_demo_earnings=False):
    for attempt in range(MAX_TX_RETRIES):
        conn = get_connection_with_retry()
        try:
            cur = conn.cursor()
            try:
                cur.execute(f"SET SESSION innodb_lock_wait_timeout = {LOCK_WAIT_TIMEOUT_SECONDS}")
                conn.start_transaction()

                cur.execute("SELECT wallet_balance FROM users WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return False, "user not found"

                balance = float(row[0])
                if balance < price:
                    conn.rollback()
                    return False, "insufficient balance"

                cur.execute("SELECT artist_id FROM make_song WHERE song_id = %s", (song_id,))
                artist_ids = [int(row[0]) for row in cur.fetchall()]

                time.sleep(random.uniform(0.01, 0.05))

                cur.execute(
                    "INSERT INTO song_sales(user_id, song_id, sale_amount, sold_at) VALUES(%s, %s, %s, NOW())",
                    (user_id, song_id, price),
                )
                sale_id = cur.lastrowid

                cur.execute(
                    "UPDATE users SET wallet_balance = %s WHERE user_id = %s",
                    (balance - price, user_id),
                )

                if artist_ids:
                    split = round(price / len(artist_ids), 2)
                    credits = [split for _ in artist_ids]
                    credits[0] = round(price - sum(credits[1:]), 2)
                    for index, artist_id in enumerate(artist_ids):
                        cur.execute(
                            """
                            INSERT INTO artist_transactions(artist_id, song_id, sale_id, transaction_type, amount, notes)
                            VALUES(%s, %s, %s, 'sale_credit', %s, %s)
                            """,
                            (artist_id, song_id, sale_id, credits[index], f"Split from song sale #{sale_id}"),
                        )

                        if track_demo_earnings:
                            # Intentionally unsafe read-modify-write to demonstrate lost updates.
                            cur.execute(
                                "SELECT earned_amount FROM artist_demo_earnings WHERE artist_id = %s",
                                (artist_id,),
                            )
                            earned_row = cur.fetchone()
                            current_earned = float(earned_row[0]) if earned_row else 0.0
                            time.sleep(random.uniform(0.01, 0.05))
                            cur.execute(
                                "UPDATE artist_demo_earnings SET earned_amount = %s WHERE artist_id = %s",
                                (current_earned + credits[index], artist_id),
                            )

                conn.commit()
                return True, None
            except IntegrityError:
                conn.rollback()
                return False, "duplicate purchase"
            except DatabaseError as exc:
                conn.rollback()
                error_text = str(exc)
                if is_retryable_lock_error(error_text) and attempt < MAX_TX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                return False, error_text
            except Exception as exc:
                conn.rollback()
                return False, str(exc)
            finally:
                cur.close()
        finally:
            conn.close()

    return False, f"retry limit reached after {MAX_TX_RETRIES} attempts"


def locked_buy_song(user_id, song_id, price, track_demo_earnings=False):
    for attempt in range(MAX_TX_RETRIES):
        conn = get_connection_with_retry()
        try:
            cur = conn.cursor()
            try:
                cur.execute(f"SET SESSION innodb_lock_wait_timeout = {LOCK_WAIT_TIMEOUT_SECONDS}")
                conn.start_transaction()

                cur.execute("SELECT wallet_balance FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return False, "user not found"

                balance = float(row[0])
                if balance < price:
                    conn.rollback()
                    return False, "insufficient balance"

                cur.execute("SELECT artist_id FROM make_song WHERE song_id = %s", (song_id,))
                artist_ids = [int(row[0]) for row in cur.fetchall()]
                if artist_ids:
                    placeholders = ",".join(["%s"] * len(artist_ids))
                    cur.execute(
                        f"SELECT artist_id FROM artist WHERE artist_id IN ({placeholders}) FOR UPDATE",
                        tuple(artist_ids),
                    )
                    cur.fetchall()

                time.sleep(random.uniform(0.01, 0.05))

                cur.execute(
                    "INSERT INTO song_sales(user_id, song_id, sale_amount, sold_at) VALUES(%s, %s, %s, NOW())",
                    (user_id, song_id, price),
                )
                sale_id = cur.lastrowid

                cur.execute(
                    "UPDATE users SET wallet_balance = %s WHERE user_id = %s",
                    (balance - price, user_id),
                )

                if artist_ids:
                    split = round(price / len(artist_ids), 2)
                    credits = [split for _ in artist_ids]
                    credits[0] = round(price - sum(credits[1:]), 2)
                    for index, artist_id in enumerate(artist_ids):
                        cur.execute(
                            """
                            INSERT INTO artist_transactions(artist_id, song_id, sale_id, transaction_type, amount, notes)
                            VALUES(%s, %s, %s, 'sale_credit', %s, %s)
                            """,
                            (artist_id, song_id, sale_id, credits[index], f"Split from song sale #{sale_id}"),
                        )

                        if track_demo_earnings:
                            cur.execute(
                                "SELECT earned_amount FROM artist_demo_earnings WHERE artist_id = %s FOR UPDATE",
                                (artist_id,),
                            )
                            earned_row = cur.fetchone()
                            current_earned = float(earned_row[0]) if earned_row else 0.0
                            time.sleep(random.uniform(0.01, 0.05))
                            cur.execute(
                                "UPDATE artist_demo_earnings SET earned_amount = %s WHERE artist_id = %s",
                                (current_earned + credits[index], artist_id),
                            )

                conn.commit()
                return True, None
            except IntegrityError:
                conn.rollback()
                return False, "duplicate purchase"
            except DatabaseError as exc:
                conn.rollback()
                error_text = str(exc)
                if is_retryable_lock_error(error_text) and attempt < MAX_TX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                return False, error_text
            except Exception as exc:
                conn.rollback()
                return False, str(exc)
            finally:
                cur.close()
        finally:
            conn.close()

    return False, f"retry limit reached after {MAX_TX_RETRIES} attempts"


def prepare_sales_cleanup(user_id, song_ids):
    if not song_ids:
        return
    placeholders = ",".join(["%s"] * len(song_ids))
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()
            cur.execute(
                f"SELECT sale_id FROM song_sales WHERE user_id = %s AND song_id IN ({placeholders})",
                (user_id, *song_ids),
            )
            sale_ids = [int(row[0]) for row in cur.fetchall()]
            if sale_ids:
                sale_placeholders = ",".join(["%s"] * len(sale_ids))
                cur.execute(
                    f"DELETE FROM artist_transactions WHERE sale_id IN ({sale_placeholders})",
                    tuple(sale_ids),
                )
                cur.execute(
                    f"DELETE FROM song_sales WHERE sale_id IN ({sale_placeholders})",
                    tuple(sale_ids),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()


def prepare_multi_user_sales_cleanup(user_ids, song_id):
    if not user_ids:
        return
    user_placeholders = ",".join(["%s"] * len(user_ids))
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()
            cur.execute(
                f"SELECT sale_id FROM song_sales WHERE song_id = %s AND user_id IN ({user_placeholders})",
                (song_id, *user_ids),
            )
            sale_ids = [int(row[0]) for row in cur.fetchall()]
            if sale_ids:
                sale_placeholders = ",".join(["%s"] * len(sale_ids))
                cur.execute(
                    f"DELETE FROM artist_transactions WHERE sale_id IN ({sale_placeholders})",
                    tuple(sale_ids),
                )
                cur.execute(
                    f"DELETE FROM song_sales WHERE sale_id IN ({sale_placeholders})",
                    tuple(sale_ids),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()


def run_money_demo(args):
    worker = unsafe_add_money if args.mode == "unsafe" else locked_add_money
    before = money_state(args.user_id)
    failures = run_threads(worker, [(args.user_id, args.amount)] * args.threads, args.workers)
    after = money_state(args.user_id)

    before_balance = float(before.get("wallet_balance") or 0) if before else 0.0
    after_balance = float(after.get("wallet_balance") or 0) if after else 0.0
    expected = before_balance + (args.threads * args.amount)

    print_rows("before users", [before] if before else [])
    print_rows("after users", [after] if after else [])
    print("\n=== expected vs actual ===")
    print({
        "expected_wallet_balance": expected,
        "actual_wallet_balance": after_balance,
        "delta": after_balance - expected,
        "failures": len(failures),
    })
    if failures:
        print("sample failures:")
        for item in failures[:10]:
            print(item)


def run_buy_demo(args):
    if args.scenario == "same-user":
        song_ids = args.song_ids or [6, 7, 8, 9, 10]
        user_id = args.user_id
        threads = len(song_ids)
        price = args.price
        prepare_sales_cleanup(user_id, song_ids)
        prefund_balance = max(args.prefund, price * threads + 50)
        conn = get_connection_with_retry()
        try:
            cur = conn.cursor()
            try:
                conn.start_transaction()
                cur.execute("UPDATE users SET wallet_balance = %s WHERE user_id = %s", (prefund_balance, user_id))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                cur.close()
        finally:
            conn.close()

        worker = unsafe_buy_song if args.mode == "unsafe" else locked_buy_song
        before_users, before_songs, before_sales, before_tx = buy_state([user_id], song_ids)
        items = [(user_id, song_id, price, False) for song_id in song_ids]
        failures = run_threads(worker, items, args.workers)
        after_users, after_songs, after_sales, after_tx = buy_state([user_id], song_ids)

        before_balance = float(before_users[0].get("wallet_balance") or 0) if before_users else 0.0
        after_balance = float(after_users[0].get("wallet_balance") or 0) if after_users else 0.0
        expected_balance = before_balance - (threads * price)

        print_rows("before users", before_users)
        print_rows("before songs", before_songs)
        print_rows("before song_sales", before_sales)
        print_rows("before artist_transactions", before_tx)
        print_rows("after users", after_users)
        print_rows("after songs", after_songs)
        print_rows("after song_sales", after_sales)
        print_rows("after artist_transactions", after_tx)
        print("\n=== expected vs actual ===")
        print({
            "scenario": "same-user",
            "expected_wallet_balance": expected_balance,
            "actual_wallet_balance": after_balance,
            "delta": after_balance - expected_balance,
            "expected_sales_rows": len(before_sales) + threads,
            "actual_sales_rows": len(after_sales),
            "expected_transaction_rows": len(before_tx) + threads,
            "actual_transaction_rows": len(after_tx),
            "failures": len(failures),
        })
        if failures:
            print("sample failures:")
            for item in failures[:10]:
                print(item)
        return

    user_ids = args.user_ids or [1, 2, 3, 4, 5, 6]
    song_id = args.song_id
    threads = min(args.threads, len(user_ids))
    worker = unsafe_buy_song if args.mode == "unsafe" else locked_buy_song

    prepare_multi_user_sales_cleanup(user_ids, song_id)
    reset_demo_earnings_for_song(song_id)
    prefund_balance = max(args.prefund, args.price + 50)
    user_placeholders = ",".join(["%s"] * len(user_ids))
    conn = get_connection_with_retry()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()
            cur.execute(
                f"UPDATE users SET wallet_balance = %s WHERE user_id IN ({user_placeholders})",
                (prefund_balance, *user_ids),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()

    before_users, before_songs, before_sales, before_tx = buy_state(user_ids, [song_id])
    before_demo_earnings = fetch_demo_earnings_for_song(song_id)
    items = [(user_id, song_id, args.price, True) for user_id in user_ids[:threads]]
    failures = run_threads(worker, items, args.workers)
    after_users, after_songs, after_sales, after_tx = buy_state(user_ids, [song_id])
    after_demo_earnings = fetch_demo_earnings_for_song(song_id)

    print_rows("before users", before_users)
    print_rows("before songs", before_songs)
    print_rows("before song_sales", before_sales)
    print_rows("before artist_transactions", before_tx)
    print_rows("after users", after_users)
    print_rows("after songs", after_songs)
    print_rows("after song_sales", after_sales)
    print_rows("after artist_transactions", after_tx)
    print_rows("before demo artist earnings", before_demo_earnings)
    print_rows("after demo artist earnings", after_demo_earnings)

    successful_sales = len(after_sales) - len(before_sales)
    expected_demo_total = successful_sales * args.price
    actual_demo_total = round(sum(float(row.get("earned_amount") or 0) for row in after_demo_earnings), 2)

    print("\n=== expected vs actual ===")
    print({
        "scenario": "multi-user",
        "expected_sales_rows": len(before_sales) + threads,
        "actual_sales_rows": len(after_sales),
        "expected_transaction_rows": len(before_tx) + threads,
        "actual_transaction_rows": len(after_tx),
        "expected_demo_artist_earnings_total": expected_demo_total,
        "actual_demo_artist_earnings_total": actual_demo_total,
        "demo_earnings_delta": round(actual_demo_total - expected_demo_total, 2),
        "failures": len(failures),
    })
    if failures:
        print("sample failures:")
        for item in failures[:10]:
            print(item)


def main():
    parser = argparse.ArgumentParser(description="Show transaction behavior under concurrency.")
    parser.add_argument("--demo", choices=["money", "buy"], required=True)
    parser.add_argument("--mode", choices=["unsafe", "locked"], default="unsafe")
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)

    parser.add_argument("--user-id", type=int, default=DEFAULT_USER_ID)
    parser.add_argument("--amount", type=float, default=DEFAULT_MONEY_AMOUNT)

    parser.add_argument("--song-id", type=int, default=DEFAULT_SONG_ID)
    parser.add_argument("--song-ids", type=parse_ids, default=None)
    parser.add_argument("--user-ids", type=parse_ids, default=None)
    parser.add_argument("--scenario", choices=["same-user", "multi-user"], default="same-user")
    parser.add_argument("--price", type=float, default=DEFAULT_BUY_AMOUNT)
    parser.add_argument("--prefund", type=float, default=500.0)
    args = parser.parse_args()

    if args.demo == "money":
        run_money_demo(args)
    else:
        run_buy_demo(args)


if __name__ == "__main__":
    main()