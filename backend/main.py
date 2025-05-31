import re
import json
import os
import uuid
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from youtube_transcript_api import YouTubeTranscriptApi
import spacy
from geopy.geocoders import Nominatim

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Load spaCy model once
nlp = spacy.load("en_core_web_sm")
geolocator = Nominatim(user_agent="yt-map-app")

UPLOAD_AUDIO_DIR = 'uploads/audio'
UPLOAD_LOC_DIR = 'uploads/locations'
os.makedirs(UPLOAD_AUDIO_DIR, exist_ok=True)
os.makedirs(UPLOAD_LOC_DIR, exist_ok=True)

def extract_locations(text):
    doc = nlp(text)
    locations = [ent.text for ent in doc.ents if ent.label_ in ["GPE", "LOC", "FAC"]]
    return locations

def geocode_location(location):
    try:
        geo = geolocator.geocode(location)
        if geo:
            return (geo.latitude, geo.longitude)
    except Exception:
        pass
    return None

def parse_youtube_id(url):
    # Handles various YouTube URL formats
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else None

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/process", response_class=JSONResponse)
async def process(request: Request, youtube_url: str = Form(...)):
    video_id = parse_youtube_id(youtube_url)
    if not video_id:
        return JSONResponse({"error": "Invalid YouTube URL"}, status_code=400)
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
    except Exception as e:
        return JSONResponse({"error": f"Could not fetch transcript: {e}"}, status_code=400)
    path = []
    print("---- Transcript Location Extraction Log ----")
    for entry in transcript:
        text = entry['text']
        ts = entry['start']
        print(f"[{ts:.1f}s] Transcript: {text}")
        locations = extract_locations(text)
        print(f"  Extracted locations: {locations}")
        for loc in locations:
            coords = geocode_location(loc)
            if coords:
                print(f"    Geocoded '{loc}' to {coords}")
                path.append({
                    "timestamp": ts,
                    "lat": coords[0],
                    "lon": coords[1],
                    "place": loc
                })
            else:
                print(f"    Failed to geocode '{loc}'")
    # Remove duplicates and sort by timestamp
    unique_path = sorted(path, key=lambda p: p['timestamp'])

    # --- Filter out parent locations if a more specific one is present nearby ---
    filtered_path = []
    i = 0
    while i < len(unique_path):
        curr = unique_path[i]
        # Look ahead to next location
        if i + 1 < len(unique_path):
            next_ = unique_path[i+1]
            # If next is within 3s and is a parent of curr, skip next
            if 0 <= next_['timestamp'] - curr['timestamp'] <= 3:
                # Use geopy address to check if next is a parent of curr
                try:
                    curr_addr = geolocator.reverse((curr['lat'], curr['lon']), language='en', exactly_one=True, timeout=10)
                    next_addr = geolocator.reverse((next_['lat'], next_['lon']), language='en', exactly_one=True, timeout=10)
                    if curr_addr and next_addr and next_['place'].lower() in curr_addr.address.lower():
                        filtered_path.append(curr)
                        i += 2
                        continue
                except Exception:
                    pass
        filtered_path.append(curr)
        i += 1
    print("Filtered path:", filtered_path)
    print("---- End of Log ----")
    return JSONResponse({
        "video_id": video_id,
        "path": filtered_path
    })

@app.post('/upload_audio')
async def upload_audio(audio: UploadFile = File(...), locations: str = Form(...)):
    rec_id = str(uuid.uuid4())
    audio_path = os.path.join(UPLOAD_AUDIO_DIR, f'{rec_id}.webm')
    loc_path = os.path.join(UPLOAD_LOC_DIR, f'{rec_id}.json')
    with open(audio_path, 'wb') as f:
        f.write(await audio.read())
    with open(loc_path, 'w') as f:
        f.write(locations)
    # Return a link to a placeholder playback page
    return {"link": f"/play/{rec_id}"}

@app.get('/list_recordings')
def list_recordings():
    recs = []
    for fname in os.listdir(UPLOAD_AUDIO_DIR):
        if fname.endswith('.webm'):
            rec_id = fname[:-5]
            recs.append({
                'name': f'Recording {rec_id[:8]}',
                'link': f'/play/{rec_id}'
            })
    return recs

@app.get('/play/{rec_id}')
def play_recording(request: Request, rec_id: str):
    # Placeholder page for now
    return templates.TemplateResponse('play_placeholder.html', {"request": request, "rec_id": rec_id})
