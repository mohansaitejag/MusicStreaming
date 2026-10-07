from typing import Any, Dict, List, Optional
from mysql.connector.errors import IntegrityError, DatabaseError
from backend.db.connection import get_connection
import time

SALE_PRICE = 30.00
MAX_RETRIES = 3
RETRY_DELAY = 0.1  # seconds


def _fetch_all_dict(query: str, params: tuple = ()) -> List[Dict[str, Any]]:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params)
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()


def _fetch_one_dict(query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(query, params)
        return cur.fetchone()
    finally:
        cur.close()
        conn.close()


def _execute(query: str, params: tuple = ()) -> int:
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        return cur.rowcount
    finally:
        cur.close()
        conn.close()


def _call_procedure(procedure_name: str, params: tuple = ()):
    """Call a stored procedure."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        # Build the call statement with appropriate number of %s placeholders
        placeholders = ", ".join(["%s"] * len(params))
        call_stmt = f"CALL {procedure_name}({placeholders})" if params else f"CALL {procedure_name}()"
        cur.execute(call_stmt, params)
        conn.commit()
    finally:
        cur.close()
        conn.close()

def get_user_by_email(email: str):
    return _fetch_one_dict(
        """
        SELECT user_id, name, email_id, user_role, password
        FROM users
        WHERE email_id = %s
        """,
        (email,)
    )

def get_user_profile(user_id: int):
    # First, check and update subscription status if expired
    _call_procedure("check_and_update_subscription", (user_id,))
    
    # Then fetch the updated user profile
    return _fetch_one_dict(
        """
        SELECT user_id, name, email_id, user_role, wallet_balance, subscription_type, 
               DATE_FORMAT(subscription_start, '%Y-%m-%d') as subscription_start,
               DATE_FORMAT(subscription_end, '%Y-%m-%d') as subscription_end
        FROM users
        WHERE user_id = %s
        """,
        (user_id,),
    )


def is_premium_and_subscribed(user_id: int) -> bool:
    """Check if user is premium and has an active subscription."""
    user = get_user_profile(user_id)
    if not user:
        return False
    sub_type = user.get("subscription_type")
    if not sub_type or sub_type == "free":
        return False
    
    # If subscription_end is not set, give them a free pass (assume valid subscription)
    if not user['subscription_end']:
        return True
    
    from datetime import datetime
    try:
        subscription_end = datetime.strptime(user['subscription_end'], '%Y-%m-%d')
        return subscription_end >= datetime.now()
    except (ValueError, TypeError):
        # If date parsing fails, assume subscription is valid for premium users
        return True


def download_song(user_id: int, song_id: int):
    """Download a song for a premium user."""
    if not is_premium_and_subscribed(user_id):
        raise ValueError("Only active premium subscribers can download songs")
    
    _execute(
        """
        INSERT IGNORE INTO user_downloads (user_id, song_id, downloaded_at)
        VALUES (%s, %s, NOW())
        """,
        (user_id, song_id),
    )
    return {"ok": True, "message": "Song downloaded successfully"}


def get_user_downloads(user_id: int):
    """Get downloaded songs for a user (only if subscription is active)."""
    # Check if user has active subscription
    if not is_premium_and_subscribed(user_id):
        return []
    
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM user_downloads ud
        JOIN songs s ON s.song_id = ud.song_id
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        WHERE ud.user_id = %s
        GROUP BY s.song_id
        ORDER BY ud.downloaded_at DESC
        """,
        (user_id,),
    )


