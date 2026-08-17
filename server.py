import os
import uuid
import json
import base64
import requests
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Metadata library for album art extraction
try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, APIC
    HAS_MUTAGEN = True
except ImportError:
    HAS_MUTAGEN = False

# Configuration from Environment Variables
def load_env():
    env_path = os.path.join(os.path.dirname(__file__), "config.env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

load_env()
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")  # Format: "username/repo"
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Track(BaseModel):
    id: str
    title: str
    artist: str
    audioUrl: str
    coverUrl: str = ""

def github_request(method: str, path: str, data: dict = None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    # Using 'Bearer' instead of 'token' which is the modern standard for GitHub API
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "TeenMusicStreamer-Server"
    }
    if method == "GET":
        response = requests.get(url, headers=headers)
    else:
        response = requests.request(method, url, headers=headers, json=data)
    
    if response.status_code == 401:
        print(f"❌ GitHub Authorization Failed (401). Check if your GITHUB_TOKEN is correct and has 'repo' permissions.")
        print(f"Response: {response.text}")
    
    return response

def get_file_sha(path: str):
    response = github_request("GET", path)
    if response.status_code == 200:
        return response.json().get("sha")
    return None

def load_tracks_from_github() -> List[dict]:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return []
    response = github_request("GET", "tracks.json")
    if response.status_code == 200:
        content_encoded = response.json()["content"]
        content = base64.b64decode(content_encoded).decode("utf-8")
        return json.loads(content)
    return []

def save_tracks_to_github(tracks: List[dict]):
    content = json.dumps(tracks, indent=4)
    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
    sha = get_file_sha("tracks.json")
    data = {
        "message": "Update tracks metadata",
        "content": encoded_content,
        "branch": GITHUB_BRANCH
    }
    if sha:
        data["sha"] = sha
    github_request("PUT", "tracks.json", data)

def upload_to_github(file_data: bytes, filename: str, folder: str) -> str:
    path = f"{folder}/{filename}"
    encoded_content = base64.b64encode(file_data).decode("utf-8")
    data = {
        "message": f"Upload {filename}",
        "content": encoded_content,
        "branch": GITHUB_BRANCH
    }
    response = github_request("PUT", path, data)
    if response.status_code in [200, 201]:
        return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{path}"
    else:
        raise Exception(f"GitHub Upload Failed: {response.status_code}")

def extract_album_art_bytes(file_path):
    if not HAS_MUTAGEN:
        return None
    try:
        audio = MP3(file_path, ID3=ID3)
        if audio.tags:
            for tag in audio.tags.values():
                if tag.__class__.__name__ == 'APIC':
                    return tag.data
    except:
        pass
    return None

@app.get("/")
async def root():
    return {"status": "Active", "storage": "GitHub", "repo": GITHUB_REPO}

@app.get("/tracks", response_model=List[Track])
async def get_tracks():
    return load_tracks_from_github()

@app.post("/upload")
async def upload_track(
    title: str = Form(...),
    artist: str = Form(...),
    file: UploadFile = File(...)
):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        raise HTTPException(status_code=500, detail="GitHub not configured")

    track_id = str(uuid.uuid4())
    file_ext = os.path.splitext(file.filename)[1]
    temp_path = f"temp_{track_id}{file_ext}"
    
    file_bytes = await file.read()
    with open(temp_path, "wb") as f:
        f.write(file_bytes)

    # 1. Upload Music to GitHub
    audio_url = upload_to_github(file_bytes, f"{track_id}{file_ext}", "music")
    
    # 2. Extract and Upload Album Art to GitHub
    cover_url = ""
    art_bytes = extract_album_art_bytes(temp_path)
    if art_bytes:
        cover_url = upload_to_github(art_bytes, f"{track_id}.jpg", "covers")
    
    os.remove(temp_path)

    # 3. Save Metadata
    new_track = {
        "id": track_id,
        "title": title,
        "artist": artist,
        "audioUrl": audio_url,
        "coverUrl": cover_url
    }
    
    tracks = load_tracks_from_github()
    tracks.append(new_track)
    save_tracks_to_github(tracks)
    
    return new_track

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
