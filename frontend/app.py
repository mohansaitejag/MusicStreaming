import os
import requests
from typing import Optional
from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
DEFAULT_USER_ID = int(os.getenv("DEFAULT_USER_ID", "1"))


def _get_logged_in_user_id():
    user_id = session.get("user_id")
    if user_id is not None:
        return int(user_id)
    return None


def _require_user_id():
    user_id = _get_logged_in_user_id()
    if user_id is None:
        return None
    return user_id


def _safe_get(path: str, params: Optional[dict] = None, fallback=None):
    headers = {}
    if "access_token" in session:
        headers["Authorization"] = f"Bearer {session['access_token']}"
    try:
        response = requests.get(f"{API_BASE_URL}{path}", params=params, headers=headers, timeout=4)
        if response.ok:
            return response.json()
    except requests.RequestException:
        pass
    return fallback

def _safe_post(path: str, json_data: Optional[dict] = None, fallback=None):
    headers = {}
    if "access_token" in session:
        headers["Authorization"] = f"Bearer {session['access_token']}"
    try:
        response = requests.post(f"{API_BASE_URL}{path}", json=json_data, headers=headers, timeout=4)
        if response.ok:
            return response.json()
    except requests.RequestException:
        pass
    return fallback


@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/home")
def home():
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    profile.setdefault(
        "user_id", user_id
    )
    profile.setdefault("name", "Guest User")
    profile.setdefault("email_id", "guest@example.com")
    profile.setdefault("subscription_type", "free")
    profile.setdefault("user_role", "user")
    profile.setdefault("wallet_balance", 0)
    
    # If user is an artist, fetch artist studio data
    if profile.get("user_role") == "artist":
        data = _safe_get(f"/api/artist-studio/{user_id}", fallback={}) or {}
        data.setdefault("profile", profile)
        data.setdefault("recent_releases", [])
        data.setdefault("top_releases", [])
        data.setdefault("top_collaborators", [])
    else:
        # Regular user home
        data = _safe_get("/api/home", params={"user_id": user_id}, fallback={}) or {}
        data.setdefault("profile", profile)
        data.setdefault("trending_songs", [])
        data.setdefault("recommendations", [])
        data.setdefault("playlists", [])
        data.setdefault("song_sales", [])
        data.setdefault("liked_songs", [])
        data.setdefault("followed_artists", [])
        data.setdefault("all_artists", [])
        data.setdefault("genres", [])
        data.setdefault("recent_songs", [])
    
    return render_template(
        "index.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        data=data,
        profile=profile,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if _get_logged_in_user_id() is not None:
        return redirect(url_for("home"))

    error = None
    success = None
    if request.args.get("registered") == "success":
        success = "Registration successful! Please log in with your new credentials."

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        
        # Authenticate via FastAPI backend
        auth_response = _safe_post("/api/auth/login", json_data={"email": email, "password": password})
        
        if auth_response and "access_token" in auth_response:
            session["user_id"] = auth_response["user_id"]
            session["access_token"] = auth_response["access_token"]
            return redirect(url_for("home"))
        error = "Invalid email or password"

    return render_template("login.html", error=error, success=success)


@app.route("/register", methods=["GET", "POST"])
def register():
    if _get_logged_in_user_id() is not None:
        return redirect(url_for("home"))

    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()
        nationality = request.form.get("nationality", "").strip() or "Unknown"

        if not name or not email or not password or not role:
            error = "All fields are required"
        else:
            try:
                response = requests.post(
                    f"{API_BASE_URL}/api/auth/register",
                    json={
                        "name": name,
                        "email": email,
                        "password": password,
                        "role": role,
                        "nationality": nationality if role == "artist" else "Unknown"
                    },
                    timeout=4
                )
                if response.status_code == 200:
                    return redirect(url_for("login", registered="success"))
                else:
                    try:
                        detail = response.json().get("detail", "Registration failed")
                    except Exception:
                        detail = "Registration failed"
                    error = detail
            except requests.RequestException:
                error = "Unable to connect to the backend authentication service"

    return render_template("register.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/collection/<string:kind>")
def collection_view(kind: str):
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    normalized = kind.lower()
    if normalized not in {"sales", "likes", "downloads"}:
        normalized = "sales"
    
    if normalized == "sales":
        api_path = "/api/song-sales"
        label = "Bought Songs"
    elif normalized == "downloads":
        api_path = "/api/downloads"
        label = "Downloaded Songs"
    else:
        api_path = "/api/likes"
        label = "Favourites"
    
    songs = _safe_get(f"{api_path}/{user_id}", fallback=[]) or []
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    return render_template(
        "collection.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        collection_title=label,
        songs=songs,
        kind=normalized,
    )


@app.route("/followed-artists")
def followed_artists_view():
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    followed_artists = _safe_get(f"/api/followed-artists/{user_id}", fallback=[]) or []
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    return render_template(
        "followed_artists.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        artists=followed_artists,
    )


@app.route("/all-songs")
def all_songs_view():
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    profile.setdefault("user_role", "user")
    
    if profile.get("user_role") == "artist":
        # Artists only see their own published songs
        studio_data = _safe_get(f"/api/artist-studio/{user_id}", fallback={}) or {}
        songs = studio_data.get("songs", [])
    else:
        songs = _safe_get(f"/api/songs/all", fallback=[]) or []
    
    return render_template(
        "all_songs.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        songs=songs,
    )


@app.route("/playlists")
def playlists_view():
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    playlists = _safe_get(f"/api/playlists/{user_id}", fallback=[]) or []
    
    for p in playlists:
        playlist_data = _safe_get(f"/api/playlists/{p['playlist_id']}/songs", params={"user_id": user_id}, fallback={}) or {}
        p["top_songs"] = playlist_data.get("songs", [])[:4]

    return render_template(
        "playlists.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        playlists=playlists,
    )


@app.route("/playlist/<int:playlist_id>")
def playlist_view(playlist_id: int):
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    payload = _safe_get(
        f"/api/playlists/{playlist_id}/songs",
        params={"user_id": user_id},
        fallback={},
    ) or {}
    playlist = payload.get(
        "playlist",
        {
            "playlist_id": playlist_id,
            "playlist_name": "Playlist",
            "created_date": "-",
            "song_count": 0,
        },
    )
    songs = payload.get("songs", [])
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    return render_template(
        "playlist.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        playlist=playlist,
        songs=songs,
    )


@app.route("/artist/<int:artist_id>")
def artist_view(artist_id: int):
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    payload = _safe_get(f"/api/artists/{artist_id}", fallback={}) or {}
    artist = payload.get(
        "artist",
        {
            "artist_id": artist_id,
            "artist_name": "Artist",
            "nationality": "-",
            "num_followers": 0,
            "monetization_status": "notmonetized",
        },
    )
    songs = payload.get("songs", [])
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    followed_artists = _safe_get(f"/api/followed-artists/{user_id}", fallback=[]) or []
    is_following = any(a.get("artist_id") == artist_id for a in followed_artists)
    return render_template(
        "artist.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        artist=artist,
        songs=songs,
        is_following=is_following,
    )


@app.route("/genres")
def genres_view():
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    
    # Fetch all genres
    genres = _safe_get(f"/api/genres", fallback=[]) or []
    
    # Fetch user profile
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    
    return render_template(
        "genres.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        genres=genres,
    )


@app.route("/genre/<int:genre_id>")
def genre_view(genre_id: int):
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    
    # Fetch all genres to find the name for this genre_id
    all_genres = _safe_get(f"/api/genres", fallback=[]) or []
    genre = next((g for g in all_genres if g.get("genre_id") == genre_id), 
                 {"genre_id": genre_id, "genre_name": "Genre"})
    
    # Fetch user profile first (needed for artist-filtered genre songs)
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    profile.setdefault("user_role", "user")

    # Fetch songs for this genre (artists only see their own and collaboration tracks)
    if profile.get("user_role") == "artist":
        songs = (
            _safe_get(
                f"/api/genres/{genre_id}/songs",
                params={"user_id": user_id},
                fallback=[],
            )
            or []
        )
    else:
        songs = _safe_get(f"/api/genres/{genre_id}/songs", fallback=[]) or []
    
    return render_template(
        "genre.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        genre=genre,
        songs=songs,
    )


@app.route("/artist-studio")
def artist_studio_view():
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    payload = _safe_get(f"/api/artist-studio/{user_id}", fallback=None)
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    edit_song = None
    edit_song_id_raw = request.args.get("edit_song_id")
    if edit_song_id_raw and profile.get("user_role") == "artist":
        try:
            edit_song_id = int(edit_song_id_raw)
        except (TypeError, ValueError):
            edit_song_id = None
        if edit_song_id is not None:
            edit_song = _safe_get(
                f"/api/artist-studio/song/{edit_song_id}",
                params={"user_id": user_id},
                fallback=None,
            )
    if payload is None and profile.get("user_role") == "artist":
        payload = {
            "artist": {
                "artist_id": 0,
                "artist_name": profile.get("name", "Artist"),
                "nationality": "Unknown",
                "num_followers": 0,
                "monetization_status": "notmonetized",
            },
            "songs": [],
            "transactions": [],
            "summary": {"total_earned": 0, "transaction_count": 0},
            "collaborators": [],
            "genres": [],
            "sale_price": 29.0,
        }
    return render_template(
        "artist_studio.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        payload=payload,
        edit_song=edit_song,
    )


@app.route("/profile")
def profile_view():
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    return render_template(
        "profile.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
    )


@app.route("/song/<int:song_id>")
def song_view(song_id: int):
    user_id = _require_user_id()
    if user_id is None:
        return redirect(url_for("login"))
    song = _safe_get(f"/api/songs/{song_id}", fallback={}) or {}
    profile = _safe_get(f"/api/profile/{user_id}", fallback={}) or {}
    liked_songs = _safe_get(f"/api/liked-songs/{user_id}", fallback=[]) or []
    song["is_liked"] = any(str(s.get("song_id")) == str(song_id) for s in liked_songs)
    
    is_publisher = False
    if profile.get("user_role") == "artist":
        artist_studio_data = _safe_get(f"/api/artist-studio/{user_id}", fallback={}) or {}
        artist_id = artist_studio_data.get("artist", {}).get("artist_id")
        if artist_id is not None and artist_id in song.get("artist_ids", []):
            is_publisher = True

    return render_template(
        "song.html",
        api_base_url=API_BASE_URL,
        user_id=user_id,
        profile=profile,
        song=song,
        is_publisher=is_publisher,
    )


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    app.run(host=host, port=port, debug=True)
