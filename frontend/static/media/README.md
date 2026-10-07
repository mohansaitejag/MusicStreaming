# Media Drop Folder

Add real media files here and control display order in `manifest.json`.

## 1) Song cover images
- Put image files in `song-covers/`
- Example names: `1.jpg`, `2.jpg`, `3.jpg`
- In `manifest.json`, list files in the exact order you want them used.
- Mapping rule in UI:
  - song with `song_id = 1` uses the first image in `songCovers`
  - song with `song_id = 2` uses the second image
  - if songs are more than images, it wraps around

## 2) Artist photos
- Put image files in `artist-photos/`
- List them in `artistPhotos` in `manifest.json`
- Artist names are hashed to this list, so the same artist keeps the same photo consistently.

## 3) Test audio
- Put one or more audio files in `audio/`
- Recommended format: `.mp3`
- Add file paths to `testAudios` in `manifest.json`
- Current behavior: the first file in `testAudios` is played for every song when Play is clicked.

## Path format for manifest
Use absolute static paths like:
- `/static/media/song-covers/1.jpg`
- `/static/media/artist-photos/1.jpg`
- `/static/media/audio/test.mp3`

If a media file is missing, the UI falls back to built-in placeholder art/audio behavior.
