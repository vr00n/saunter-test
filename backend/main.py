import os
import uuid
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
templates = Jinja2Templates(directory="templates")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_AUDIO_DIR = 'uploads/audio'
UPLOAD_LOC_DIR = 'uploads/locations'
os.makedirs(UPLOAD_AUDIO_DIR, exist_ok=True)
os.makedirs(UPLOAD_LOC_DIR, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post('/upload_audio')
async def upload_audio(audio: UploadFile = File(...), locations: str = Form(...)):
    rec_id = str(uuid.uuid4())
    audio_path = os.path.join(UPLOAD_AUDIO_DIR, f'{rec_id}.webm')
    loc_path = os.path.join(UPLOAD_LOC_DIR, f'{rec_id}.json')
    with open(audio_path, 'wb') as f:
        f.write(await audio.read())
    with open(loc_path, 'w') as f:
        f.write(locations)
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

@app.get('/play/{rec_id}', response_class=HTMLResponse)
def play_recording(request: Request, rec_id: str):
    return templates.TemplateResponse('play.html', {"request": request, "rec_id": rec_id})

@app.get('/audio/{rec_id}')
def get_audio(rec_id: str):
    audio_path = os.path.join(UPLOAD_AUDIO_DIR, f'{rec_id}.webm')
    if not os.path.exists(audio_path):
        return JSONResponse({"error": "Audio not found"}, status_code=404)
    return FileResponse(audio_path, media_type='audio/webm')

@app.get('/locations/{rec_id}')
def get_locations(rec_id: str):
    loc_path = os.path.join(UPLOAD_LOC_DIR, f'{rec_id}.json')
    if not os.path.exists(loc_path):
        return JSONResponse({"error": "Locations not found"}, status_code=404)
    with open(loc_path) as f:
        data = f.read()
    return JSONResponse(content=data)
