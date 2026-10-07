# 🎵 Music Streaming App (Spotify-Style UI & Simulated Playback)

A full-stack, modular music streaming application designed with a Spotify-inspired violet-theme UI. The system implements a stateless FastAPI backend interacting with a MySQL database, coupled with a Flask frontend web server. 

Playback is simulated on the client side with sample audio, while the entire business logic surrounding subscriptions, purchases, like systems, user playlists, follow graphs, history logging, and artist studio dashboards is fully implemented.

---

## 🛠️ Technology Stack

* **Frontend Web Server**: Flask (Python), HTML5, CSS3 (Custom Vanilla Violet Theme), Vanilla JavaScript
* **Backend API Server**: FastAPI (Python), Pydantic (Data validation), JWT (Authentication)
* **Database**: MySQL (Relational schema with foreign keys, transaction handling, and aggregate metrics)
* **Environment/Package Management**: `uv` or `pip`

---

## 🚀 Key Features Implemented

### 1. Security & Authentication
* **Role-Based Accounts**: Supports distinct roles for regular **Listeners** and **Artists** during registration.
* **Secure Hashing**: Passwords are encrypted using `bcrypt` before storage.
* **Stateless JWTs**: Token-based authentication utilizing HMAC-SHA256 (`HS256`) algorithms with customizable token expiry (24-hour default).

### 2. Listener Experience & Personalization
* **Dynamic Home Dashboard**: Custom dashboard loaded with trending tracks, personal playlists, liked songs, followed artists, recent play history, and available genres.
* **Unified Search Engine**: Search globally across songs, artists, and playlists using efficient query filters.
* **Smart Recommendation Engine**: Recommends new songs based on the user's listening history, interested genres.
* **Simulated Playback & Analytics**: Client-side media controller with real play/pause/seek operations. Listening triggers automatic database updates, logging user history, incrementing play counts, and recalculating track popularity scores.
* **Social Engagement**:
  * Like/unlike songs to add/remove them from a dedicated library.
  * Follow/unfollow artist profiles to keep track of new releases.
  * Create custom user playlists and add/remove songs dynamically.

### 3. Monetization & Subscriptions
* **Personal Digital Wallet**: Top-up wallets or withdraw artist earnings.
* **Premium Subscriptions**: listeners can purchase premium Subscriptions for monthly and anually with support for cancellation.
* **Song Purchases (Pay-to-Own)**: listeners can buy specific premium songs. The system handles transaction processing, wallet balance deduction, and executes the royalty/revenue split directly to the artist.
* **Downloads**: Safe download pathways permitted only for tracks owned by the listener or active premium subscriber.

### 4. Exclusive Artist Studio
* **KPI Dashboard**: View total earnings, transaction count, listener reach, and overall play statistics.
* **Music Release Workflow**: Publish new tracks specifying title, duration, release date, and multi-genre tagging.
* **Collaborator Support**: Real database mappings for multi-artist collaborations, allowing main and collaborating artists to share credits and visibility.
* **Catalog Management**: Edit song titles, durations, genres, or collaborator lists, or delete/retire tracks from the active library.
* **Earnings**: view and manage earnings.

---

## 📁 Project Structure

```text
backend/
  api/routes/          # FastAPI route handlers
  core/                # configuration
  db/                  # DB connection + repository layer
  models/              # pydantic schemas
  services/            # business logic layer
frontend/
  templates/           # Flask templates
  static/css/          # theme + layout
  static/js/           # UI interactions + API calls
sql/
  seed.sql             # sample data
ARCHITECTURE.md        # detailed overview of project.
run_api.py             # start FastAPI
run_ui.py              # start Flask UI
```


## ⚡ Setup & Installation

### Prerequisites
Make sure you have a running MySQL instance and `python` installed.

### 1. Install Dependencies
Create a virtual environment and install the required modules:

```bash
uv venv
uv pip install -r requirements.txt
```
*(Or use standard `pip` if `uv` is not installed)*

### 2. Environment Configuration
Copy the template and replace it with your local credentials (DB password, secrets, etc.):
```bash
copy .env.example .env
```

### 3. Load Schema & Seed Data
Initialize your MySQL database using the seeding script:
```bash
mysql -u root -p < sql/seed.sql
```

### 4. Run the Servers
Start the backend API server:
```bash
uv run python run_api.py
```
In a new terminal window, start the frontend UI launcher:
```bash
uv run python run_ui.py
```

### 5. Access the Application
* **Web UI**: [http://127.0.0.1:5000](http://127.0.0.1:5000)
* **FastAPI Docs (Swagger)**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)


