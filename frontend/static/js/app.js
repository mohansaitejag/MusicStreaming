function resolveConfig() {
  if (window.APP_CONFIG) return window.APP_CONFIG;
  const node = document.getElementById("app-config");
  if (!node) return null;
  try {
    return JSON.parse(node.textContent || "{}");
  } catch (error) {
    return null;
  }
}

const config = resolveConfig();
if (!config) {
  throw new Error("APP_CONFIG missing");
}
let activeSong = null;
let elapsedSeconds = 0;
let timer = null;
let paused = false;
let searchDebounce = null;
let playlistCache = null;
const playbackHistory = [];
const forwardHistory = [];
let artistMappings = { artist_id_to_filename: {}, artist_name_to_filename: {} };

const npTitle = document.getElementById("np-title");
const npArtist = document.getElementById("np-artist");
const elapsedEl = document.getElementById("elapsed");
const durationEl = document.getElementById("duration");
const progressEl = document.getElementById("progress");
const toggleBtn = document.getElementById("toggle-play");
const prevBtn = document.getElementById("prev-track");
const nextBtn = document.getElementById("next-track");
const createPlaylistInput = document.getElementById("create-playlist-name");
const createPlaylistBtn = document.getElementById("create-playlist-btn");
const searchInput = document.getElementById("search-input");
const searchBtn = document.getElementById("search-btn");
const searchDropdown = document.getElementById("search-dropdown");
const statsPopover = document.getElementById("song-stats-popover");
const statsContent = document.getElementById("stats-content");
const closeStats = document.getElementById("close-stats");
const sectionTitle = document.getElementById("song-section-title");
const trendingGrid = document.getElementById("trending-grid");
const initialTrendingMarkup = trendingGrid ? trendingGrid.innerHTML : "";
const releaseSongForm = document.getElementById("release-song-form");
const addMoneyBtn = document.getElementById("add-money-btn");
const fallbackSongArtworkAssets = [
  "/static/art/song-1.svg",
  "/static/art/song-2.svg",
  "/static/art/song-3.svg",
  "/static/art/song-4.svg",
];
const fallbackArtistArtworkAssets = [
  "/static/art/artist-1.svg",
  "/static/art/artist-2.svg",
  "/static/art/artist-3.svg",
  "/static/art/artist-4.svg",
];
let mediaManifest = {
  songCovers: [...fallbackSongArtworkAssets],
  artistPhotos: [...fallbackArtistArtworkAssets],
  testAudios: [],
};
let mediaAudio = null;
let activeAudioPath = "";

function hashValue(value) {
  const text = String(value || "default");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function pickArtwork(assets, key) {
  if (!assets.length) return "";
  return assets[hashValue(key) % assets.length];
}

function normalizeMediaList(value) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => String(item || "").trim())
    .filter((item) => item.length > 0);
}

async function loadMediaManifest() {
  try {
    const response = await fetch("/static/media/manifest.json", { cache: "no-store" });
    if (!response.ok) {
      console.warn("Failed to load media manifest: HTTP", response.status);
      return;
    }
    const manifest = await response.json();
    console.log("[loadMediaManifest] Loaded manifest:", manifest);
    const songCovers = normalizeMediaList(manifest.songCovers);
    const artistPhotos = normalizeMediaList(manifest.artistPhotos);
    const testAudios = normalizeMediaList(manifest.testAudios);

    mediaManifest = {
      songCovers: songCovers.length ? songCovers : [...fallbackSongArtworkAssets],
      artistPhotos: artistPhotos.length ? artistPhotos : [...fallbackArtistArtworkAssets],
      testAudios,
    };
    console.log("[loadMediaManifest] Final manifest:", mediaManifest);
  } catch (error) {
    console.warn("Failed to load media manifest:", error);
  }
}

async function loadArtistMappings() {
  try {
    const response = await fetch("/static/media/artist_mappings.json", { cache: "no-store" });
    if (!response.ok) {
      console.warn("Failed to load artist mappings: HTTP", response.status);
      return;
    }
    artistMappings = await response.json();
    console.log("[loadArtistMappings] Loaded mappings:", artistMappings);
  } catch (error) {
    console.warn("Failed to load artist mappings:", error);
  }
}

function getSongArtwork(song) {
  if (!song || !song.song_title) return "https://picsum.photos/seed/randomsong/400/400";
  return `https://picsum.photos/seed/${encodeURIComponent(song.song_title)}/400/400`;
}

function getArtistArtwork(artistId, artistName) {
  // 1. Try to find by artistId in the mappings
  if (artistId && artistMappings && artistMappings.artist_id_to_filename) {
    const filename = artistMappings.artist_id_to_filename[String(artistId)];
    if (filename) {
      return `/static/media/artist-photos/${filename}`;
    }
  }

  // 2. Try to find by artistName (case-insensitive) in mappings as fallback
  if (artistName && artistMappings && artistMappings.artist_name_to_filename) {
    const cleanName = artistName.toLowerCase().trim();
    const filename = artistMappings.artist_name_to_filename[cleanName];
    if (filename) {
      return `/static/media/artist-photos/${filename}`;
    }
  }

  // 3. Fallback to random picsum
  if (!artistName) return "https://picsum.photos/seed/randomartist/400/400";
  return `https://picsum.photos/seed/${encodeURIComponent(artistName)}/400/400`;
}

function extractArtistIdFromNode(node) {
  if (!node) return null;

  const fromDataset = Number(node.dataset.artistId);
  if (Number.isFinite(fromDataset) && fromDataset > 0) {
    return fromDataset;
  }

  const hrefNode = node.matches("a") ? node : node.querySelector("a[href*='/artist/']");
  const href = hrefNode ? hrefNode.getAttribute("href") || "" : "";
  const match = href.match(/\/artist\/(\d+)/);
  if (match) {
    const id = Number(match[1]);
    if (Number.isFinite(id) && id > 0) {
      return id;
    }
  }

  return null;
}

function setCoverImage(coverEl, url) {
  if (!coverEl || !url) return;
  coverEl.style.backgroundImage = `url("${url}")`;
  coverEl.style.backgroundSize = "cover";
  coverEl.style.backgroundPosition = "center";
  coverEl.classList.add("has-art");
}

