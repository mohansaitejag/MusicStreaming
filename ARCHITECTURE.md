# Architecture — Music Streaming DBMS Project

> A full-stack music-streaming platform built as a DBMS learning project. It demonstrates real-world database design: relational schema design, triggers, stored procedures, transaction safety, and concurrency control — all wired up to a live web application.

---

## Table of Contents

1. [High-Level Overview](#1-high-level-overview)
2. [Technology Stack](#2-technology-stack)
3. [Project Directory Map](#3-project-directory-map)
4. [Layer-by-Layer Explanation](#4-layer-by-layer-explanation)
5. [Database Schema & Design Decisions](#5-database-schema--design-decisions)
6. [Request Lifecycle — How Everything Connects](#6-request-lifecycle--how-everything-connects)
7. [Key Concepts Demonstrated](#7-key-concepts-demonstrated)

---

## 1. High-Level Overview

The application is split into **two independent servers** that talk to each other over HTTP, and a single **MySQL database** that stores all persistent data.

```
+----------------------------------------------------------------------+
|                          User's Browser                              |
+----------------------------------------------------------------------+
                       |  visits localhost:5000
                       v
+----------------------------------------------------------------------+
|               Frontend  (Flask - port 5000)                          |
|   Renders HTML pages. Calls the API server to get data.              |
+----------------------------------------------------------------------+
                       |  HTTP requests to localhost:8000
                       v
+----------------------------------------------------------------------+
|               Backend   (FastAPI - port 8000)                        |
|   Pure JSON REST API. Validates requests, runs business logic.       |
+----------------------------------------------------------------------+
                       |  SQL queries via connection pool
                       v
+----------------------------------------------------------------------+
|               MySQL Database  (music_app)                            |
|   Stores users, songs, playlists, history, transactions, etc.        |
|   Contains triggers, indexes, and stored procedures.                 |
+----------------------------------------------------------------------+
```

**Why two servers?** This mirrors real-world architecture where the UI layer and the data/business layer are decoupled. The Flask frontend only renders pages; all data access goes through the FastAPI backend. This means you could replace the Flask UI with a mobile app, a React app, or anything else without touching the backend.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Database** | MySQL (InnoDB) | Relational data store; triggers, procedures, indexes |
| **API Server** | FastAPI (Python) | REST API; data validation, JWT auth, business logic |
| **API Runtime** | Uvicorn | ASGI server that runs FastAPI |
| **Web UI** | Flask (Python) | Server-side HTML rendering; session management |
| **DB Driver** | mysql-connector-python | Python <-> MySQL communication; connection pooling |
| **Data Validation** | Pydantic | Validates all API request/response shapes |
| **Auth** | JWT (PyJWT) + bcrypt | Stateless token auth; secure password hashing |
| **Config** | python-dotenv | Reads secrets from `.env` file at startup |

---

## 3. Project Directory Map

```
DBMS/
|
+-- run_api.py                  <- Starts the FastAPI backend server
+-- run_ui.py                   <- Starts the Flask frontend server
+-- requirements.txt            <- All Python dependencies
+-- .env                        <- Secret config values (not committed to git)
+-- .env.example                <- Template showing what .env should contain
|
+-- backend/                    <- API server (FastAPI)
|   +-- main.py                 <- App factory: wires up routes, CORS, startup check
|   +-- core/
|   |   +-- config.py           <- Reads .env and exposes a settings object
|   +-- db/
|   |   +-- connection.py       <- MySQL connection pool (singleton)
|   |   +-- repositories.py     <- Every SQL query the app makes (1549 lines)
|   +-- models/
|   |   +-- schemas.py          <- Pydantic models: the shape of every request/response
|   +-- services/
|   |   +-- music_service.py    <- Orchestration logic (composes multiple DB calls)
|   +-- api/
|       +-- routes/
|           +-- auth.py         <- POST /api/auth/login  and  POST /api/auth/register
|           +-- music.py        <- All other API endpoints (songs, playlists, artists...)
|
+-- frontend/                   <- Web UI server (Flask)
|   +-- app.py                  <- All Flask routes; renders HTML templates
|   +-- templates/              <- Jinja2 HTML pages (one file per page)
|   |   +-- base.html           <- Shared layout, navigation bar, player bar
|   |   +-- index.html          <- Home/dashboard page
|   |   +-- login.html          <- Login form
|   |   +-- register.html       <- Registration form
|   |   +-- song.html           <- Individual song detail page
|   |   +-- artist.html         <- Public artist profile page
|   |   +-- artist_studio.html  <- Private artist dashboard (release/edit songs)
|   |   +-- playlist.html       <- Single playlist view
|   |   +-- playlists.html      <- All playlists listing
|   |   +-- all_songs.html      <- Full song catalogue
|   |   +-- collection.html     <- User's purchased/downloaded songs
|   |   +-- followed_artists.html  <- Artists the user follows
|   |   +-- genre.html          <- Songs within a single genre
|   |   +-- genres.html         <- All genres listing
|   |   +-- profile.html        <- User profile, wallet, subscription management
|   +-- static/
|       +-- css/styles.css      <- Global stylesheet
|       +-- js/app.js           <- All frontend JavaScript (API calls, UI interactions)
|       +-- art/                <- Album art / artwork images
|       +-- media/              <- Audio/media files
|
+-- race_condition_demo/        <- Standalone scripts to demonstrate DB concurrency
|
|
--- sql/
   +-- seed.sql                <- Complete DB: schema + triggers + procedures + sample data


```

---

## 4. Layer-by-Layer Explanation

### 4.1 Root Level

#### `run_api.py` — Backend Launcher
Starts the FastAPI server using **Uvicorn**. It reads `host` and `port` from the settings object (which in turn reads `.env`). The `reload=True` flag means any code change instantly restarts the server — useful during development.

#### `run_ui.py` — Frontend Launcher
Starts the Flask development server. Flask reads `FLASK_HOST` and `FLASK_PORT` from the environment. Run this in a **separate terminal** from `run_api.py`.

#### `.env` / `.env.example`
Secrets (database password, JWT signing key) are never hardcoded in source files. Instead they live in `.env`, which is loaded at startup and **excluded from git**. `.env.example` is a safe-to-commit template that shows collaborators which values they need to fill in.

---

### 4.2 `backend/` — FastAPI API Server

The backend is a pure JSON API. It has **no HTML, no sessions, no cookies**. Every response is a structured JSON object. This makes it easy to test, swap frontends, or build a mobile client later.

---

#### `backend/main.py` — The App Factory

Think of this as the **control room** of the API server. It does four things:

1. **Creates the FastAPI app** and gives it a title.
2. **Adds CORS middleware** — This allows the Flask frontend (running on port 5000) to make requests to the API (running on port 8000). Without this, browsers would block cross-origin requests.
3. **Registers route groups** — `auth_router` (handles login/register) and `music_router` (handles everything else) are "plugged in" here.
4. **Runs a startup health check** — When the server boots, it immediately tries to connect to MySQL and prints the result. If the DB is down, you know instantly instead of discovering it on the first real request.

---

#### `backend/core/config.py` — Settings Object

A simple class that reads environment variables and exposes them as typed Python attributes. Every other part of the codebase imports `settings` from here — **one single source of truth** for all configuration.

| Setting | What it's for |
|---|---|
| `mysql_host/port/user/password/db` | How to connect to MySQL |
| `fastapi_host/port` | Where to bind the API server |
| `jwt_secret_key` | Used to sign and verify auth tokens |
| `jwt_algorithm` | The algorithm used for JWT (HS256 = HMAC-SHA256) |

---

#### `backend/db/connection.py` — Connection Pool

**The Problem:** Opening a new database connection for every single HTTP request is very slow (a full TCP handshake + MySQL authentication each time).

**The Solution:** A **connection pool** — a collection of pre-opened connections that sit idle and are handed out on demand. When a request finishes, the connection is returned to the pool (not closed).

Key details:
- The pool is created **once** (`_pool` is a module-level variable, initialized on first use).
- Pool size is **10** — at most 10 queries can run in parallel.
- `get_connection()` is the single function called across the entire app whenever SQL is needed.
- `test_connection()` is only called at startup to verify the DB is reachable.

---

#### `backend/db/repositories.py` — The SQL Layer (1549 lines)

This is the largest and most important file in the backend. It is the **only place in the entire application where SQL is written**. Nothing outside this file talks to MySQL directly.

**Internal helpers (private functions):**

| Function | What it does |
|---|---|
| `_fetch_all_dict(query, params)` | Runs a SELECT, returns a list of row-dictionaries |
| `_fetch_one_dict(query, params)` | Runs a SELECT, returns only the first row (or None) |
| `_execute(query, params)` | Runs INSERT/UPDATE/DELETE, commits, returns affected row count |
| `_call_procedure(name, params)` | Calls a MySQL stored procedure by name |

Every query uses `%s` placeholders filled in from a `params` tuple — never string concatenation. This prevents **SQL injection** attacks.


#### `backend/models/schemas.py` — Data Contracts (Pydantic)

Pydantic models are Python classes that define the **exact shape** of data flowing in and out of the API. FastAPI uses them automatically to:
- **Validate requests**: If a required field is missing or the wrong type, FastAPI rejects the request with a clear error message before any code runs.
- **Serialize responses**: Converts Python dicts/objects into clean JSON.
- **Generate API docs**: FastAPI auto-generates interactive docs at `/docs` using these schemas.

---

#### `backend/services/music_service.py` — Orchestration Layer

This thin layer sits between the route handlers and the repositories. Currently it handles the two most complex data-fetching operations:

- **`get_home_payload(user_id)`**: Calls ~9 different repository functions and merges their results into a single dictionary. This prevents the frontend from making 9 separate API calls just to load the home page.
- **`search_payload(user_id, term)`**: Runs song search, artist search, and playlist search in sequence and combines results.

As the app grows, more complex orchestration logic (e.g., "when a song is released, notify followers") would live here — keeping routes thin and repositories focused on single queries.

---

#### `backend/api/routes/auth.py` — Authentication Endpoints

Prefix: `/api/auth`

**How login works (step by step):**
1. User submits email + password.
2. Backend fetches the stored **bcrypt hash** of their password from the DB.
3. `bcrypt.checkpw()` verifies the submitted password against the hash — bcrypt is designed to be slow, making brute-force attacks impractical.
4. If it matches, a **JWT (JSON Web Token)** is created. The token contains the `user_id` and `user_role`, is signed with the secret key, and expires in 24 hours.
5. The token is returned to the client, which includes it in the `Authorization: Bearer <token>` header on future requests.

| Endpoint | Method | What it does |
|---|---|---|
| `/api/auth/login` | POST | Verifies credentials, returns JWT |
| `/api/auth/register` | POST | Creates new user or artist account |

---

#### `backend/api/routes/music.py` — All Other Endpoints

Prefix: `/api`

This file exposes every feature of the platform as REST endpoints. It acts purely as a **translation layer** — it takes an HTTP request, calls the right repository or service function, and returns the result as JSON. Almost no logic lives here; it all lives in `repositories.py`.

Key endpoint groups:

| Group | Endpoints | Purpose |
|---|---|---|
| **Data Reads** | `GET /home`, `GET /search`, `GET /profile/{id}`, `GET /songs/{id}`, `GET /artists/{id}`, `GET /genres` | Fetch data for pages |
| **User Actions** | `POST /like`, `POST /unlike`, `POST /follow-artist`, `POST /unfollow-artist`, `POST /simulate-play` | Record user interactions |
| **Commerce** | `POST /song-sale`, `POST /download`, `POST /users/add-money`, `POST /users/withdraw-money`, `POST /users/purchase-subscription`, `POST /users/cancel-subscription` | Financial transactions |
| **Playlists** | `POST /playlists`, `POST /playlists/{id}/songs`, `GET /playlists/{id}/songs` | Playlist management |
| **Artist Studio** | `GET /artist-studio/{id}`, `POST /artist-studio/release`, `POST /artist-studio/update`, `DELETE /artist-studio/song/{id}` | Artist content management |

---

### 4.3 `frontend/` — Flask Web UI

The frontend is a  **server-side rendered** web application. Flask handles routes, fetches data from the FastAPI backend, and renders an HTML page — which is then sent to the browser.

---

#### `frontend/app.py` — All Flask Routes (485 lines)

Every URL the user visits is handled here. The file is organized around a few utility functions and then route handlers.

**Internal helpers:**

| Function | Role |
|---|---|
| `_get_logged_in_user_id()` | Reads `user_id` from the Flask session (set at login) |
| `_require_user_id()` | Returns the user ID or `None` if not logged in (used to guard pages) |
| `_safe_get(path, params)` | Makes a GET request to the FastAPI API with the user's auth token; returns JSON or a fallback on failure |
| `_safe_post(path, json_data)` | Makes a POST request to the FastAPI API; returns JSON or fallback |

**How session-based auth works in Flask:**
When a user logs in, Flask stores `user_id`, `user_role`, and `access_token` in the **server-side session** (a signed cookie). Every subsequent page load reads from this session. When the UI calls any API endpoint, `_safe_get/_safe_post` automatically include the JWT from the session as the `Authorization` header.

**Notable Flask routes:**

| Route | Template | Description |
|---|---|---|
| `GET /` | — | Redirects to login |
| `GET /home` | `index.html` | Fetches the home payload; artists see the studio dashboard |
| `GET /login`, `POST /login` | `login.html` | Shows form; on POST, calls `/api/auth/login`, stores token in session |
| `GET /register`, `POST /register` | `register.html` | Shows form; on POST, calls `/api/auth/register` |
| `GET /logout` | — | Clears session, redirects to login |
| `GET /song/<id>` | `song.html` | Loads a song's detail page |
| `GET /artist/<id>` | `artist.html` | Loads a public artist profile |
| `GET /artist-studio` | `artist_studio.html` | Artist-only dashboard (redirects regular users) |
| `GET /profile` | `profile.html` | User profile with wallet and subscription controls |
| `GET /genres`, `GET /genre/<id>` | `genres.html`, `genre.html` | Browse genres |
| `GET /playlists`, `GET /playlist/<id>` | `playlists.html`, `playlist.html` | Browse and view playlists |
| `GET /collection` | `collection.html` | Purchased and downloaded songs |
| `GET /all-songs` | `all_songs.html` | Full song catalogue |

---

#### `frontend/templates/` — HTML Pages (Jinja2)

All templates extend `base.html`, which provides the shared shell (navigation bar, music player bar at the bottom, CSS/JS imports).

| Template | What the user sees |
|---|---|
| `base.html` | The navigation sidebar, top bar, bottom player bar — present on every page |
| `index.html` | Home dashboard: trending songs, recommendations, playlists, followed artists |
| `login.html` | Email + password login form |
| `register.html` | Name, email, password, role (user/artist) registration form |
| `song.html` | Song title, artist, duration, stats (plays, likes, downloads); like button, buy button, add-to-playlist |
| `artist.html` | Artist profile: name, follower count, follow button, their songs |
| `artist_studio.html` | Private artist dashboard: stats summary, release new song form, edit/delete existing songs, transaction history |
| `playlist.html` | Playlist contents: songs list, add song controls |
| `playlists.html` | All of the user's playlists |
| `all_songs.html` | Scrollable catalogue of every song |
| `collection.html` | Songs the user has bought or downloaded |
| `followed_artists.html` | Artists the user follows |
| `genre.html` | All songs in a specific genre |
| `genres.html` | All genres as browsable cards |
| `profile.html` | User info, wallet balance, top-up controls, subscription status, buy/cancel subscription |

---

#### `frontend/static/js/app.js` — Frontend JavaScript (~51 KB)

This is the single JavaScript file for the entire frontend. It handles all **dynamic interactions** — things that happen without a full page reload:

- Clicking the **Like** button (sends POST `/api/like` or `/api/unlike`, updates button state)
- **Simulating a song play** (sends POST `/api/simulate-play` to increment play count)
- **Adding a song to a playlist** (dropdown selector, sends POST to `/api/playlists/{id}/songs`)
- **Buying / downloading a song** (sends POST, updates UI feedback)
- **Following/unfollowing an artist**
- **Wallet top-up** and **subscription purchase** from the profile page
- **Searching** (sends GET `/api/search`, renders results dynamically)
- **Artist studio actions**: release form submission, song editing, song deletion
- The **bottom music player bar**: play/pause state, now-playing display

#### `frontend/static/css/styles.css` — Global Styles

A small stylesheet providing base styles that complement the inline styles defined in templates. Most visual styling is done inline or in `base.html`'s `<style>` block for simplicity.

---

### 4.4 `sql/` — Database Blueprint

#### `sql/seed.sql` — The Complete Database Definition

This single file creates the **entire database from scratch**.

**Section 1: Table Definitions (Schema)**

| Table | What it stores |
|---|---|
| `users` | Every account: regular users and artists. Artists have `NULL` subscription fields (enforced by a `CHECK` constraint). |
| `artist` | Artist-specific data: name, nationality, follower count, monetization status. Separate from `users` because artist metadata differs from user account data. |
| `songs` | Song metadata: title, duration, play/like/download counters, popularity score, release date. |
| `genre` | Simple lookup table of music genres (Pop, Rock, Romantic, Indie, Hip-Hop). |
| `playlist` | User-created playlists (name, date, owner). |
| `make_song` | **Many-to-many**: a song can have multiple artists, an artist can have multiple songs (collaborations). |
| `user_likes_song` | **Many-to-many**: which users liked which songs. |
| `categorize_song` | **Many-to-many**: a song can belong to multiple genres. |
| `playlist_songs` | **Many-to-many**: which songs are in which playlist. |
| `user_follows_artist` | **Many-to-many**: which users follow which artists. |
| `user_history` | Listening history: `(user_id, song_id)` pair + timestamp + listen count. The primary key prevents duplicate rows — re-listening increments `listening_count`. |
| `song_sales` | Records when a user buys a song. A `UNIQUE` constraint prevents buying the same song twice. |
| `artist_transactions` | Financial ledger: every time a song is sold, each contributing artist gets a credit entry here. |
| `user_downloads` | Tracks premium-user downloads. A `UNIQUE` constraint prevents downloading the same song twice. |

**Section 2: Indexes**

Custom indexes are created on the columns most frequently used in `WHERE` and `ORDER BY` clauses — for example, `songs.popularity_score` (used for trending feed) and `artist.num_followers`.

**Section 3: Triggers**

| Trigger | When it fires | What it does |
|---|---|---|
| `before_users_insert` | Before a new user row is inserted | If role is `"artist"`, clears subscription fields. If role is `"user"` and no subscription given, defaults to `"free"`. |
| `before_users_update` | Before a user row is updated | Same subscription-field enforcement on updates. |
| `after_song_sale_insert` | After a song is purchased | Increments `songs.num_downloads` for that song. |
| `after_history_insert` | After a first listen is recorded | Increments `songs.num_plays`. |
| `after_history_update` | After a listen count increases | Increments `songs.num_plays` (so every re-listen counts). |
| `after_follow_insert` | After a user follows an artist | Increments `artist.num_followers`. |
| `after_follow_delete` | After a user unfollows an artist | Decrements `artist.num_followers`. |

**Section 4: Stored Procedure — `check_and_update_subscription`**

A stored procedure is a named SQL program stored inside the database itself. This one is called every time a user's profile is fetched. It checks if the user's `subscription_end` date has passed and, if so, automatically resets their subscription type to `"free"`.

### 4.5 `race_condition_demo/` — Educational Demos

These scripts exist purely to **demonstrate database concurrency problems** — a core topic in DBMS education. They are not part of the running application.

The key insight being demonstrated: **when multiple processes read and then write the same data simultaneously, without proper locking, the results can be wrong.**

#### `tx_demo.py` — The Main Demo Engine (651 lines)

The central script that implements every demo scenario. It uses Python's `ThreadPoolExecutor` to simulate many users acting simultaneously. It supports a CLI with `--demo`, `--mode`, and `--threads` flags.


## 5. Database Schema & Design Decisions

### Entity-Relationship Overview

```
users ------------- playlist       (one-to-many: a user owns many playlists)
  |
  +-- user_history --------- songs   (many-to-many via junction table)
  +-- user_likes_song ------- songs
  +-- user_follows_artist --- artist
  +-- song_sales ------------ songs
  +-- user_downloads -------- songs

songs --- make_song ------- artist      (many-to-many: collaborations)
songs --- categorize_song - genre       (many-to-many: multi-genre songs)
songs --- playlist_songs -- playlist    (many-to-many)

artist --- artist_transactions          (one-to-many: revenue log per artist)
song_sales --- artist_transactions      (one-to-one: each sale generates a credit)
```


### `SELECT ... FOR UPDATE` in Song Sales 
- Itplaces a row-level lock on the user row, forcing other transactions to wait until the first one commits. This guarantees correctness.


---

## 6. Request Lifecycle — How Everything Connects

Here is a concrete example: **a user clicks "Like" on a song.**

```
Step 1: User clicks the heart icon on song.html
        app.js detects the click event

Step 2: app.js sends directly to FastAPI:
        POST http://localhost:8000/api/like
        Body:    { "user_id": 3, "song_id": 15 }
        Headers: { Authorization: "Bearer <jwt_token>" }

Step 3: FastAPI receives the request
        music.py -> like_song() is called
        Calls repo.like_song(3, 15)

Step 4: repositories.py -> like_song()
        Runs: INSERT IGNORE INTO user_likes_song (user_id, song_id) VALUES (3, 15)
        "INSERT IGNORE" means: if the row already exists, silently do nothing
        A DB trigger fires automatically:
            UPDATE songs SET num_likes = num_likes + 1 WHERE song_id = 15

Step 5: FastAPI returns:
        { "ok": true, "message": "Liked" }

Step 6: app.js receives the 200 response
        Updates the heart icon to filled (liked state)
        Updates the displayed like count on the page
```

- Notice that **the Flask server is not involved at all** in this interaction. The JavaScript in the browser calls the FastAPI server directly. Flask only rendered the initial HTML page — from that point on, all interactivity goes directly to the API.
- When ever full page reloads are not required, app.js makes API call based on event and updates only target section.This makes ui responsive,and good user experience. 
- Page switches (like switching from profie page to all songs page, etc..) require full page render from Flask.
---