def purchase_subscription(user_id: int, subscription_type: str, duration_months: int):
    # Check if user already has an active premium plan
    user = get_user_profile(user_id)
    if not user:
        raise ValueError("User not found")
        
    if user.get("subscription_type") and user.get("subscription_type") != "free":
        from datetime import datetime
        if user['subscription_end']:
            try:
                end_date = datetime.strptime(user['subscription_end'], '%Y-%m-%d')
                if end_date > datetime.now():
                    raise ValueError("You already have an active premium plan")
            except (ValueError, TypeError):
                raise ValueError("You already have an active premium plan")
        else:
            raise ValueError("You already have an active premium plan")

    # Calculate cost (assuming premium is $10/month, $100/year)
    if duration_months == 12:
        cost = 100.0
    else:
        cost = 10.0 * duration_months
    
    # Check wallet balance
    if float(user['wallet_balance']) < cost:
        raise ValueError(f"Insufficient wallet balance. You need ${cost}.")
    
    # Calculate new subscription dates
    from datetime import datetime, timedelta
    now = datetime.now()
    start_date = now
    end_date = start_date + timedelta(days=30 * duration_months)
    
    # Update user subscription and deduct wallet
    _execute(
        """
        UPDATE users
        SET subscription_type = %s, subscription_start = %s, subscription_end = %s, wallet_balance = wallet_balance - %s
        WHERE user_id = %s
        """,
        (subscription_type, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'), cost, user_id),
    )

def cancel_subscription(user_id: int):
    user = get_user_profile(user_id)
    if not user:
        raise ValueError("User not found")
    sub_type = user.get("subscription_type")
    if not sub_type or sub_type == "free":
        raise ValueError("User is not on a premium plan")
    
    from datetime import datetime
    refund_amount = 0
    if user.get('subscription_end') and user.get('subscription_start'):
        try:
            start_date = datetime.strptime(user['subscription_start'], '%Y-%m-%d')
            end_date = datetime.strptime(user['subscription_end'], '%Y-%m-%d')
            now = datetime.now()
            if end_date > now:
                days_left = (end_date - now).days
                total_days = (end_date - start_date).days
                if total_days > 300:
                    # $100 per 365 days
                    refund_amount = round(days_left * (100.0 / 365.0), 2)
                else:
                    # $10 per 30 days
                    refund_amount = round(days_left * (10.0 / 30.0), 2)
        except (ValueError, TypeError):
            pass

    _execute(
        """
        UPDATE users
        SET subscription_type = 'free', subscription_end = NULL, wallet_balance = wallet_balance + %s
        WHERE user_id = %s
        """,
        (refund_amount, user_id),
    )
    return {"message": f"Subscription cancelled. ${refund_amount} refunded to your wallet."}


def get_trending_songs(limit: int = 12):
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM songs s
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        GROUP BY s.song_id
        ORDER BY s.popularity_score DESC, s.num_plays DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_recent_songs(user_id: int, limit: int = 10):
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM user_history uh
        JOIN songs s ON s.song_id = uh.song_id
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        WHERE uh.user_id = %s
        GROUP BY s.song_id, uh.listening_time
        ORDER BY uh.listening_time DESC
        LIMIT %s
        """,
        (user_id, limit),
    )


def get_user_playlists(user_id: int):
    return _fetch_all_dict(
        """
        SELECT p.playlist_id, p.playlist_name, DATE_FORMAT(p.created_date, '%%Y-%%m-%%d') AS created_date,
               COUNT(ps.song_id) AS song_count
        FROM playlist p
        LEFT JOIN playlist_songs ps ON ps.playlist_id = p.playlist_id
        WHERE p.user_id = %s
        GROUP BY p.playlist_id
        ORDER BY p.created_date DESC
        """,
        (user_id,),
    )


def get_playlist_detail(playlist_id: int, user_id: int):
    return _fetch_one_dict(
        """
        SELECT p.playlist_id, p.playlist_name, DATE_FORMAT(p.created_date, '%%Y-%%m-%%d') AS created_date,
               COUNT(ps.song_id) AS song_count
        FROM playlist p
        LEFT JOIN playlist_songs ps ON ps.playlist_id = p.playlist_id
        WHERE p.playlist_id = %s AND p.user_id = %s
        GROUP BY p.playlist_id
        """,
        (playlist_id, user_id),
    )


def get_playlist_songs(playlist_id: int, user_id: int):
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM playlist p
        JOIN playlist_songs ps ON ps.playlist_id = p.playlist_id
        JOIN songs s ON s.song_id = ps.song_id
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        WHERE p.playlist_id = %s AND p.user_id = %s
        GROUP BY s.song_id
        ORDER BY s.song_title ASC
        """,
        (playlist_id, user_id),
    )


def get_user_song_sales(user_id: int):
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM song_sales ss
        JOIN songs s ON s.song_id = ss.song_id
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        WHERE ss.user_id = %s
        GROUP BY s.song_id
        ORDER BY MAX(ss.sold_at) DESC, s.song_title ASC
        """,
        (user_id,),
    )


def get_user_liked_songs(user_id: int):
    artist = get_artist_id_for_user(user_id)
    if artist:
        artist_id = int(artist["artist_id"])
        return _fetch_all_dict(
            """
            SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
                   COALESCE(s.popularity_score, 0) AS popularity_score,
                   COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
            FROM user_likes_song ul
            JOIN songs s ON s.song_id = ul.song_id
            LEFT JOIN make_song ms ON ms.song_id = s.song_id
            LEFT JOIN artist a ON a.artist_id = ms.artist_id
            WHERE ul.user_id = %s AND s.song_id IN (SELECT ms3.song_id FROM make_song ms3 WHERE ms3.artist_id = %s)
            GROUP BY s.song_id
            ORDER BY s.song_title ASC
            """,
            (user_id, artist_id),
        )
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM user_likes_song ul
        JOIN songs s ON s.song_id = ul.song_id
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        WHERE ul.user_id = %s
        GROUP BY s.song_id
        ORDER BY s.song_title ASC
        """,
        (user_id,),
    )


def get_followed_artists(user_id: int):
    return _fetch_all_dict(
        """
        SELECT a.artist_id, a.artist_name, a.num_followers
        FROM user_follows_artist ufa
        JOIN artist a ON a.artist_id = ufa.artist_id
        WHERE ufa.user_id = %s
        ORDER BY a.artist_name ASC
        """,
        (user_id,),
    )


def get_all_artists(limit: int = 24):
    return _fetch_all_dict(
        """
        SELECT artist_id, artist_name, num_followers
        FROM artist
        ORDER BY num_followers DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_genres():
    return _fetch_all_dict(
        """
        SELECT genre_id, genre_name
        FROM genre
        ORDER BY genre_name ASC
        """
    )


def get_songs_by_genre(genre_id: int, limit: int = 24):
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM categorize_song cs
        JOIN songs s ON s.song_id = cs.song_id
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        WHERE cs.genre_id = %s
        GROUP BY s.song_id
        ORDER BY s.popularity_score DESC, s.num_plays DESC
        LIMIT %s
        """,
        (genre_id, limit),
    )


def get_songs_by_genre_for_artist(artist_id: int, genre_id: int, limit: int = 24):
    """Songs in a genre where the artist is credited (solo or collaboration)."""
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM categorize_song cs
        JOIN songs s ON s.song_id = cs.song_id
        INNER JOIN make_song ms_self ON ms_self.song_id = s.song_id AND ms_self.artist_id = %s
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        WHERE cs.genre_id = %s
        GROUP BY s.song_id
        ORDER BY s.popularity_score DESC, s.num_plays DESC
        LIMIT %s
        """,
        (artist_id, genre_id, limit),
    )


def search_songs(term: str, limit: int = 20):
    q = f"%{term}%"
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM songs s
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        WHERE s.song_title LIKE %s
        GROUP BY s.song_id
        ORDER BY s.popularity_score DESC
        LIMIT %s
        """,
        (q, limit),
    )