function refreshSongArtwork(root = document) {
  const songElements = root.querySelectorAll("[data-song]");
  console.log(`[refreshSongArtwork] Found ${songElements.length} elements with [data-song]`);
  songElements.forEach((card, index) => {
    const song = parseSongFromElement(card);
    if (!song) {
      console.warn(`[refreshSongArtwork] Failed to parse song at index ${index}`);
      return;
    }
    const cover = card.matches(".tile-cover, .row-cover, .recent-cover, .song-cover-large")
      ? card
      : card.querySelector(".tile-cover, .row-cover, .recent-cover, .song-cover-large");
    if (!cover) {
      console.warn(`[refreshSongArtwork] No cover element found for song ${song.song_id} "${song.song_title}"`);
      return;
    }
    const artworkUrl = getSongArtwork(song);
    console.log(`[refreshSongArtwork] Setting cover for song ${song.song_id} to ${artworkUrl}`);
    setCoverImage(cover, artworkUrl);
  });
}

function refreshArtistArtwork(root = document) {
  root.querySelectorAll(".tile-card").forEach((card) => {
    if (card.dataset.song) return;
    const artistId = extractArtistIdFromNode(card);
    const titleEl = card.querySelector(".tile-title") || card.querySelector(".font-semibold") || card.querySelector(".text-primary");
    const name = card.dataset.artistName || card.getAttribute("data-artist-name") || titleEl?.textContent?.trim() || "";
    const cover = card.querySelector(".tile-cover") || card.querySelector(".artist-portrait") || (card.matches(".artist-portrait") ? card : null);
    if (!cover) return;
    setCoverImage(cover, getArtistArtwork(artistId, name));
  });

  root.querySelectorAll("[data-artist-name]").forEach((card) => {
    const artistId = extractArtistIdFromNode(card);
    const name = card.dataset.artistName || card.getAttribute("data-artist-name") || "";
    const cover = card.matches(".artist-portrait") ? card : card.querySelector(".artist-portrait");
    if (!cover || !name) return;
    setCoverImage(cover, getArtistArtwork(artistId, name));
  });
}

function syncPlayerArtwork(song) {
  const cover = document.querySelector(".tiny-cover");
  if (!cover || !song) return;
  setCoverImage(cover, getSongArtwork(song));
}

function getDefaultAudioPath() {
  if (!mediaManifest.testAudios.length) return "";
  return mediaManifest.testAudios[0];
}

function stopTestAudio() {
  if (mediaAudio) {
    mediaAudio.pause();
    mediaAudio.currentTime = 0;
  }
}

function ensureMediaAudio(path) {
  if (!path) return null;
  if (!mediaAudio || activeAudioPath !== path) {
    if (mediaAudio) {
      mediaAudio.pause();
    }
    mediaAudio = new Audio(path);
    mediaAudio.loop = true;
    mediaAudio.preload = "auto";
    activeAudioPath = path;
  }
  return mediaAudio;
}

async function startTestAudio(song) {
  const audioPath = getDefaultAudioPath();
  const audio = ensureMediaAudio(audioPath);
  if (!audio) {
    syncPlayerArtwork(song);
    return;
  }

  audio.currentTime = 0;
  try {
    await audio.play();
  } catch (error) {
    console.warn("Audio playback blocked:", error);
  }
  syncPlayerArtwork(song);
}

async function suspendTestAudio() {
  if (mediaAudio) {
    mediaAudio.pause();
  }
}

async function resumeTestAudio() {
  if (mediaAudio) {
    try {
      await mediaAudio.play();
    } catch (error) {
      console.warn("Audio playback resume failed:", error);
    }
  }
}

function savePlayerState() {
  if (!activeSong) return;
  const state = {
    song: activeSong,
    elapsed: elapsedSeconds,
    paused: paused,
    timestamp: Date.now()
  };
  try {
    localStorage.setItem("musicPlayerState", JSON.stringify(state));
  } catch (error) {
    console.error("Failed to save player state:", error);
  }
}

function restorePlayerState() {
  try {
    const stored = localStorage.getItem("musicPlayerState");
    if (!stored) return;
    const state = JSON.parse(stored);
    // Only restore if it was saved recently (within last 30 minutes)
    if (Date.now() - state.timestamp > 30 * 60 * 1000) {
      localStorage.removeItem("musicPlayerState");
      return;
    }
    activeSong = state.song;
    elapsedSeconds = state.elapsed;
    paused = state.paused;
    if (npTitle) {
      npTitle.textContent = state.song.song_title;
      npTitle.href = "/song/" + state.song.song_id;
    }
    if (npArtist) npArtist.textContent = state.song.artists || "Unknown Artist";
    const playIcon = document.getElementById("play-icon");
    if (playIcon) playIcon.className = paused ? "ri-play-fill text-2xl ml-0.5" : "ri-pause-fill text-2xl";
    
    const likeIcon = document.getElementById("np-like-icon");
    if (likeIcon) {
      if (state.song.is_liked) {
        likeIcon.classList.remove("ri-heart-line");
        likeIcon.classList.add("ri-heart-fill", "text-accent");
      } else {
        likeIcon.classList.add("ri-heart-line");
        likeIcon.classList.remove("ri-heart-fill", "text-accent");
      }
    }
    if (!paused) {
      startPlaybackTimer(state.song, true);
      startTestAudio(state.song).catch((error) => console.error("Failed to restore audio:", error));
    } else {
      updatePlayerUI();
    }
  } catch (error) {
    console.error("Failed to restore player state:", error);
    localStorage.removeItem("musicPlayerState");
  }
}

function updatePlayerUI() {
  if (!activeSong) return;
  if (elapsedEl && durationEl && progressEl) {
    const duration = Math.max(activeSong.duration || 1, 1);
    const pct = Math.min(Math.round((elapsedSeconds / duration) * 100), 100);
    elapsedEl.textContent = toClock(elapsedSeconds);
    durationEl.textContent = toClock(duration);
    progressEl.value = pct;
  }
}

