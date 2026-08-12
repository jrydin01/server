import os
import uuid
import json
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Metadata library
try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MUSIC_DIR = "music"
COVERS_DIR = "covers"
METADATA_FILE = "tracks.json"

for d in [MUSIC_DIR, COVERS_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

class Track(BaseModel):
    id: str
    title: str
    artist: str
    audioUrl: str
    coverUrl: str = ""

def load_tracks():
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_tracks(tracks):
    with open(METADATA_FILE, "w") as f:
        json.dump(tracks, f, indent=4)

def extract_album_art(file_path, track_id):
    if not HAS_MUTAGEN:
        return ""
    try:
        audio = MP3(file_path, ID3=ID3)
        if audio.tags:
            for tag in audio.tags.values():
                if tag.__class__.__name__ == 'APIC':
                    cover_filename = f"{track_id}.jpg"
                    cover_path = os.path.join(COVERS_DIR, cover_filename)
                    with open(cover_path, "wb") as f:
                        f.write(tag.data)
                    return f"/covers/{cover_filename}"
    except:
        pass
    return ""

@app.get("/")
async def root():
    return {"message": "Server is Running"}

@app.get("/tracks")
async def get_tracks():
    return load_tracks()

@app.post("/upload")
async def upload_track(
    title: str = Form(...),
    artist: str = Form(...),
    file: UploadFile = File(...)
):
    track_id = str(uuid.uuid4())
    file_ext = os.path.splitext(file.filename)[1]
    filename = f"{track_id}{file_ext}"
    file_path = os.path.join(MUSIC_DIR, filename)

    with open(file_path, "wb") as f:
        f.write(await file.read())

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

app.mount("/music", StaticFiles(directory=MUSIC_DIR), name="music")
app.mount("/covers", StaticFiles(directory=COVERS_DIR), name="covers")

if __name__ == "__main__":
    import uvicorn
    # Listen on all interfaces (0.0.0.0) so the VS Code tunnel can reach it
    print(f"Server starting on http://0.0.0.0:8000. Mutagen: {HAS_MUTAGEN}")
    uvicorn.run(app, host="0.0.0.0", port=8000)