def search_artists(term: str, limit: int = 10):
    q = f"%{term}%"
    return _fetch_all_dict(
        """
        SELECT artist_id, artist_name, num_followers
        FROM artist
        WHERE artist_name LIKE %s
        ORDER BY num_followers DESC
        LIMIT %s
        """,
        (q, limit),
    )


def search_playlists(term: str, user_id: int, limit: int = 10):
    q = f"%{term}%"
    return _fetch_all_dict(
        """
        SELECT p.playlist_id, p.playlist_name, DATE_FORMAT(p.created_date, '%%Y-%%m-%%d') AS created_date,
               COUNT(ps.song_id) AS song_count
        FROM playlist p
        LEFT JOIN playlist_songs ps ON ps.playlist_id = p.playlist_id
        WHERE p.user_id = %s AND p.playlist_name LIKE %s
        GROUP BY p.playlist_id
        ORDER BY p.created_date DESC
        LIMIT %s
        """,
        (user_id, q, limit),
    )


def get_artist_detail(artist_id: int):
    return _fetch_one_dict(
        """
        SELECT artist_id, artist_name, nationality, num_followers, monetization_status
        FROM artist
        WHERE artist_id = %s
        """,
        (artist_id,),
    )


def get_all_songs():
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM songs s
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        GROUP BY s.song_id
        ORDER BY s.popularity_score DESC
        LIMIT 500
        """
    )


def get_song_detail(song_id: int):
    row = _fetch_one_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(GROUP_CONCAT(DISTINCT ms.artist_id), '') AS artist_ids,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists,
               COALESCE(GROUP_CONCAT(DISTINCT g.genre_name ORDER BY g.genre_name SEPARATOR ', '), 'Unknown') AS genres
        FROM songs s
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        LEFT JOIN categorize_song cs ON cs.song_id = s.song_id
        LEFT JOIN genre g ON g.genre_id = cs.genre_id
        WHERE s.song_id = %s
        GROUP BY s.song_id
        """,
        (song_id,),
    )
    if row:
        if row.get("artist_ids"):
            row["artist_ids"] = [int(x) for x in row["artist_ids"].split(",") if x]
            row["artist_id"] = row["artist_ids"][0] if row["artist_ids"] else None
        else:
            row["artist_ids"] = []
            row["artist_id"] = None
    return row


