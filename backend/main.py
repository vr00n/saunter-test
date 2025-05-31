import os
import uuid
import requests
import json
import base64
import io
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from dateutil import parser

# Load environment variables
load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://vr00n.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GitHub API URL and credentials from environment variables
GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")

# Validate required environment variables
if not all([GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO]):
    raise ValueError("Missing required environment variables: GITHUB_TOKEN, GITHUB_OWNER, or GITHUB_REPO")

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def upload_to_github(content, path):
    """Upload content to GitHub"""
    content_base64 = base64.b64encode(content).decode("utf-8")
    url = GITHUB_API_URL.format(owner=GITHUB_OWNER, repo=GITHUB_REPO, path=path)
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "message": f"Upload {path}",
        "content": content_base64,
    }
    response = requests.put(url, headers=headers, data=json.dumps(data))
    return response.status_code == 201 or response.status_code == 200

def get_from_github(path):
    """Get content from GitHub"""
    url = GITHUB_API_URL.format(owner=GITHUB_OWNER, repo=GITHUB_REPO, path=path)
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
    }
    try:
        print(f"Fetching from GitHub: {path}")
        response = requests.get(url, headers=headers)
        print(f"GitHub API response status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                content_data = response.json()
                if 'content' not in content_data:
                    print(f"No content field in GitHub response: {content_data}")
                    return None
                    
                # GitHub API returns content in base64, but it might be encoded with newlines
                content = content_data['content'].replace('\n', '')
                print(f"Decoding base64 content of length: {len(content)}")
                decoded_content = base64.b64decode(content)
                print(f"Successfully decoded content of size: {len(decoded_content)} bytes")
                return decoded_content
            except json.JSONDecodeError as e:
                print(f"Failed to parse GitHub response as JSON: {str(e)}")
                print(f"Response text: {response.text[:200]}...")  # Print first 200 chars
                return None
            except base64.binascii.Error as e:
                print(f"Failed to decode base64 content: {str(e)}")
                return None
                
        print(f"GitHub API error: {response.status_code} - {response.text}")
        return None
    except Exception as e:
        print(f"Error fetching from GitHub: {str(e)}")
        return None

@app.post('/upload_audio')
async def upload_audio(audio: UploadFile = File(...), locations: str = Form(...)):
    try:
        rec_id = str(uuid.uuid4())
        audio_path = f"recordings/{rec_id}.webm"
        loc_path = f"recordings/{rec_id}.json"
        
        # Upload audio to GitHub
        audio_content = await audio.read()
        print(f"Uploading audio file of size: {len(audio_content)} bytes")
        if not upload_to_github(audio_content, audio_path):
            print(f"Failed to upload audio to {audio_path}")
            return JSONResponse({"error": "Failed to upload audio"}, status_code=500)
        print(f"Successfully uploaded audio to {audio_path}")
        
        # Upload locations to GitHub
        if not upload_to_github(locations.encode('utf-8'), loc_path):
            print(f"Failed to upload locations to {loc_path}")
            return JSONResponse({"error": "Failed to upload locations"}, status_code=500)
        print(f"Successfully uploaded locations to {loc_path}")
        
        return {"link": f"/play/{rec_id}"}
    except Exception as e:
        print(f"Error in upload_audio: {str(e)}")
        return JSONResponse({"error": f"Upload failed: {str(e)}"}, status_code=500)

@app.get('/list_recordings')
def list_recordings():
    url = GITHUB_API_URL.format(owner=GITHUB_OWNER, repo=GITHUB_REPO, path="recordings")
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
    }
    response = requests.get(url, headers=headers)
    recs = []
    if response.status_code == 200:
        files = response.json()
        for file in files:
            if file['name'].endswith('.webm') or file['name'].endswith('.mp4') or file['name'].endswith('.wav'):
                rec_id = file['name'].rsplit('.', 1)[0]
                # Fetch commit info for timestamp
                commit_url = file.get('git_url')
                timestamp = None
                if commit_url:
                    commit_resp = requests.get(commit_url, headers=headers)
                    if commit_resp.status_code == 200:
                        commit_data = commit_resp.json()
                        # Use the committer date as the upload timestamp
                        timestamp_str = commit_data.get('committer', {}).get('date')
                        if timestamp_str:
                            dt = parser.isoparse(timestamp_str)
                            timestamp = int(dt.timestamp() * 1000)  # ms since epoch
                recs.append({
                    'name': f'Recording {rec_id[:8]}',
                    'link': f'/play/{rec_id}',
                    'timestamp': timestamp
                })
    return recs

@app.get('/play/{rec_id}', response_class=HTMLResponse)
def play_recording(request: Request, rec_id: str):
    if rec_id == "record.html":
        return RedirectResponse(url="/record.html")
    return templates.TemplateResponse('play.html', {"request": request, "rec_id": rec_id})

@app.get('/audio/{rec_id}')
def get_audio(rec_id: str):
    try:
        print(f"Fetching audio for recording {rec_id}")
        # Try all supported extensions
        for ext, mime in [("webm", "audio/webm;codecs=opus"), ("mp4", "audio/mp4"), ("wav", "audio/wav")]:
            audio_path = f"recordings/{rec_id}.{ext}"
            audio_content = get_from_github(audio_path)
            if audio_content:
                print(f"Successfully retrieved audio content of size: {len(audio_content)} bytes and type: {mime}")
                audio_io = io.BytesIO(audio_content)
                audio_io.seek(0)
                return StreamingResponse(
                    audio_io,
                    media_type=mime,
                    headers={"Content-Disposition": f"attachment; filename={rec_id}.{ext}"}
                )
        print(f"Audio content not found for {rec_id}")
        return JSONResponse(
            {"error": "Audio not found. Please check if the recording exists."}, 
            status_code=404
        )
    except Exception as e:
        print(f"Error serving audio for {rec_id}: {str(e)}")
        return JSONResponse(
            {"error": f"Error serving audio: {str(e)}"}, 
            status_code=500
        )

@app.get('/locations/{rec_id}')
def get_locations(rec_id: str):
    try:
        print(f"Fetching locations for recording {rec_id}")
        locations_content = get_from_github(f"recordings/{rec_id}.json")
        if locations_content:
            print(f"Successfully retrieved locations content of size: {len(locations_content)} bytes")
            return JSONResponse(content=locations_content.decode('utf-8'))
        print(f"Locations content not found for {rec_id}")
        return JSONResponse({"error": "Locations not found. Please check if the recording exists."}, status_code=404)
    except Exception as e:
        print(f"Error serving locations for {rec_id}: {str(e)}")
        return JSONResponse({"error": f"Error serving locations: {str(e)}"}, status_code=500)

@app.get("/record.html", response_class=HTMLResponse)
def record(request: Request):
    return templates.TemplateResponse("record.html", {"request": request})
