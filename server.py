import os
import uuid
import json
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Metadata library for album art extraction
try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC
    HAS_MUTAGEN = True
except ImportError:
    MP3 = None
    ID3 = None
    APIC = None
    HAS_MUTAGEN = False

app = FastAPI(title="Teen Music Streamer API (Self-Hosted)")

# CORS configuration to allow connections from mobile and desktop apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Local Storage Configuration
MUSIC_DIR = "music"
COVERS_DIR = "covers"
METADATA_FILE = "tracks.json"

# Ensure directories exist
for d in [MUSIC_DIR, COVERS_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

class Track(BaseModel):
    """Data model representing a single music track."""
    id: str
    title: str
    artist: str
    audioUrl: str
    coverUrl: str = ""

def load_tracks() -> List[dict]:
    """Loads track metadata from the local tracks.json file."""
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_tracks(tracks: List[dict]):
    """Saves the track list to the local tracks.json file."""
    with open(METADATA_FILE, "w") as f:
        json.dump(tracks, f, indent=4)

def extract_album_art(file_path: str, track_id: str) -> str:
    """
    Extracts album art from an MP3 file and saves it locally.
    Returns the relative URL path to the image.
    """
    if not HAS_MUTAGEN:
        return ""
    try:
        audio = MP3(file_path, ID3=ID3)
        if audio.tags:
            for tag in audio.tags.values():
                if isinstance(tag, APIC):
                    cover_filename = f"{track_id}.jpg"
                    cover_path = os.path.join(COVERS_DIR, cover_filename)
                    with open(cover_path, "wb") as f:
                        f.write(tag.data)
                    return f"/covers/{cover_filename}"
    except Exception as e:
        print(f"⚠️ Art extraction failed: {e}")
    return ""

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "Self-Hosted Server Active", "storage": "Local Disk"}

@app.get("/tracks", response_model=List[Track])
async def get_tracks():
    """Returns the list of all music tracks stored on this server."""
    return load_tracks()

@app.post("/upload")
async def upload_track(
    title: str = Form(...),
    artist: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Handles music track uploads.
    Saves the file to the local 'music' directory and extracts album art.
    """
    try:
        track_id = str(uuid.uuid4())
        file_ext = os.path.splitext(file.filename)[1]
        filename = f"{track_id}{file_ext}"
        file_path = os.path.join(MUSIC_DIR, filename)

        # Save audio file locally
        with open(file_path, "wb") as f:
            f.write(await file.read())

        # Extract and save album art
        cover_url = extract_album_art(file_path, track_id)

        new_track = {
            "id": track_id,
            "title": title,
            "artist": artist,
            "audioUrl": f"/music/{filename}",
            "coverUrl": cover_url
        }

        tracks = load_tracks()
        tracks.append(new_track)
        save_tracks(tracks)
        
        return new_track
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Mount static directories so files can be accessed via URL
app.mount("/music", StaticFiles(directory=MUSIC_DIR), name="music")
app.mount("/covers", StaticFiles(directory=COVERS_DIR), name="covers")

if __name__ == "__main__":
    import uvicorn
    # 0.0.0.0 allows connections from other devices on your local network (like your phone)
    print("🚀 Teen Music Streamer (Self-Hosted) starting...")
    print("📍 Local Access: http://localhost:8000")
    print("📱 Network Access: Check your Mac's System Settings > Network for your IP address")
    uvicorn.run(app, host="0.0.0.0", port=8000)
