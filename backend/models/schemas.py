from typing import List, Optional
from pydantic import BaseModel, Field


class SongCard(BaseModel):
    song_id: int
    song_title: str
    duration: int
    num_plays: int
    num_likes: int
    num_downloads: int
    popularity_score: float
    artists: str


class ArtistReleaseCard(BaseModel):
    song_id: int
    song_title: str
    duration: int
    num_plays: int
    release_date: Optional[str] = None
    artists: str


class PlaylistCard(BaseModel):
    playlist_id: int
    playlist_name: str
    created_date: str
    song_count: int


class ArtistCard(BaseModel):
    artist_id: int
    artist_name: str
    num_followers: int


class ArtistLiteCard(BaseModel):
    artist_id: int
    artist_name: str


class CollaboratorCard(BaseModel):
    artist_id: int
    artist_name: str
    collaboration_count: int = 0


class GenreCard(BaseModel):
    genre_id: int
    genre_name: str


class ArtistStudioSong(BaseModel):
    song_id: int
    song_title: str
    duration: int
    release_date: Optional[str] = None
    artists: str
    num_plays: int = 0
    num_likes: int = 0
    num_downloads: int = 0
    num_sales: int = 0


class ArtistTransactionCard(BaseModel):
    transaction_id: int
    song_id: Optional[int] = None
    song_title: Optional[str] = None
    amount: float
    transaction_type: str
    notes: Optional[str] = None
    created_at: str


class ArtistStudioSummary(BaseModel):
    total_earned: float
    transaction_count: int


class ArtistStudioArtist(BaseModel):
    artist_id: int
    artist_name: str
    nationality: Optional[str] = None
    num_followers: int
    monetization_status: str


class ArtistStudioResponse(BaseModel):
    artist: ArtistStudioArtist
    songs: List[ArtistStudioSong]
    transactions: List[ArtistTransactionCard]
    summary: ArtistStudioSummary
    collaborators: List[ArtistLiteCard]
    recent_releases: List[ArtistReleaseCard]
    top_releases: List[ArtistReleaseCard]
    top_collaborators: List[CollaboratorCard]
    genres: List[GenreCard]
    sale_price: float


class UserProfile(BaseModel):
    user_id: int
    name: str
    email_id: str
    user_role: str
    wallet_balance: float = 0
    subscription_type: Optional[str] = None
    subscription_start: Optional[str] = None
    subscription_end: Optional[str] = None


class PurchaseSubscriptionRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    subscription_type: str = Field(..., description="Type of subscription to purchase: 'premium'")
    duration_months: int = Field(..., description="Duration in months: 1, 3, 6, or 12", ge=1, le=12)


class CancelSubscriptionRequest(BaseModel):
    user_id: int = Field(..., gt=0)


class HomeResponse(BaseModel):
    profile: UserProfile
    trending_songs: List[SongCard]
    recommendations: List[SongCard]
    playlists: List[PlaylistCard]
    song_sales: List[SongCard]
    liked_songs: List[SongCard]
    followed_artists: List[ArtistCard]
    all_artists: List[ArtistCard] = []
    genres: List[GenreCard]
    recent_songs: List[SongCard]


class SearchResponse(BaseModel):
    songs: List[SongCard]
    artists: List[ArtistCard]
    playlists: List[PlaylistCard]


class SimulatePlayRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    song_id: int = Field(..., gt=0)


class UserSongAction(BaseModel):
    user_id: int = Field(..., gt=0)
    song_id: int = Field(..., gt=0)


class UserArtistAction(BaseModel):
    user_id: int = Field(..., gt=0)
    artist_id: int = Field(..., gt=0)


class CreatePlaylistRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    playlist_name: str = Field(..., min_length=1, max_length=100)


class PlaylistSongAction(BaseModel):
    song_id: int = Field(..., gt=0)
    user_id: Optional[int] = Field(None, gt=0)


class AddMoneyRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    amount: float = Field(default=50.0, gt=0, le=10000.0)


class ReleaseSongRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    song_title: str = Field(..., min_length=1, max_length=255)
    duration: int = Field(..., gt=0)
    release_date: Optional[str] = None
    genre_ids: List[int]
    collaborator_ids: List[int]


class UpdateSongRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    song_id: int = Field(..., gt=0)
    song_title: str = Field(..., min_length=1, max_length=255)
    duration: int = Field(..., gt=0)
    genre_ids: List[int]
    collaborator_ids: List[int]


class DeleteSongRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    song_id: int = Field(..., gt=0)