def get_artist_songs(artist_id: int):
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a2.artist_name ORDER BY a2.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM make_song ms
        JOIN songs s ON s.song_id = ms.song_id
        LEFT JOIN make_song ms2 ON ms2.song_id = s.song_id
        LEFT JOIN artist a2 ON a2.artist_id = ms2.artist_id
        WHERE ms.artist_id = %s
        GROUP BY s.song_id
        ORDER BY s.num_plays DESC, s.song_title ASC
        """,
        (artist_id,),
    )


def unlike_song(user_id: int, song_id: int):
    for attempt in range(MAX_RETRIES):
        conn = get_connection()
        try:
            cur = conn.cursor()
            try:
                cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
                conn.start_transaction()

                cur.execute("SELECT song_id FROM songs WHERE song_id = %s FOR UPDATE", (song_id,))
                if not cur.fetchone():
                    conn.rollback()
                    return {"ok": False, "message": "Song not found"}

                cur.execute(
                    """
                    DELETE FROM user_likes_song
                    WHERE user_id = %s AND song_id = %s
                    """,
                    (user_id, song_id),
                )
                if cur.rowcount > 0:
                    cur.execute("UPDATE songs SET num_likes = GREATEST(0, num_likes - 1) WHERE song_id = %s", (song_id,))
                    cur.execute(
                        """
                        UPDATE songs
                        SET popularity_score = (num_plays * 0.6) + (num_likes * 0.3) + (num_downloads * 0.1)
                        WHERE song_id = %s
                        """,
                        (song_id,),
                    )

                conn.commit()
                return {"ok": True, "message": "Song unliked"}
            except DatabaseError as e:
                conn.rollback()
                if "1213" in str(e) and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return {"ok": False, "message": f"Database error: {str(e)}"}
            except Exception as e:
                conn.rollback()
                return {"ok": False, "message": f"Transaction failed: {str(e)}"}
        finally:
            cur.close()
            conn.close()



def create_playlist(user_id: int, playlist_name: str):
    _execute(
        """
        INSERT INTO playlist (user_id, playlist_name, created_date)
        VALUES (%s, %s, NOW())
        """,
        (user_id, playlist_name),
    )
    return {"ok": True, "message": "Playlist created"}


def add_song_to_playlist(user_id: int, song_id: int, playlist_id: int):
    _execute(
        """
        INSERT IGNORE INTO playlist_songs (playlist_id, song_id)
        VALUES (%s, %s)
        """,
        (playlist_id, song_id),
    )
    return {"ok": True, "message": "Added to playlist"}


def follow_artist(user_id: int, artist_id: int):
    _execute(
        """
        INSERT IGNORE INTO user_follows_artist (user_id, artist_id)
        VALUES (%s, %s)
        """,
        (user_id, artist_id),
    )


def unfollow_artist(user_id: int, artist_id: int):
    _execute(
        """
        DELETE FROM user_follows_artist
        WHERE user_id = %s AND artist_id = %s
        """,
        (user_id, artist_id),
    )


def add_money(user_id: int, amount: float):
    _execute(
        """
        UPDATE users
        SET wallet_balance = wallet_balance + %s
        WHERE user_id = %s
        """,
        (amount, user_id),
    )
    row = _fetch_one_dict(
        """
        SELECT wallet_balance
        FROM users
        WHERE user_id = %s
        """,
        (user_id,),
    )
    return {"ok": True, "message": f"Added ${amount} to wallet", "wallet_balance": row["wallet_balance"] if row else 0}


def withdraw_money(user_id: int, amount: float):
    if not (amount and amount > 0):
        raise ValueError("Amount must be greater than 0")

    row = _fetch_one_dict(
        """
        SELECT wallet_balance
        FROM users
        WHERE user_id = %s
        """,
        (user_id,),
    )
    balance = float(row["wallet_balance"]) if row and row.get("wallet_balance") is not None else 0.0
    if balance < float(amount):
        raise ValueError("Insufficient wallet balance")

    _execute(
        """
        UPDATE users
        SET wallet_balance = wallet_balance - %s
        WHERE user_id = %s
        """,
        (amount, user_id),
    )
    updated = _fetch_one_dict(
        """
        SELECT wallet_balance
        FROM users
        WHERE user_id = %s
        """,
        (user_id,),
    )
    return {
        "ok": True,
        "message": f"Withdrew ${amount} from wallet",
        "wallet_balance": updated["wallet_balance"] if updated else 0,
    }


def release_song(user_id: int, song_title: str, duration: int, collaborator_ids: List[int], genre_ids: List[int]):
    # Insert into songs
    _execute(
        """
        INSERT INTO songs (song_title, duration, num_plays, num_likes, num_downloads, popularity_score)
        VALUES (%s, %s, 0, 0, 0, 0)
        """,
        (song_title, duration),
    )
    song_id = _fetch_one_dict("SELECT LAST_INSERT_ID() as id")["id"]
    
    # Insert into make_song for the artist
    artist_id = get_artist_id_for_user(user_id)
    if artist_id:
        _execute(
            """
            INSERT INTO make_song (artist_id, song_id)
            VALUES (%s, %s)
            """,
            (artist_id, song_id),
        )
    
    # For collaborators
    for collab_id in collaborator_ids:
        _execute(
            """
            INSERT INTO make_song (artist_id, song_id)
            VALUES (%s, %s)
            """,
            (collab_id, song_id),
        )
    
    # For genres
    for genre_id in genre_ids:
        _execute(
            """
            INSERT INTO categorize_song (song_id, genre_id)
            VALUES (%s, %s)
            """,
            (song_id, genre_id),
        )
    
    return {"ok": True, "message": "Song released"}


def get_artist_id_for_user(user_id: int):
    row = _fetch_one_dict(
        """
        SELECT
            a.artist_id,
            a.artist_name,
            a.nationality,
            a.num_followers,
            a.monetization_status,
            COUNT(DISTINCT ms.song_id) AS song_count,
            COUNT(DISTINCT atx.transaction_id) AS tx_count
        FROM users u
        JOIN artist a ON LOWER(REPLACE(a.artist_name, ' ', '')) = LOWER(REPLACE(u.name, ' ', ''))
        LEFT JOIN make_song ms ON ms.artist_id = a.artist_id
        LEFT JOIN artist_transactions atx ON atx.artist_id = a.artist_id
        WHERE u.user_id = %s AND u.user_role = 'artist'
        GROUP BY a.artist_id
        ORDER BY tx_count DESC, song_count DESC, a.artist_id ASC
        LIMIT 1
        """,
        (user_id,),
    )
    if row:
        return row

    user_row = _fetch_one_dict(
        """
        SELECT user_id, name
        FROM users
        WHERE user_id = %s AND user_role = 'artist'
        LIMIT 1
        """,
        (user_id,),
    )
    if not user_row:
        return None

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO artist(artist_name, nationality, num_followers, monetization_status)
            VALUES(%s, %s, 0, 'notmonetized')
            """,
            (user_row["name"], "Unknown"),
        )
        artist_id = cur.lastrowid
        conn.commit()
    finally:
        cur.close()
        conn.close()

    return _fetch_one_dict(
        """
        SELECT artist_id, artist_name, nationality, num_followers, monetization_status
        FROM artist
        WHERE artist_id = %s
        """,
        (artist_id,),
    )


