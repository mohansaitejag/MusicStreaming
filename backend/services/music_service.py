from backend.db import repositories as repo


def get_home_payload(user_id: int):
    profile = repo.get_user_profile(user_id)
    if not profile:
        raise ValueError("User not found")
    return {
        "profile": profile,
        "trending_songs": repo.get_trending_songs(),
        "recommendations": repo.get_recommendations(user_id),
        "playlists": repo.get_user_playlists(user_id),
        "song_sales": repo.get_user_song_sales(user_id),
        "liked_songs": repo.get_user_liked_songs(user_id),
        "followed_artists": repo.get_followed_artists(user_id),
        "all_artists": repo.get_all_artists(12),
        "genres": repo.get_genres(),
        "recent_songs": repo.get_recent_songs(user_id),
    }


def search_payload(user_id: int, term: str):
    return {
        "songs": repo.search_songs(term),
        "artists": repo.search_artists(term),
        "playlists": repo.search_playlists(term, user_id),
    }
