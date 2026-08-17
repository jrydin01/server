import os
import uuid
import json
import base64
import requests
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Configuration from Environment Variables
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
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    # For GET, we don't send a JSON body. For PUT, we do.
    if method == "GET":
        response = requests.get(url, headers=headers)
    else:
        response = requests.request(method, url, headers=headers, json=data)
    return response

def get_file_sha(path: str):
    response = github_request("GET", path)
    if response.status_code == 200:
        return response.json().get("sha")
    return None

def load_tracks_from_github() -> List[dict]:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("⚠️ GitHub Token or Repo not configured. Returning empty track list.")
        return []
    
    response = github_request("GET", "tracks.json")
    if response.status_code == 200:
        content_encoded = response.json()["content"]
        content = base64.b64decode(content_encoded).decode("utf-8")
        return json.loads(content)
    elif response.status_code == 404:
        return []
    else:
        print(f"❌ Error loading tracks from GitHub: {response.status_code} {response.text}")
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
    
    # Check if file exists to get SHA (though filenames are unique UUIDs)
    sha = get_file_sha(path)
    
    data = {
        "message": f"Upload {filename}",
        "content": encoded_content,
        "branch": GITHUB_BRANCH
    }
    if sha:
        data["sha"] = sha
    
    response = github_request("PUT", path, data)
    if response.status_code in [200, 201]:
        return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{path}"
    else:
        raise Exception(f"GitHub Upload Failed: {response.status_code} {response.text}")

@app.get("/")
async def root():
    return {
        "status": "GitHub Storage Server Active", 
        "repo": GITHUB_REPO,
        "configured": bool(GITHUB_TOKEN and GITHUB_REPO)
    }

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
        raise HTTPException(status_code=500, detail="GitHub Storage not configured on server")

    track_id = str(uuid.uuid4())
    file_ext = os.path.splitext(file.filename)[1]
    
    # 1. Upload Music File to GitHub
    file_bytes = await file.read()
    audio_url = upload_to_github(file_bytes, f"{track_id}{file_ext}", "music")
    
    # 2. Add to Metadata and save back to GitHub
    new_track = {
        "id": track_id,
        "title": title,
        "artist": artist,
        "audioUrl": audio_url,
        "coverUrl": f"https://picsum.photos/id/{(hash(track_id) % 100) + 100}/400/400"
    }
    
    tracks = load_tracks_from_github()
    tracks.append(new_track)
    save_tracks_to_github(tracks)
    
    return new_track

if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Teen Music Streamer Server starting...")
    print(f"📦 Backend: GitHub Repository ({GITHUB_REPO})")
    uvicorn.run(app, host="0.0.0.0", port=8000)
