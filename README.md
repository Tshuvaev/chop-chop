# Slicer MVP

Slicer is a full-stack MVP web app that extracts audio samples from YouTube videos.

Workflow:

1. Paste YouTube URL
2. Analyze audio with AI onset segmentation
3. Edit detected sample start/end points
4. Export WAV samples as ZIP

## Tech Stack

- Backend: Python + FastAPI
- Audio: yt-dlp, ffmpeg, librosa, numpy, pydub, soundfile
- Frontend: React + Vite + TailwindCSS

## Project Structure

```text
slicer/
  backend/
    main.py
    routes.py
    models/
      sample.py
    services/
      ai_segmenter.py
      audio_processor.py
      exporter.py
      session_store.py
      youtube_downloader.py
    utils/
      cleanup.py
      config.py
  frontend/
    index.html
    package.json
    postcss.config.js
    tailwind.config.js
    vite.config.js
    src/
      App.jsx
      index.css
      main.jsx
      components/
        SampleRow.jsx
        Spinner.jsx
  storage/
    downloads/
    samples/
    exports/
  requirements.txt
  README.md
```

## Prerequisites

1. Python 3.11+
2. Node.js 20+
3. FFmpeg installed and available in PATH

### Install FFmpeg

#### Windows

- Download FFmpeg build from: https://www.gyan.dev/ffmpeg/builds/
- Extract and add `ffmpeg/bin` to system PATH
- Verify:

```bash
ffmpeg -version
```

#### macOS

```bash
brew install ffmpeg
ffmpeg -version
```

#### Ubuntu/Debian

```bash
sudo apt update
sudo apt install -y ffmpeg
ffmpeg -version
```

## Backend Setup

From project root `slicer/`:

```bash
python -m venv .venv
```

Activate venv:

- Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

- macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run backend:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API base URL: `http://localhost:8000`

## Frontend Setup

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend URL: `http://localhost:5173`

The frontend calls backend at `http://localhost:8000` by default.

Optional override:

```bash
# frontend/.env
VITE_API_BASE_URL=http://localhost:8000
```

## API Endpoints

### `POST /analyze`

Request:

```json
{
  "url": "https://www.youtube.com/watch?v=..."
}
```

Response:

```json
{
  "session_id": "...",
  "title": "Video Title",
  "duration": 123.45,
  "audio_url": "/session/<session_id>/audio",
  "segments": [
    {
      "id": 1,
      "name": "sample_001",
      "start": 34.2,
      "end": 38.1
    }
  ]
}
```

### `POST /export`

Request:

```json
{
  "segments": [
    {
      "id": 1,
      "name": "sample_001",
      "start": 34.2,
      "end": 38.1
    }
  ]
}
```

Response:

```json
{
  "download_url": "/download/<session_id>/sample_pack.zip",
  "file_name": "sample_pack.zip"
}
```

### `GET /download/{file}`

Downloads exported ZIP.

## Validation and Error Handling

Handled cases:

- Invalid YouTube URL
- Video longer than 30 minutes
- YouTube download failures
- ffmpeg missing or conversion failures
- Segmentation failures
- Invalid segment ranges during export

API returns clear JSON errors via `detail` field.

## Background Tasks and Cleanup

- Storage directories are auto-created
- Background cleanup runs:
  - periodically (every 5 minutes)
  - after analyze/export requests
- Files and session state older than 30 minutes are deleted

## Notes

- Anonymous mode (no accounts)
- One video per session (new analysis in same session replaces previous files)
- Output samples are WAV 48kHz / 24-bit PCM (`pcm_s24le`)

