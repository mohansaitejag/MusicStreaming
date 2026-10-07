from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Path
from backend.models.schemas import (
    AddMoneyRequest,
    ArtistStudioResponse,
    CreatePlaylistRequest,
    DeleteSongRequest,
    HomeResponse,
    PlaylistSongAction,
    PurchaseSubscriptionRequest,
    CancelSubscriptionRequest,
    ReleaseSongRequest,
    SearchResponse,
    SimulatePlayRequest,
    UpdateSongRequest,
    UserArtistAction,
    UserSongAction,
    UserProfile,
)
from backend.db import repositories as repo
from backend.services.music_service import get_home_payload, search_payload

router = APIRouter(prefix="/api", tags=["music"])


@router.get("/profile/{user_id}", response_model=UserProfile)
def profile(user_id: int = Path(..., gt=0)):
    row = repo.get_user_profile(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


@router.get("/home", response_model=HomeResponse)
def home(user_id: int = Query(..., gt=0)):
    try:
        return get_home_payload(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/search", response_model=SearchResponse)
def search(user_id: int = Query(..., gt=0), q: str = Query(..., min_length=1, max_length=100)):
    if not q.strip():
        return {"songs": [], "artists": [], "playlists": []}
    return search_payload(user_id, q.strip())


@router.get("/playlists/{user_id}")
def playlists(user_id: int = Path(..., gt=0)):
    return repo.get_user_playlists(user_id)


@router.get("/playlists/{playlist_id}/songs")
def playlist_songs(playlist_id: int = Path(..., gt=0), user_id: int = Query(..., gt=0)):
    details = repo.get_playlist_detail(playlist_id, user_id)
    if not details:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"playlist": details, "songs": repo.get_playlist_songs(playlist_id, user_id)}


@router.get("/song-sales/{user_id}")
def song_sales(user_id: int):
    return repo.get_user_song_sales(user_id)


@router.get("/likes/{user_id}")
def liked_songs(user_id: int):
    return repo.get_user_liked_songs(user_id)


@router.get("/liked-songs/{user_id}")
def liked_songs_alias(user_id: int):
    """Alias for /likes/{user_id} — used by song page."""
    return repo.get_user_liked_songs(user_id)


@router.get("/followed-artists/{user_id}")
def followed_artists(user_id: int):
    return repo.get_followed_artists(user_id)


@router.get("/genres")
def genres():
    return repo.get_genres()


@router.get("/genres/{genre_id}/songs")
def songs_for_genre(genre_id: int, user_id: Optional[int] = None):
    """When user_id is an artist account, only that artist's songs (including collaborations) in the genre."""
    if user_id is not None:
        profile = repo.get_user_profile(user_id)
        if profile and profile.get("user_role") == "artist":
            artist = repo.get_artist_id_for_user(user_id)
            if artist:
                return repo.get_songs_by_genre_for_artist(int(artist["artist_id"]), genre_id)
    return repo.get_songs_by_genre(genre_id)


@router.get("/recent/{user_id}")
def recent(user_id: int):
    return repo.get_recent_songs(user_id)


@router.get("/recommendations/{user_id}")
def recommendations(user_id: int):
    return repo.get_recommendations(user_id)


@router.get("/artists/{artist_id}")
def artist_details(artist_id: int):
    details = repo.get_artist_detail(artist_id)
    if not details:
        raise HTTPException(status_code=404, detail="Artist not found")
    return {"artist": details, "songs": repo.get_artist_songs(artist_id)}


@router.get("/songs/all")
def all_songs():
    return repo.get_all_songs()


@router.get("/songs/{song_id}")
def song_details(song_id: int):
    details = repo.get_song_detail(song_id)
    if not details:
        raise HTTPException(status_code=404, detail="Song not found")
    return details


@router.get("/artist-studio/{user_id}", response_model=ArtistStudioResponse)
def artist_studio(user_id: int):
    payload = repo.get_artist_studio_dashboard(user_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Artist studio not available for this user")
    return payload


@router.post("/simulate-play")
def simulate_play(payload: SimulatePlayRequest):
    return repo.simulate_play(payload.user_id, payload.song_id)


@router.post("/like")
def like_song(req: dict):
    user_id = req.get("user_id")
    song_id = req.get("song_id")
    repo.like_song(user_id, song_id)
    return {"ok": True, "message": "Liked"}

@router.post("/unlike")
def unlike_song(req: dict):
    user_id = req.get("user_id")
    song_id = req.get("song_id")
    repo.unlike_song(user_id, song_id)
    return {"ok": True, "message": "Unliked"}


@router.post("/song-sale")
def create_song_sale(payload: UserSongAction):
    return repo.create_song_sale(payload.user_id, payload.song_id)


@router.get("/downloads/{user_id}")
def get_downloads(user_id: int):
    return repo.get_user_downloads(user_id)


@router.post("/download")
def download_song(payload: UserSongAction):
    try:
        return repo.download_song(payload.user_id, payload.song_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/add-money")
def add_money(payload: AddMoneyRequest):
    return repo.add_money(payload.user_id, payload.amount)


@router.post("/users/withdraw-money")
def withdraw_money(payload: AddMoneyRequest):
    profile = repo.get_user_profile(payload.user_id)
    if not profile or profile.get("user_role") != "artist":
        raise HTTPException(status_code=403, detail="Withdraw is only available for artist accounts")
    try:
        return repo.withdraw_money(payload.user_id, payload.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/purchase-subscription")
def purchase_subscription(payload: PurchaseSubscriptionRequest):
    try:
        repo.purchase_subscription(payload.user_id, payload.subscription_type, payload.duration_months)
        return {"message": "Subscription purchased successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/cancel-subscription")
def cancel_subscription(payload: CancelSubscriptionRequest):
    try:
        res = repo.cancel_subscription(payload.user_id)
        return res
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/follow-artist")
def follow_artist(payload: UserArtistAction):
    return repo.follow_artist(payload.user_id, payload.artist_id)


@router.post("/unfollow-artist")
def unfollow_artist(payload: UserArtistAction):
    return repo.unfollow_artist(payload.user_id, payload.artist_id)


@router.post("/playlists")
def create_playlist(payload: CreatePlaylistRequest):
    return repo.create_user_playlist(payload.user_id, payload.playlist_name)


@router.post("/playlists/{playlist_id}/songs")
def add_to_playlist(playlist_id: int, payload: PlaylistSongAction):
    return repo.add_song_to_playlist(playlist_id, payload.song_id)


@router.post("/artist-studio/release")
def release_song(payload: ReleaseSongRequest):
    return repo.release_artist_song(
        payload.user_id,
        payload.song_title,
        payload.duration,
        payload.release_date,
        payload.genre_ids,
        payload.collaborator_ids,
    )


@router.get("/artist-studio/song/{song_id}")
def artist_song_for_edit(song_id: int, user_id: int):
    song = repo.get_artist_song_for_edit(user_id, song_id)
    if not song:
        raise HTTPException(status_code=404, detail="Editable artist song not found")
    return song


@router.post("/artist-studio/update")
def update_song(payload: UpdateSongRequest):
    return repo.update_artist_song(
        payload.user_id,
        payload.song_id,
        payload.song_title,
        payload.duration,
        payload.genre_ids,
        payload.collaborator_ids,
    )


@router.delete("/artist-studio/song/{song_id}")
def delete_song(song_id: int, user_id: int):
    result = repo.delete_artist_song(user_id, song_id)
    if not result.get("ok"):
        raise HTTPException(status_code=403, detail=result.get("message", "Delete failed"))
    return result