def get_artist_studio_dashboard(user_id: int):
    artist = get_artist_id_for_user(user_id)
    if not artist:
        return None

    artist_id = int(artist["artist_id"])
    songs = _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
                         COALESCE(CAST(DATE(s.release_date) AS CHAR), 'Unknown') AS release_date,
               COALESCE(GROUP_CONCAT(DISTINCT a2.artist_name ORDER BY a2.artist_name SEPARATOR ', '), 'Unknown') AS artists,
             COUNT(DISTINCT ss.sale_id) AS num_sales
        FROM make_song ms
        JOIN songs s ON s.song_id = ms.song_id
        LEFT JOIN make_song ms2 ON ms2.song_id = s.song_id
        LEFT JOIN artist a2 ON a2.artist_id = ms2.artist_id
        LEFT JOIN song_sales ss ON ss.song_id = s.song_id
        WHERE ms.artist_id = %s
        GROUP BY s.song_id
        ORDER BY s.release_date DESC, s.song_id DESC
        """,
        (artist_id,),
    )

    transactions = _fetch_all_dict(
        """
        SELECT atx.transaction_id,
               atx.song_id,
               s.song_title,
               atx.amount,
               atx.transaction_type,
               atx.notes,
             DATE_FORMAT(atx.created_at, '%%Y-%%m-%%d %%T') AS created_at
        FROM artist_transactions atx
        LEFT JOIN songs s ON s.song_id = atx.song_id
        WHERE atx.artist_id = %s
        ORDER BY atx.created_at DESC, atx.transaction_id DESC
        LIMIT 150
        """,
        (artist_id,),
    )

    summary = _fetch_one_dict(
        """
        SELECT
            COALESCE(SUM(ss.sale_amount / song_counts.artist_count), 0) AS total_earned,
            COUNT(DISTINCT ss.sale_id) AS transaction_count
        FROM song_sales ss
        JOIN make_song ms ON ms.song_id = ss.song_id
        JOIN (
            SELECT song_id, COUNT(*) AS artist_count
            FROM make_song
            GROUP BY song_id
        ) song_counts ON song_counts.song_id = ss.song_id
        WHERE ms.artist_id = %s
        """,
        (artist_id,),
    ) or {"total_earned": 0, "transaction_count": 0}

    # Get recent releases (past 1 year)
    recent_releases = _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays,
               DATE_FORMAT(s.release_date, '%%Y-%%m-%%d') AS release_date,
               COALESCE(GROUP_CONCAT(DISTINCT a2.artist_name ORDER BY a2.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM make_song ms
        JOIN songs s ON s.song_id = ms.song_id
        LEFT JOIN make_song ms2 ON ms2.song_id = s.song_id
        LEFT JOIN artist a2 ON a2.artist_id = ms2.artist_id
        WHERE ms.artist_id = %s AND s.release_date >= DATE_SUB(NOW(), INTERVAL 1 YEAR)
        GROUP BY s.song_id
        ORDER BY s.release_date DESC
        LIMIT 5
        """,
        (artist_id,),
    )

    # Get top releases by plays/views
    top_releases = _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays,
               DATE_FORMAT(s.release_date, '%%Y-%%m-%%d') AS release_date,
               COALESCE(GROUP_CONCAT(DISTINCT a2.artist_name ORDER BY a2.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM make_song ms
        JOIN songs s ON s.song_id = ms.song_id
        LEFT JOIN make_song ms2 ON ms2.song_id = s.song_id
        LEFT JOIN artist a2 ON a2.artist_id = ms2.artist_id
        WHERE ms.artist_id = %s
        GROUP BY s.song_id
        ORDER BY s.num_plays DESC, s.song_id DESC
        LIMIT 5
        """,
        (artist_id,),
    )

    # Get top collaborators (artists who have collaborated with this artist)
    top_collaborators = _fetch_all_dict(
        """
        SELECT a.artist_id, a.artist_name, COUNT(DISTINCT s.song_id) AS collaboration_count
        FROM make_song ms1
        JOIN songs s ON s.song_id = ms1.song_id
        JOIN make_song ms2 ON ms2.song_id = s.song_id
        JOIN artist a ON a.artist_id = ms2.artist_id
        WHERE ms1.artist_id = %s AND ms2.artist_id <> %s
        GROUP BY a.artist_id, a.artist_name
        ORDER BY collaboration_count DESC, a.artist_name ASC
        LIMIT 5
        """,
        (artist_id, artist_id),
    )

    collaborators = _fetch_all_dict(
        """
        SELECT artist_id, artist_name
        FROM artist
        WHERE artist_id <> %s
        ORDER BY artist_name ASC
        """,
        (artist_id,),
    )
    genres = get_genres()

    return {
        "artist": artist,
        "songs": songs,
        "transactions": transactions,
        "summary": summary,
        "collaborators": collaborators,
        "recent_releases": recent_releases,
        "top_releases": top_releases,
        "top_collaborators": top_collaborators,
        "genres": genres,
        "sale_price": SALE_PRICE,
    }


def release_artist_song(
    user_id: int,
    song_title: str,
    duration: int,
    release_date: Optional[str],
    genre_ids: List[int],
    collaborator_ids: List[int],
):
    artist = get_artist_id_for_user(user_id)
    if not artist:
        return {"ok": False, "message": "Artist profile not found for this user"}

    clean_title = song_title.strip()
    if not clean_title:
        return {"ok": False, "message": "Song title is required"}
    if duration <= 0:
        return {"ok": False, "message": "Duration must be greater than 0"}

    primary_artist_id = int(artist["artist_id"])
    artist_ids = {primary_artist_id}
    artist_ids.update(aid for aid in collaborator_ids if int(aid) != primary_artist_id)

    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()

            cur.execute(
                """
                INSERT INTO songs(song_title, duration, release_date, num_plays, num_likes, num_downloads, popularity_score)
                VALUES(%s, %s, NOW(), 0, 0, 0, 0)
                """,
                (clean_title, duration),
            )
            song_id = cur.lastrowid

            for artist_id in sorted(artist_ids):
                cur.execute(
                    "INSERT INTO make_song(song_id, artist_id) VALUES(%s, %s)",
                    (song_id, artist_id),
                )

            for genre_id in sorted(set(genre_ids)):
                cur.execute(
                    "INSERT INTO categorize_song(song_id, genre_id) VALUES(%s, %s)",
                    (song_id, genre_id),
                )

            conn.commit()
            return {"ok": True, "message": "Song released", "song_id": song_id}
        except Exception as e:
            conn.rollback()
            return {"ok": False, "message": f"Transaction failed: {str(e)}"}
    finally:
        cur.close()
        conn.close()


def get_artist_song_for_edit(user_id: int, song_id: int):
    artist = get_artist_id_for_user(user_id)
    if not artist:
        return None
    artist_id = int(artist["artist_id"])

    allowed = _fetch_one_dict(
        """
        SELECT 1 AS ok
        FROM make_song
        WHERE song_id = %s AND artist_id = %s
        LIMIT 1
        """,
        (song_id, artist_id),
    )
    if not allowed:
        return None

    song = _fetch_one_dict(
        """
        SELECT song_id, song_title, duration
        FROM songs
        WHERE song_id = %s
        """,
        (song_id,),
    )
    if not song:
        return None

    collaborator_rows = _fetch_all_dict(
        """
        SELECT artist_id
        FROM make_song
        WHERE song_id = %s AND artist_id <> %s
        ORDER BY artist_id ASC
        """,
        (song_id, artist_id),
    )
    genre_rows = _fetch_all_dict(
        """
        SELECT genre_id
        FROM categorize_song
        WHERE song_id = %s
        ORDER BY genre_id ASC
        """,
        (song_id,),
    )

    return {
        "song_id": int(song["song_id"]),
        "song_title": song["song_title"],
        "duration": int(song["duration"]),
        "collaborator_ids": [int(row["artist_id"]) for row in collaborator_rows],
        "genre_ids": [int(row["genre_id"]) for row in genre_rows],
    }


def update_artist_song(
    user_id: int,
    song_id: int,
    song_title: str,
    duration: int,
    genre_ids: List[int],
    collaborator_ids: List[int],
):
    artist = get_artist_id_for_user(user_id)
    if not artist:
        return {"ok": False, "message": "Artist profile not found for this user"}

    clean_title = song_title.strip()
    if not clean_title:
        return {"ok": False, "message": "Song title is required"}
    if duration <= 0:
        return {"ok": False, "message": "Duration must be greater than 0"}
    if not genre_ids:
        return {"ok": False, "message": "At least one genre is required"}

    primary_artist_id = int(artist["artist_id"])
    can_edit = _fetch_one_dict(
        """
        SELECT 1 AS ok
        FROM make_song
        WHERE song_id = %s AND artist_id = %s
        LIMIT 1
        """,
        (song_id, primary_artist_id),
    )
    if not can_edit:
        return {"ok": False, "message": "You can only update your own songs"}

    artist_ids = {primary_artist_id}
    artist_ids.update(int(aid) for aid in collaborator_ids if int(aid) != primary_artist_id)

    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()

            cur.execute(
                """
                UPDATE songs
                SET song_title = %s, duration = %s
                WHERE song_id = %s
                """,
                (clean_title, duration, song_id),
            )

            cur.execute("DELETE FROM make_song WHERE song_id = %s", (song_id,))
            for artist_id in sorted(artist_ids):
                cur.execute(
                    "INSERT INTO make_song(song_id, artist_id) VALUES(%s, %s)",
                    (song_id, artist_id),
                )

            cur.execute("DELETE FROM categorize_song WHERE song_id = %s", (song_id,))
            for genre_id in sorted(set(int(gid) for gid in genre_ids)):
                cur.execute(
                    "INSERT INTO categorize_song(song_id, genre_id) VALUES(%s, %s)",
                    (song_id, genre_id),
                )

            conn.commit()
            return {"ok": True, "message": "Song updated", "song_id": song_id}
        except Exception as e:
            conn.rollback()
            return {"ok": False, "message": f"Update failed: {str(e)}"}
    finally:
        cur.close()
        conn.close()


def simulate_play(user_id: int, song_id: int):
    for attempt in range(MAX_RETRIES):
        conn = get_connection()
        try:
            cur = conn.cursor()
            try:
                cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
                conn.start_transaction()

                cur.execute("SELECT song_id FROM songs WHERE song_id = %s FOR UPDATE", (song_id,))
                if not cur.fetchone():
                    conn.rollback()
                    return {"ok": False, "message": "Song not found"}

                cur.execute(
                    """
                    INSERT INTO user_history(user_id, song_id, listening_time, listening_count)
                    VALUES(%s, %s, NOW(), 1)
                    ON DUPLICATE KEY UPDATE listening_count = listening_count + 1, listening_time = NOW()
                    """,
                    (user_id, song_id),
                )
                # NOTE: num_plays is updated by DB triggers after_history_insert / after_history_update
                cur.execute(
                    """
                    UPDATE songs
                    SET popularity_score = (num_plays * 0.6) + (num_likes * 0.3) + (num_downloads * 0.1)
                    WHERE song_id = %s
                    """,
                    (song_id,),
                )

                conn.commit()
                return {"ok": True}
            except DatabaseError as e:
                conn.rollback()
                if "1213" in str(e) and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return {"ok": False, "message": f"Database error: {str(e)}"}
            except Exception as e:
                conn.rollback()
                return {"ok": False, "message": f"Transaction failed: {str(e)}"}
        finally:
            cur.close()
            conn.close()


def like_song(user_id: int, song_id: int):
    for attempt in range(MAX_RETRIES):
        conn = get_connection()
        try:
            cur = conn.cursor()
            try:
                cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
                conn.start_transaction()

                cur.execute("SELECT song_id FROM songs WHERE song_id = %s FOR UPDATE", (song_id,))
                if not cur.fetchone():
                    conn.rollback()
                    return {"ok": False, "message": "Song not found"}

                cur.execute(
                    "INSERT INTO user_likes_song(user_id, song_id) VALUES(%s, %s)",
                    (user_id, song_id),
                )
                cur.execute("UPDATE songs SET num_likes = num_likes + 1 WHERE song_id = %s", (song_id,))
                cur.execute(
                    """
                    UPDATE songs
                    SET popularity_score = (num_plays * 0.6) + (num_likes * 0.3) + (num_downloads * 0.1)
                    WHERE song_id = %s
                    """,
                    (song_id,),
                )

                conn.commit()
                return {"ok": True, "message": "Song liked"}
            except IntegrityError:
                conn.rollback()
                return {"ok": False, "message": "Song already liked"}
            except DatabaseError as e:
                conn.rollback()
                if "1213" in str(e) and attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return {"ok": False, "message": f"Database error: {str(e)}"}
            except Exception as e:
                conn.rollback()
                return {"ok": False, "message": f"Transaction failed: {str(e)}"}
        finally:
            cur.close()
            conn.close()


def create_song_sale(user_id: int, song_id: int):
    profile = get_user_profile(user_id)
    if not profile:
        return {"ok": False, "message": "User not found"}
    balance = float(profile.get("wallet_balance") or 0)
    if balance < SALE_PRICE:
        return {"ok": False, "message": f"Insufficient wallet balance. Add money and try again. Need ${SALE_PRICE:.2f}."}

    # RETRY LOOP for WW (Write-Write) conflicts / deadlocks
    for attempt in range(MAX_RETRIES):
        conn = get_connection()
        try:
            cur = conn.cursor()
            try:
                # SET ISOLATION LEVEL to READ COMMITTED (prevents dirty reads)
                # WR conflict handling: READ COMMITTED prevents reading uncommitted data
                cur.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED")
                
                # START TRANSACTION
                conn.start_transaction()
                
                # RW CONFLICT HANDLING: Lock user wallet FOR UPDATE
                # Prevents Read-Write conflicts (ensures exclusive access)
                cur.execute(
                    "SELECT wallet_balance FROM users WHERE user_id = %s FOR UPDATE",
                    (user_id,),
                )
                user_wallet = cur.fetchone()
                if not user_wallet:
                    conn.rollback()
                    return {"ok": False, "message": "User not found"}
                
                # Re-check balance after lock acquired (prevents lost update)
                current_balance = float(user_wallet[0])
                if current_balance < SALE_PRICE:
                    conn.rollback()
                    return {"ok": False, "message": f"Insufficient wallet balance. Need ${SALE_PRICE:.2f}."}
                
                # Get artist IDs before locking
                cur.execute("SELECT artist_id FROM make_song WHERE song_id = %s", (song_id,))
                rows = cur.fetchall()
                artist_ids = [int(row[0]) for row in rows]
                
                # WW CONFLICT HANDLING: Lock artist rows FOR UPDATE
                # Prevents concurrent writes for same artist set during credit logging
                if artist_ids:
                    placeholders = ",".join(["%s"] * len(artist_ids))
                    cur.execute(
                        f"SELECT artist_id FROM artist WHERE artist_id IN ({placeholders}) FOR UPDATE",
                        tuple(artist_ids),
                    )
                    cur.fetchall()
                
                # INSERT song sale record (unique constraint prevents duplicate purchases)
                cur.execute(
                    "INSERT INTO song_sales(user_id, song_id, sale_amount, sold_at) VALUES(%s, %s, %s, NOW())",
                    (user_id, song_id, SALE_PRICE),
                )
                sale_id = cur.lastrowid
                
                # UPDATE user wallet (debit) - WR protected by lock
                cur.execute(
                    "UPDATE users SET wallet_balance = wallet_balance - %s WHERE user_id = %s",
                    (SALE_PRICE, user_id),
                )
                rows_affected = cur.rowcount
                if rows_affected == 0:
                    conn.rollback()
                    return {"ok": False, "message": "Failed to update user wallet (user may have been deleted)"}
                
                # Credit artists - WW protected by locks
                if artist_ids:
                    split = round(SALE_PRICE / len(artist_ids), 2)
                    credits = [split for _ in artist_ids]
                    credits[0] = round(SALE_PRICE - sum(credits[1:]), 2)
                    
                    for index, artist_id in enumerate(artist_ids):
                        # LOG transaction (audit trail for RW/WR/WW conflicts)
                        cur.execute(
                            """
                            INSERT INTO artist_transactions(artist_id, song_id, sale_id, transaction_type, amount, notes, created_at)
                            VALUES(%s, %s, %s, 'sale_credit', %s, %s, NOW())
                            """,
                            (
                                artist_id,
                                song_id,
                                sale_id,
                                credits[index],
                                f"Split from song sale #{sale_id}",
                            ),
                        )
                
                # COMMIT transaction
                conn.commit()
                return {"ok": True, "message": "Purchased. Artist earnings updated.", "sale_id": sale_id}
                
            except IntegrityError as e:
                conn.rollback()
                if "uq_song_sales_user_song" in str(e):
                    return {"ok": False, "message": "Song already purchased"}
                else:
                    return {"ok": False, "message": f"Data conflict: {str(e)}"}
            except DatabaseError as e:
                conn.rollback()
                # WW Deadlock detected - retry
                if "1213" in str(e):  # MySQL deadlock error code
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        return {"ok": False, "message": f"Transaction deadlock after {MAX_RETRIES} retries. Please try again."}
                else:
                    return {"ok": False, "message": f"Database error: {str(e)}"}
            except Exception as e:
                conn.rollback()
                return {"ok": False, "message": f"Transaction failed: {str(e)}"}
        finally:
            cur.close()
            conn.close()
    
    return {"ok": False, "message": "Transaction failed after maximum retries"}


def add_test_money(user_id: int, amount: float = 50.0):
    changed = _execute(
        "UPDATE users SET wallet_balance = wallet_balance + %s WHERE user_id = %s",
        (amount, user_id),
    )
    if changed <= 0:
        return {"ok": False, "message": "User not found"}
    profile = get_user_profile(user_id) or {}
    return {
        "ok": True,
        "message": f"Added ${amount:.2f} to wallet",
        "wallet_balance": float(profile.get("wallet_balance") or 0),
    }


def follow_artist(user_id: int, artist_id: int):
    try:
        changed = _execute(
            "INSERT INTO user_follows_artist(user_id, artist_id) VALUES(%s, %s)",
            (user_id, artist_id),
        )
        return {"ok": changed > 0, "message": "Artist followed"}
    except IntegrityError:
        return {"ok": False, "message": "Artist already followed"}


def unfollow_artist(user_id: int, artist_id: int):
    changed = _execute(
        "DELETE FROM user_follows_artist WHERE user_id = %s AND artist_id = %s",
        (user_id, artist_id),
    )
    if changed > 0:
        return {"ok": True, "message": "Artist unfollowed"}
    return {"ok": False, "message": "Artist was not followed"}


def add_song_to_playlist(playlist_id: int, song_id: int):
    try:
        changed = _execute(
            "INSERT INTO playlist_songs(playlist_id, song_id) VALUES(%s, %s)",
            (playlist_id, song_id),
        )
        return {"ok": changed > 0, "message": "Added to playlist"}
    except IntegrityError:
        return {"ok": False, "message": "Song already in playlist"}


def create_user_playlist(user_id: int, playlist_name: str):
    clean_name = playlist_name.strip()
    if not clean_name:
        return {"ok": False, "message": "Playlist name is required"}

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO playlist(playlist_name, created_date, user_id) VALUES(%s, CURDATE(), %s)",
            (clean_name, user_id),
        )
        conn.commit()
        return {"ok": True, "message": "Playlist created", "playlist_id": cur.lastrowid}
    finally:
        cur.close()
        conn.close()


def get_recommendations(user_id: int, limit: int = 12):
    return _fetch_all_dict(
        """
        SELECT s.song_id, s.song_title, s.duration, s.num_plays, s.num_likes, s.num_downloads,
               COALESCE(s.popularity_score, 0) AS popularity_score,
               COALESCE(GROUP_CONCAT(DISTINCT a.artist_name ORDER BY a.artist_name SEPARATOR ', '), 'Unknown') AS artists
        FROM songs s
        JOIN categorize_song cs2 ON cs2.song_id = s.song_id
        JOIN (
            SELECT cs.genre_id
            FROM user_history uh
            JOIN categorize_song cs ON cs.song_id = uh.song_id
            WHERE uh.user_id = %s
            GROUP BY cs.genre_id
            ORDER BY SUM(uh.listening_count) DESC
            LIMIT 3
        ) AS tg ON tg.genre_id = cs2.genre_id
        LEFT JOIN make_song ms ON ms.song_id = s.song_id
        LEFT JOIN artist a ON a.artist_id = ms.artist_id
        GROUP BY s.song_id
        ORDER BY s.popularity_score DESC
        LIMIT %s
        """,
        (user_id, limit),
    )


def delete_artist_song(user_id: int, song_id: int):
    """Delete a song if the artist owns it. Removes from all related tables."""
    artist = get_artist_id_for_user(user_id)
    if not artist:
        return {"ok": False, "message": "Artist profile not found for this user"}
    artist_id = int(artist["artist_id"])

    can_delete = _fetch_one_dict(
        """
        SELECT 1 AS ok
        FROM make_song
        WHERE song_id = %s AND artist_id = %s
        LIMIT 1
        """,
        (song_id, artist_id),
    )
    if not can_delete:
        return {"ok": False, "message": "You can only delete your own songs"}

    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            conn.start_transaction()
            cur.execute("DELETE FROM user_likes_song WHERE song_id = %s", (song_id,))
            cur.execute("DELETE FROM user_history WHERE song_id = %s", (song_id,))
            cur.execute("DELETE FROM user_downloads WHERE song_id = %s", (song_id,))
            cur.execute("DELETE FROM playlist_songs WHERE song_id = %s", (song_id,))
            cur.execute("DELETE FROM artist_transactions WHERE song_id = %s", (song_id,))
            cur.execute("DELETE FROM song_sales WHERE song_id = %s", (song_id,))
            cur.execute("DELETE FROM categorize_song WHERE song_id = %s", (song_id,))
            cur.execute("DELETE FROM make_song WHERE song_id = %s", (song_id,))
            cur.execute("DELETE FROM songs WHERE song_id = %s", (song_id,))
            conn.commit()
            return {"ok": True, "message": "Song deleted successfully"}
        except Exception as e:
            conn.rollback()
            return {"ok": False, "message": f"Delete failed: {str(e)}"}
    finally:
        cur.close()
        conn.close()


def create_user(name: str, email: str, password_hash: str, role: str, nationality: Optional[str] = "Unknown"):
    """Create a new user. If the role is artist, also create an entry in the artist table."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        
        # 1. Check if email already exists (case-insensitive check)
        cur.execute("SELECT user_id FROM users WHERE LOWER(email_id) = LOWER(%s)", (email,))
        if cur.fetchone():
            return {"success": False, "error": "Email already exists"}
            
        # 2. Insert into users table
        cur.execute(
            """
            INSERT INTO users (email_id, name, password, sign_up_date, user_role, wallet_balance)
            VALUES (%s, %s, %s, CURDATE(), %s, 0.00)
            """,
            (email, name, password_hash, role)
        )
        user_id = cur.lastrowid
        
        # 3. If role is 'artist', insert into artist table
        if role == 'artist':
            cur.execute(
                """
                INSERT INTO artist (artist_name, nationality, num_followers, monetization_status)
                VALUES (%s, %s, 0, 'monetized')
                """,
                (name, nationality or "Unknown")
            )
            
        conn.commit()
        return {"success": True, "user_id": user_id}
    except IntegrityError as e:
        conn.rollback()
        return {"success": False, "error": "Integrity error: Email might already be registered."}
    except DatabaseError as e:
        conn.rollback()
        return {"success": False, "error": f"Database error: {str(e)}"}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": f"An unexpected error occurred: {str(e)}"}
    finally:
        cur.close()
        conn.close()