function toClock(seconds) {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const m = Math.floor(safe / 60);
  const s = safe % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function encodeSong(song) {
  return encodeURIComponent(JSON.stringify(song));
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function parseSongFromElement(element) {
  if (!element || !element.dataset.song) return null;
  try {
    if (element.dataset.song.startsWith("%7B")) {
      return JSON.parse(decodeURIComponent(element.dataset.song));
    }
    return JSON.parse(element.dataset.song);
  } catch (error) {
    return null;
  }
}

function songsMatch(left, right) {
  if (!left || !right) return false;
  return Number(left.song_id) === Number(right.song_id);
}

function getVisibleSongs() {
  const songs = [];
  const seen = new Set();
  document.querySelectorAll("[data-song]").forEach((el) => {
    const song = parseSongFromElement(el);
    if (!song || !Number.isFinite(Number(song.song_id))) return;
    if (seen.has(song.song_id)) return;
    seen.add(song.song_id);
    songs.push(song);
  });
  return songs;
}

async function postJson(path, payload) {
  const response = await fetch(`${config.apiBaseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

async function deleteSong(songId, songTitle, redirectTo) {
  if (!confirm(`Delete "${songTitle}"? This action cannot be undone.`)) return;
  try {
    const response = await fetch(`${config.apiBaseUrl}/api/artist-studio/song/${songId}?user_id=${config.userId}`, {
      method: "DELETE",
    });
    const result = await response.json();
    if (response.ok && result.ok !== false) {
      alert(result.message || "Song deleted successfully");
      if (redirectTo && redirectTo !== window.location.pathname) {
        window.location.href = redirectTo;
      } else {
        window.location.reload();
      }
    } else {
      alert(result.detail || result.message || "Failed to delete song");
    }
  } catch (error) {
    alert("Failed to delete song");
    console.error(error);
  }
}

function showSongStats(song, anchorElement) {
  if (!statsPopover || !statsContent || !song) return;
  statsContent.innerHTML = `
    <h4 class="stats-title">${song.song_title}</h4>
    <div class="meta">${song.artists || "Unknown Artist"}</div>
    <div class="stats-grid">
      <div class="stats-pill">Duration: ${toClock(song.duration || 0)}</div>
      <div class="stats-pill">Plays: ${song.num_plays || 0}</div>
      <div class="stats-pill">Likes: ${song.num_likes || 0}</div>
      <div class="stats-pill">Sales: ${song.num_downloads || 0}</div>
    </div>
  `;
  const rect = anchorElement.getBoundingClientRect();
  const left = Math.min(rect.right + 10, window.innerWidth - 320);
  const top = Math.min(rect.top, window.innerHeight - 210);
  statsPopover.style.left = `${Math.max(8, left)}px`;
  statsPopover.style.top = `${Math.max(8, top)}px`;
  statsPopover.classList.remove("hidden");
}

function hideSongStats() {
  if (statsPopover) statsPopover.classList.add("hidden");
}

function startPlaybackTimer(song, resumeFromElapsed = false) {
  if (!elapsedEl || !progressEl || !durationEl) return;
  if (!resumeFromElapsed) {
    elapsedSeconds = 0;
  }
  progressEl.value = 0;
  durationEl.textContent = toClock(song.duration || 0);
  if (!resumeFromElapsed) {
    elapsedEl.textContent = "0:00";
  } else {
    const duration = Math.max(song.duration || 1, 1);
    const pct = Math.min(Math.round((elapsedSeconds / duration) * 100), 100);
    elapsedEl.textContent = toClock(elapsedSeconds);
    progressEl.value = pct;
  }
  if (timer) clearInterval(timer);
  timer = setInterval(() => {
    if (paused || !activeSong) return;
    elapsedSeconds += 1;
    const duration = Math.max(activeSong.duration || 1, 1);
    const pct = Math.min(Math.round((elapsedSeconds / duration) * 100), 100);
    elapsedEl.textContent = toClock(elapsedSeconds);
    progressEl.value = pct;
    const progressFill = document.getElementById("progress-fill");
    if (progressFill) progressFill.style.width = pct + "%";
    // Save player state every 5 seconds
    if (elapsedSeconds % 5 === 0) {
      savePlayerState();
    }
    if (elapsedSeconds >= duration) {
      clearInterval(timer);
      timer = null;
    }
  }, 1000);
}

async function refreshRecent() {
  const host = document.getElementById("recent-list");
  if (!host) return;
  const res = await fetch(`${config.apiBaseUrl}/api/recent/${config.userId}`);
  const recent = await res.json();
  if (!recent.length) {
    host.innerHTML = `<div class="empty">No recent activity</div>`;
    return;
  }
  host.innerHTML = recent
    .map(
      (s) => `
      <div class="list-item song-clickable" data-song="${encodeSong(s)}">
        <div class="name">${s.song_title}</div>
        <div class="meta">${s.artists}</div>
      </div>`
    )
    .join("");
  refreshSongArtwork(host);
}

async function playSong(song, options = {}) {
  const { recordHistory = true, clearForward = true } = options;
  if (activeSong && recordHistory && !songsMatch(activeSong, song)) {
    playbackHistory.push(activeSong);
  }
  if (clearForward) {
    forwardHistory.length = 0;
  }
  activeSong = song;
  paused = false;
  if (npTitle) {
    npTitle.textContent = song.song_title;
    npTitle.href = "/song/" + song.song_id;
  }
  if (npArtist) npArtist.textContent = song.artists || "Unknown Artist";
  const playIcon = document.getElementById("play-icon");
  if (playIcon) playIcon.className = "ri-pause-fill text-2xl";

  const likeIcon = document.getElementById("np-like-icon");
  if (likeIcon) {
    if (song.is_liked) {
      likeIcon.classList.remove("ri-heart-line");
      likeIcon.classList.add("ri-heart-fill", "text-accent");
    } else {
      likeIcon.classList.add("ri-heart-line");
      likeIcon.classList.remove("ri-heart-fill", "text-accent");
    }
  }
  startPlaybackTimer(song);
  startTestAudio(song).catch((error) => console.error("Failed to start test audio:", error));
  savePlayerState();
  await postJson("/api/simulate-play", { user_id: config.userId, song_id: song.song_id });
  await refreshRecent();
}

async function getPreviousFromListeningHistory() {
  const res = await fetch(`${config.apiBaseUrl}/api/recent/${config.userId}`);
  const recent = await res.json();
  if (!Array.isArray(recent) || !recent.length) return null;
  return recent.find((song) => !songsMatch(song, activeSong)) || null;
}

async function playPreviousSong() {
  if (!activeSong) {
    alert("Play a song first");
    return;
  }
  if (!playbackHistory.length) {
    const previousFromRecent = await getPreviousFromListeningHistory();
    if (previousFromRecent) {
      await playSong(previousFromRecent, { recordHistory: true, clearForward: true });
      return;
    }
    alert("No previous song in listening history");
    return;
  }
  const previous = playbackHistory.pop();
  forwardHistory.push(activeSong);
  await playSong(previous, { recordHistory: false, clearForward: false });
}

async function playNextSong() {
  if (!activeSong) {
    const visibleSongs = getVisibleSongs();
    if (visibleSongs.length) {
      await playSong(visibleSongs[0]);
      return;
    }
    alert("No songs available to play");
    return;
  }

  if (forwardHistory.length) {
    const nextFromForward = forwardHistory.pop();
    await playSong(nextFromForward, { recordHistory: true, clearForward: false });
    return;
  }

  const visibleSongs = getVisibleSongs();
  const currentIndex = visibleSongs.findIndex((song) => songsMatch(song, activeSong));
  if (currentIndex === -1 || currentIndex >= visibleSongs.length - 1) {
    alert("No next song available");
    return;
  }
  await playSong(visibleSongs[currentIndex + 1], { recordHistory: true, clearForward: true });
}

async function likeSong(songId, btnEl) {
  let isLiked = false;
  if (btnEl) {
    const icon = btnEl.querySelector("i");
    if (icon && icon.classList.contains("ri-heart-fill")) {
      isLiked = true;
    }
  }
  
  if (isLiked) {
    const result = await postJson("/api/unlike", { user_id: config.userId, song_id: songId });
    if (btnEl) {
      btnEl.classList.remove("border-accent", "text-accent");
      btnEl.classList.add("border-border");
      const icon = btnEl.querySelector("i");
      if (icon) icon.className = "ri-heart-line text-xl";
      btnEl.title = "Like";
    }
    const npLike = document.getElementById("np-like-icon");
    if (npLike && activeSong && activeSong.song_id === songId) {
       npLike.className = "ri-heart-line text-xl";
       activeSong.is_liked = false;
    }
    // No alert on unlike to avoid annoyance, or maybe just console log
  } else {
    const result = await postJson("/api/like", { user_id: config.userId, song_id: songId });
    if (btnEl) {
      btnEl.classList.remove("border-border");
      btnEl.classList.add("border-accent", "text-accent");
      const icon = btnEl.querySelector("i");
      if (icon) icon.className = "ri-heart-fill text-xl";
      btnEl.title = "Unlike";
    }
    const npLike = document.getElementById("np-like-icon");
    if (npLike && activeSong && activeSong.song_id === songId) {
       npLike.className = "ri-heart-fill text-accent text-xl";
       activeSong.is_liked = true;
    }
    alert(result.message || "Liked");
  }
}

async function updateProfileDisplay() {
  try {
    const profileRes = await fetch(`${config.apiBaseUrl}/api/profile/${config.userId}`);
    const profile = await profileRes.json();
    
    // Update profile meta in top bar
    const profileMeta = document.querySelector(".profile-meta");
    if (profileMeta) {
      const subType = profile.subscription_type || "free";
      profileMeta.textContent = `${subType} • ${profile.user_role}`;
    }
    
    // Update wallet balance if it exists
    const walletBalance = document.getElementById("wallet-balance");
    if (walletBalance && Number.isFinite(Number(profile.wallet_balance))) {
      walletBalance.textContent = Number(profile.wallet_balance).toFixed(2);
    }

    // Update Subscription logic for instantaneous UI updates
    const subTypeEl = document.getElementById("profile-sub-type");
    if (subTypeEl) subTypeEl.textContent = profile.subscription_type || "Free";

    const subEndContainer = document.getElementById("profile-sub-end-container");
    const subEndEl = document.getElementById("profile-sub-end");
    if (subEndContainer && subEndEl) {
      if (profile.subscription_end) {
        subEndEl.textContent = profile.subscription_end;
        subEndContainer.style.display = "";
      } else {
        subEndContainer.style.display = "none";
      }
    }

    const activeSubContainer = document.getElementById("active-sub-container");
    const activeSubName = document.getElementById("active-sub-name");
    const availablePlansContainer = document.getElementById("available-plans-container");

    const isPremium = profile.subscription_type && profile.subscription_type !== 'free';
    if (activeSubContainer && activeSubName) {
      if (isPremium) {
        activeSubName.textContent = profile.subscription_type;
        activeSubContainer.style.display = "";
      } else {
        activeSubContainer.style.display = "none";
      }
    }

    if (availablePlansContainer) {
      if (isPremium) {
        availablePlansContainer.style.display = "none";
      } else {
        availablePlansContainer.style.display = "";
      }
    }
  } catch (error) {
    console.error("Failed to update profile display:", error);
  }
}

async function purchaseSubscriptionFromPage(subscriptionType, durationMonths) {
  if (!confirm(`Purchase ${subscriptionType} subscription for ${durationMonths} month(s)?`)) return;

  try {
    const response = await fetch(`${config.apiBaseUrl}/api/users/purchase-subscription`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: config.userId, subscription_type: subscriptionType, duration_months: durationMonths })
    });
    const result = await response.json();
    if (!response.ok) {
      alert(result.detail || "Failed to purchase subscription");
      return;
    }
    alert(result.message || "Subscription purchased successfully");
    await updateProfileDisplay();
  } catch (error) {
    alert("Failed to purchase subscription");
    console.error(error);
  }
}

async function createSongSale(songId) {
  const result = await postJson("/api/song-sale", { user_id: config.userId, song_id: songId });
  alert(result.message || "Done");
  if (result.ok !== false) {
    // Update profile after successful purchase
    await updateProfileDisplay();
  }
}

async function downloadSong(songId) {
  const result = await postJson("/api/download", { user_id: config.userId, song_id: songId });
  alert(result.message || "Song downloaded successfully");
}

async function addTestMoney() {
  const amountStr = window.prompt("Enter amount to add:");
  if (!amountStr) return;
  const amount = parseFloat(amountStr);
  if (isNaN(amount) || amount <= 0) {
    alert("Invalid amount");
    return;
  }
  const result = await postJson("/api/users/add-money", { user_id: config.userId, amount: amount });
  alert(result.message || "Done");
  if (result.ok !== false) {
    await updateProfileDisplay();
    const walletBalance = document.getElementById("wallet-balance");
    if (walletBalance && Number.isFinite(Number(result.wallet_balance))) {
      walletBalance.textContent = Number(result.wallet_balance).toFixed(2);
    }
  }
}

async function cancelSubscription() {
  if (!confirm("Are you sure you want to cancel your premium subscription? Unused balance will be refunded.")) return;
  try {
    const response = await fetch(`${config.apiBaseUrl}/api/users/cancel-subscription`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: config.userId })
    });
    const result = await response.json();
    if (!response.ok) {
      alert(result.detail || "Failed to cancel subscription");
      return;
    }
    alert(result.message || "Subscription cancelled");
    await updateProfileDisplay();
  } catch (error) {
    alert("Failed to cancel subscription");
    console.error(error);
  }
}

async function getUserPlaylists(force = false) {
  if (!force && Array.isArray(playlistCache)) return playlistCache;
  const res = await fetch(`${config.apiBaseUrl}/api/playlists/${config.userId}`);
  const playlists = await res.json();
  playlistCache = Array.isArray(playlists) ? playlists : [];
  return playlistCache;
}

async function addSongToPlaylist(songId) {
  const playlists = await getUserPlaylists();
  if (!playlists.length) {
    alert("No playlists found. Create one first.");
    return;
  }

  const options = playlists.map((p, i) => `${i + 1}. ${p.playlist_name}`).join("\n");
  const input = window.prompt(`Choose playlist number:\n${options}`);
  if (!input) return;
  const selectedIndex = Number.parseInt(input, 10) - 1;
  if (!Number.isInteger(selectedIndex) || selectedIndex < 0 || selectedIndex >= playlists.length) {
    alert("Invalid playlist selection");
    return;
  }

  const playlist = playlists[selectedIndex];
  const result = await postJson(`/api/playlists/${playlist.playlist_id}/songs`, {
    user_id: config.userId,
    song_id: songId,
  });
  alert(result.message || "Done");
}

async function followArtist(artistId) {
  const result = await postJson("/api/follow-artist", { user_id: config.userId, artist_id: artistId });
  alert(result.message || "Done");
  if (!result.ok) return;
  const artistToggle = document.getElementById("artist-follow-toggle");
  if (artistToggle && Number.parseInt(artistToggle.dataset.artistId || "", 10) === artistId) {
    artistToggle.classList.remove("follow-artist-btn");
    artistToggle.classList.add("unfollow-artist-btn");
    artistToggle.textContent = "Unfollow Artist";
  }
  const countEl = document.getElementById("artist-followers-count");
  if (!countEl) return;
  const current = Number.parseInt(countEl.textContent || "0", 10);
  if (Number.isFinite(current)) {
    countEl.textContent = String(current + 1);
  }
}

async function unfollowArtist(artistId, removeRow) {
  const result = await postJson("/api/unfollow-artist", { user_id: config.userId, artist_id: artistId });
  alert(result.message || "Done");
  if (!result.ok) return false;
  const artistToggle = document.getElementById("artist-follow-toggle");
  if (artistToggle && Number.parseInt(artistToggle.dataset.artistId || "", 10) === artistId) {
    artistToggle.classList.remove("unfollow-artist-btn");
    artistToggle.classList.add("follow-artist-btn");
    artistToggle.textContent = "Follow Artist";
  }
  const countEl = document.getElementById("artist-followers-count");
  if (countEl) {
    const current = Number.parseInt(countEl.textContent || "0", 10);
    if (Number.isFinite(current)) {
      countEl.textContent = String(Math.max(0, current - 1));
    }
  }
  if (removeRow) {
    const row = document.querySelector(`[data-follow-row="${artistId}"]`);
    if (row) row.remove();
  }
  return true;
}

function renderPlaylistList(playlists) {
  const host = document.getElementById("playlist-list");
  if (!host) return;
  if (!Array.isArray(playlists) || !playlists.length) {
    host.innerHTML = `<div class="empty">No playlists yet</div>`;
    return;
  }
  host.innerHTML = playlists
    .map(
      (p) => `
      <a class="list-item playlist-link" href="/playlist/${p.playlist_id}">
        <div class="name">${escapeHtml(p.playlist_name)}</div>
        <div class="meta">${Number(p.song_count || 0)} songs</div>
      </a>`
    )
    .join("");
}

async function refreshPlaylists() {
  const host = document.getElementById("playlist-list");
  if (!host) return;
  const playlists = await getUserPlaylists(true);
  renderPlaylistList(playlists);
}

async function createPlaylist() {
  if (!createPlaylistInput) return;
  const playlistName = createPlaylistInput.value.trim();
  if (!playlistName) {
    alert("Playlist name is required");
    return;
  }
  const result = await postJson("/api/playlists", {
    user_id: config.userId,
    playlist_name: playlistName,
  });
  if (result.ok !== false) {
    createPlaylistInput.value = "";
    createPlaylistInput.classList.add("hidden");
    await refreshPlaylists();
  } else {
    alert(result.message || "Failed to create playlist");
  }
}

async function createPlaylistFromModal() {
  const modalInput = document.getElementById("modal-playlist-name");
  if (!modalInput) return;
  const playlistName = modalInput.value.trim();
  if (!playlistName) {
    alert("Playlist name is required");
    return;
  }
  const result = await postJson("/api/playlists", {
    user_id: config.userId,
    playlist_name: playlistName,
  });
  if (result.ok !== false) {
    modalInput.value = "";
    document.getElementById("playlist-dialog")?.close();
    if (window.location.pathname === "/playlists") {
      window.location.reload();
    } else {
      await refreshPlaylists();
    }
  } else {
    alert(result.message || "Failed to create playlist");
  }
}

async function releaseSong() {
  const form = document.getElementById("release-song-form");
  if (!form) return;
  const titleEl = document.getElementById("release-song-title");
  const durationEl = document.getElementById("release-song-duration");
  const collaboratorsEl = document.getElementById("release-collaborators");
  const genresEl = document.getElementById("release-genres");

  const songTitle = titleEl ? titleEl.value.trim() : "";
  const duration = durationEl ? Number.parseInt(durationEl.value || "0", 10) : 0;
  const collaboratorIds = collaboratorsEl
    ? (collaboratorsEl.tagName === "SELECT"
        ? Array.from(collaboratorsEl.selectedOptions)
        : Array.from(collaboratorsEl.querySelectorAll('input[type="checkbox"]:checked')))
        .map((opt) => Number.parseInt(opt.value, 10))
        .filter(Number.isFinite)
    : [];
  const genreIds = genresEl
    ? (genresEl.tagName === "SELECT"
        ? Array.from(genresEl.selectedOptions)
        : Array.from(genresEl.querySelectorAll('input[type="checkbox"]:checked')))
        .map((opt) => Number.parseInt(opt.value, 10))
        .filter(Number.isFinite)
    : [];

  if (!songTitle) {
    alert("Song title is required");
    return;
  }
  if (!Number.isFinite(duration) || duration <= 0) {
    alert("Duration must be greater than 0");
    return;
  }
  if (!genreIds.length) {
    alert("Select at least one genre");
    return;
  }

  const editSong = config.editSong;
  const isEdit = editSong && Number.isFinite(Number(editSong.song_id));
  const endpoint = isEdit ? "/api/artist-studio/update" : "/api/artist-studio/release";
  const payload = {
    user_id: config.userId,
    song_title: songTitle,
    duration,
    collaborator_ids: collaboratorIds,
    genre_ids: genreIds,
  };
  if (isEdit) {
    payload.song_id = Number(editSong.song_id);
  } else {
    payload.release_date = new Date().toISOString().slice(0, 10);
  }

  const submitBtn = form.querySelector('button[type="submit"]');
  if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = isEdit ? "Saving..." : "Releasing..."; }

  const result = await postJson(endpoint, payload);

  if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = isEdit ? '<i class="ri-save-line mr-2"></i>Update Song' : '<i class="ri-upload-cloud-line mr-2"></i>Release Song'; }

  alert(result.message || "Done");
  if (result.ok) {
    // Return to artist studio after edit or release
    window.location.href = "/artist-studio";
  }
}

function initArtistStudioForm() {
  const form = document.getElementById("release-song-form");
  if (!form) return;

  // Bind submit if not already bound
  if (!form._submitBound) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      releaseSong();
    });
    form._submitBound = true;
  }

  const editSong = config.editSong;
  const titleEl = document.getElementById("release-song-title");
  const durationEl = document.getElementById("release-song-duration");
  const collaboratorsEl = document.getElementById("release-collaborators");
  const genresEl = document.getElementById("release-genres");

  if (!editSong) {
    // new release mode - fields already blank from server render
    return;
  }

  // Re-apply edit values (in case JS ran before server render)
  if (titleEl && !titleEl.value) titleEl.value = editSong.song_title || "";
  if (durationEl && !durationEl.value && Number.isFinite(Number(editSong.duration))) {
    durationEl.value = String(Number(editSong.duration));
  }

  const markChecked = (container, selectedIds) => {
    if (!container || !Array.isArray(selectedIds)) return;
    const wanted = new Set(selectedIds.map((id) => Number(id)).filter(Number.isFinite));
    if (container.tagName === "SELECT") {
      Array.from(container.options).forEach((opt) => {
        opt.selected = wanted.has(Number(opt.value));
      });
    } else {
      container.querySelectorAll('input[type="checkbox"]').forEach((input) => {
        const id = Number(input.value);
        input.checked = wanted.has(id);
      });
    }
  };

  markChecked(collaboratorsEl, editSong.collaborators || editSong.collaborator_ids || []);
  markChecked(genresEl, editSong.genres || editSong.genre_ids || []);
}

function renderSongTiles(target, songs) {
  if (!target) return;
  if (!songs.length) {
    target.innerHTML = `<div class="empty">No songs found</div>`;
    return;
  }
  const isPremium = (config.subscriptionType || "free") !== "free";
  const isArtist = config.userRole === "artist";
  target.innerHTML = songs
    .map(
      (s) => `
    <article class="song-tile song-clickable" data-song="${encodeSong(s)}">
      <div class="tile-cover"></div>
      <div class="tile-title">${s.song_title}</div>
      <div class="tile-meta">${s.artists || "Unknown Artist"}</div>
      <div class="tile-actions">
        <button class="play-btn">Play</button>
        ${isArtist ? "" : `
        <button class="like-btn">Like</button>
        <button class="add-playlist-btn">Add</button>
        <button class="${isPremium ? 'download-btn' : 'sale-btn'}">${isPremium ? 'Download' : 'Buy'}</button>
        `}
      </div>
    </article>`
    )
    .join("");
  refreshSongArtwork(target);
}

function renderSearchDropdown(payload) {
  if (!searchDropdown) return;
  const songs = payload.songs || [];
  const artists = payload.artists || [];
  const playlists = payload.playlists || [];
  searchDropdown.innerHTML = `
    <div class="dropdown-section p-2">
      <h4 class="text-xs font-semibold text-muted tracking-wider uppercase mb-2 px-2">Songs</h4>
      ${songs.length ? songs.map((s) => `
        <div class="flex items-center gap-3 p-2 hover:bg-surface-hover rounded-lg cursor-pointer song-clickable transition-colors" data-song="${encodeSong(s)}">
          <div class="w-10 h-10 rounded bg-surface-active shrink-0 relative overflow-hidden bg-cover-center row-cover"></div>
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium text-primary truncate">${s.song_title}</div>
            <div class="text-xs text-secondary truncate">${s.artists}</div>
          </div>
        </div>`).join("") : `<div class="empty text-muted text-sm py-2 px-2 border border-border border-dashed rounded-lg text-center mx-2 mb-2">No songs found</div>`}
    </div>
    <div class="dropdown-section p-2 border-t border-border">
      <h4 class="text-xs font-semibold text-muted tracking-wider uppercase mb-2 px-2">Artists</h4>
      ${artists.length ? artists.map((a) => `
        <div class="flex items-center justify-between p-2 hover:bg-surface-hover rounded-lg transition-colors group tile-card" data-artist-name="${escapeHtml(a.artist_name)}" data-artist-id="${a.artist_id}">
          <a href="/artist/${a.artist_id}" class="flex items-center gap-3 min-w-0 flex-1">
            <div class="w-10 h-10 rounded-full bg-surface-active shrink-0 relative overflow-hidden bg-cover-center artist-portrait"></div>
            <div class="min-w-0">
              <div class="text-sm font-medium text-primary truncate">${a.artist_name}</div>
              <div class="text-xs text-secondary truncate">${a.num_followers} followers</div>
            </div>
          </a>
          <button class="text-xs font-medium px-3 py-1.5 rounded-full border border-border hover:border-primary hover:text-primary transition-colors follow-artist-btn ml-2" data-artist-id="${a.artist_id}">Follow</button>
        </div>`).join("") : `<div class="empty text-muted text-sm py-2 px-2 border border-border border-dashed rounded-lg text-center mx-2 mb-2">No artists found</div>`}
    </div>
    <div class="dropdown-section p-2 border-t border-border">
      <h4 class="text-xs font-semibold text-muted tracking-wider uppercase mb-2 px-2">Playlists</h4>
      ${playlists.length ? playlists.map((p) => `
        <a href="/playlist/${p.playlist_id}" class="flex items-center gap-3 p-2 hover:bg-surface-hover rounded-lg transition-colors">
          <div class="w-10 h-10 rounded bg-surface-active shrink-0 flex items-center justify-center text-secondary border border-border">
            <i class="ri-play-list-line text-lg"></i>
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium text-primary truncate">${p.playlist_name}</div>
            <div class="text-xs text-secondary truncate">${p.song_count} songs</div>
          </div>
        </a>`).join("") : `<div class="empty text-muted text-sm py-2 px-2 border border-border border-dashed rounded-lg text-center mx-2 mb-2">No playlists found</div>`}
    </div>
  `;
  refreshSongArtwork(searchDropdown);
  refreshArtistArtwork(searchDropdown);
  searchDropdown.classList.remove("hidden");
}

async function runSearchImmediate() {
  if (!searchInput || !searchDropdown) return;
  const q = searchInput.value.trim();
  if (!q) {
    searchDropdown.classList.add("hidden");
    searchDropdown.innerHTML = "";
    return;
  }
  const res = await fetch(`${config.apiBaseUrl}/api/search?user_id=${config.userId}&q=${encodeURIComponent(q)}`);
  const payload = await res.json();
  renderSearchDropdown(payload);
}

function bindGlobalEvents() {
  document.addEventListener("click", (e) => {
    const playBtn = e.target.closest(".play-btn");
    if (playBtn) {
      const tile = playBtn.closest("[data-song]");
      if (!tile) return;
      const song = parseSongFromElement(tile);
      if (!song) return;
      playSong(song);
      return;
    }

    const likeBtn = e.target.closest(".like-btn");
    if (likeBtn) {
      const target = e.target.closest(".like-btn");
      if (!target) return;
      const song = parseSongFromElement(target.closest("[data-song]") || target);
      if (!song) return;
      likeSong(song.song_id, target);
      return;
    }

    const addPlaylistBtn = e.target.closest(".add-playlist-btn");
    if (addPlaylistBtn) {
      const tile = addPlaylistBtn.closest("[data-song]");
      if (!tile) return;
      const song = parseSongFromElement(tile);
      if (!song) return;
      addSongToPlaylist(song.song_id);
      return;
    }

    const saleBtn = e.target.closest(".sale-btn");
    if (saleBtn) {
      const tile = saleBtn.closest("[data-song]");
      if (!tile) return;
      const song = parseSongFromElement(tile);
      if (!song) return;
      createSongSale(song.song_id);
      return;
    }

    const downloadBtn = e.target.closest(".download-btn");
    if (downloadBtn) {
      const tile = downloadBtn.closest("[data-song]");
      if (!tile) return;
      const song = parseSongFromElement(tile);
      if (!song) return;
      downloadSong(song.song_id);
      return;
    }

    const unfollowArtistBtn = e.target.closest(".unfollow-artist-btn");
    if (unfollowArtistBtn) {
      const artistId = Number.parseInt(unfollowArtistBtn.dataset.artistId || "", 10);
      if (!Number.isFinite(artistId)) return;
      const removeRow = Boolean(unfollowArtistBtn.closest("[data-follow-row]"));
      unfollowArtist(artistId, removeRow);
      return;
    }

    const followArtistBtn = e.target.closest(".follow-artist-btn");
    if (followArtistBtn) {
      const artistId = Number.parseInt(followArtistBtn.dataset.artistId || "", 10);
      if (!Number.isFinite(artistId)) return;
      followArtist(artistId);
      return;
    }

    const clickSong = e.target.closest(".song-clickable, .song-tile");
    if (clickSong && clickSong.dataset.song && !e.target.closest(".tile-actions") && !e.target.closest(".delete-song-btn")) {
      const song = parseSongFromElement(clickSong);
      if (!song) return;
      // Redirect to song page instead of showing stats
      window.location.href = `/song/${song.song_id}`;
      return;
    }

    const deleteSongBtn = e.target.closest(".delete-song-btn");
    if (deleteSongBtn) {
      const songId = Number.parseInt(deleteSongBtn.dataset.songId || "", 10);
      const songTitle = deleteSongBtn.dataset.songTitle || "this song";
      const redirectTo = deleteSongBtn.dataset.redirect;
      if (!Number.isFinite(songId)) return;
      deleteSong(songId, songTitle, redirectTo);
      return;
    }

    if (searchDropdown && !e.target.closest(".search-wrap")) {
      searchDropdown.classList.add("hidden");
    }
    if (statsPopover && !e.target.closest(".song-stats-popover")) {
      hideSongStats();
    }
  });

  if (closeStats) closeStats.addEventListener("click", hideSongStats);

  if (searchBtn) searchBtn.addEventListener("click", runSearchImmediate);
  if (addMoneyBtn) addMoneyBtn.addEventListener("click", addTestMoney);
  
  const cancelSubBtn = document.getElementById("cancel-sub-btn");
  if (cancelSubBtn) cancelSubBtn.addEventListener("click", cancelSubscription);
  
  document.querySelectorAll(".purchase-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const type = btn.dataset.type;
      const duration = Number.parseInt(btn.dataset.duration || "1", 10);
      purchaseSubscriptionFromPage(type, duration);
    });
  });
  
  if (createPlaylistBtn) {
    createPlaylistBtn.addEventListener("click", () => {
      if (createPlaylistInput.classList.contains("hidden")) {
        createPlaylistInput.classList.remove("hidden");
        createPlaylistInput.focus();
      } else {
        createPlaylist();
      }
    });
  }

  const savePlaylistBtn = document.getElementById("save-playlist-btn");
  if (savePlaylistBtn) {
    savePlaylistBtn.addEventListener("click", createPlaylistFromModal);
  }

  const cancelPlaylistBtn = document.getElementById("cancel-playlist-btn");
  if (cancelPlaylistBtn) {
    cancelPlaylistBtn.addEventListener("click", () => {
      document.getElementById("playlist-dialog")?.close();
    });
  }
  const studioForm = document.getElementById("release-song-form");
  if (studioForm && !studioForm._submitBound) {
    studioForm.addEventListener("submit", (e) => {
      e.preventDefault();
      releaseSong();
    });
    studioForm._submitBound = true;
  }
  if (createPlaylistInput) {
    createPlaylistInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") createPlaylist();
    });
  }
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(runSearchImmediate, 160);
    });
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") runSearchImmediate();
    });
  }

  document.querySelectorAll(".view-all").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const targetKey = link.dataset.toggleSection;
      if (!targetKey) return;
      const sectionId = targetKey === "trending" ? "trending-grid" : targetKey === "artists" ? "recommended-grid" : null;
      if (!sectionId) return;
      const section = document.getElementById(sectionId);
      if (!section) return;
      const expanded = section.classList.toggle("expanded");
      section.classList.toggle("collapsed", !expanded);
      link.textContent = expanded ? "Show less" : "See all";
    });
  });

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      if (!activeSong) return;
      paused = !paused;
      const playIcon = document.getElementById("play-icon");
      if (playIcon) playIcon.className = paused ? "ri-play-fill text-2xl ml-0.5" : "ri-pause-fill text-2xl";
      if (paused) {
        suspendTestAudio();
      } else if (activeSong) {
        resumeTestAudio();
      }
      savePlayerState();
    });
  }

  if (prevBtn) {
    prevBtn.addEventListener("click", () => {
      playPreviousSong();
    });
  }

  if (nextBtn) {
    nextBtn.addEventListener("click", () => {
      playNextSong();
    });
  }

  const playerBuyBtn = document.getElementById("player-buy");
  if (playerBuyBtn) {
    playerBuyBtn.addEventListener("click", () => {
      if (!activeSong) return;
      createSongSale(activeSong.song_id);
    });
  }
  
  const playerAddPlaylistBtn = document.getElementById("player-add-playlist");
  if (playerAddPlaylistBtn) {
    playerAddPlaylistBtn.addEventListener("click", () => {
      if (!activeSong) return;
      addSongToPlaylist(activeSong.song_id);
    });
  }
  
  const playerDownloadBtn = document.getElementById("player-download");
  if (playerDownloadBtn) {
    playerDownloadBtn.addEventListener("click", () => {
      if (!activeSong) return;
      if (config.subscriptionType && config.subscriptionType !== 'free') {
        downloadSong(activeSong.song_id);
      } else {
        createSongSale(activeSong.song_id);
      }
    });
  }

  const npLikeBtn = document.getElementById("np-like");
  if (npLikeBtn) {
    npLikeBtn.addEventListener("click", () => {
      if (!activeSong) return;
      likeSong(activeSong.song_id);
      activeSong.is_liked = !activeSong.is_liked;
      savePlayerState();
      
      const icon = document.getElementById("np-like-icon");
      if (icon) {
        if (activeSong.is_liked) {
          icon.classList.remove("ri-heart-line");
          icon.classList.add("ri-heart-fill", "text-accent");
        } else {
          icon.classList.add("ri-heart-line");
          icon.classList.remove("ri-heart-fill", "text-accent");
        }
      }
    });
  }
}

async function initApp() {
  console.log("[initApp] Starting initialization");
  await loadMediaManifest();
  console.log("[initApp] Manifest loaded");
  await loadArtistMappings();
  console.log("[initApp] Artist mappings loaded");
  bindGlobalEvents();
  console.log("[initApp] Global events bound");
  initArtistStudioForm();
  console.log("[initApp] Artist studio form initialized");
  refreshSongArtwork();
  console.log("[initApp] Song artwork refreshed");
  refreshArtistArtwork();
  console.log("[initApp] Artist artwork refreshed");
  restorePlayerState();
  console.log("[initApp] Player state restored, initialization complete");
  runPageAnimations();
}

function runPageAnimations() {
  if (typeof gsap === 'undefined') return;
  gsap.fromTo(".song-clickable, .tile-card", 
    { y: 20, opacity: 0 },
    { y: 0, opacity: 1, duration: 0.5, stagger: 0.05, ease: "power2.out", clearProps: "all" }
  );
  gsap.fromTo("h1, h2, h3", 
    { x: -20, opacity: 0 },
    { x: 0, opacity: 1, duration: 0.6, ease: "power2.out", clearProps: "all" }
  );
}

document.body.addEventListener('htmx:afterSwap', function(evt) {
  if (evt.detail.target.id === 'main-content') {
    // Rebind inline scripts from swapped content if needed
    const pageScripts = evt.detail.target.querySelectorAll("script");
    pageScripts.forEach(script => {
      const newScript = document.createElement("script");
      if (script.src) {
        newScript.src = script.src;
      } else {
        newScript.textContent = script.textContent;
      }
      document.body.appendChild(newScript);
      document.body.removeChild(newScript);
    });

    initArtistStudioForm();
    refreshSongArtwork();
    refreshArtistArtwork();
    runPageAnimations();
  }
});

initApp();
