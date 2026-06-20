# HalalClip — Setup & Run Guide

## What it does
Paste any video URL → the app downloads it, uses AI (Spleeter) to strip all
instrumental music, keeps only vocals/speech, and saves the result to your
Downloads folder.  100% free. Everything runs locally on your machine.

---

## Prerequisites

### 1. Python 3.9+
Check: `python3 --version`

### 2. FFmpeg  (required by yt-dlp and Spleeter)

| OS      | Command |
|---------|---------|
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| macOS   | `brew install ffmpeg` |
| Windows | Download from https://ffmpeg.org/download.html and add to PATH |

---

## Installation

```bash
# 1. Clone / download this folder, then enter it
cd halal_video

# 2. Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# NOTE: Spleeter downloads its AI model (~130 MB) on first use automatically.
```

---

## Running the app

```bash
# Make sure venv is active, then:
python app.py
```

Open your browser and go to:  **http://localhost:5000**

---

## Usage

1. Copy a video URL (YouTube, Instagram, TikTok, Twitter/X, Facebook, etc.)
2. Paste it into the input box and click **Remove Music**
3. Wait — the progress bar shows each step (download → AI separation → mux)
4. The finished file appears in your **Downloads** folder as `<title>_vocals_only.mp4`

---

## How it works (tech stack)

| Component | Library | Cost |
|-----------|---------|------|
| Web UI    | Flask (Python) | Free |
| Video download | yt-dlp | Free / open-source |
| Vocal separation | Spleeter (Deezer) | Free / open-source |
| Audio/video mux | FFmpeg | Free / open-source |

**Spleeter** uses a pre-trained deep learning model to separate a mixed audio
track into two stems: `vocals` and `accompaniment`. We keep only the `vocals`
stem and replace the original audio in the video file.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ffmpeg not found` | Install FFmpeg and ensure it's on your PATH |
| `spleeter: command not found` | Make sure venv is active; re-run `pip install spleeter` |
| Download fails for a URL | Update yt-dlp: `pip install -U yt-dlp` |
| First run is slow | Spleeter downloads the AI model (~130 MB) once on first use |
| Port 5000 in use | Change the port in the last line of `app.py` |

---

## Notes

- **Privacy**: Nothing is uploaded to any server. All processing happens on your machine.
- **Output location**: Files are saved to `~/Downloads/` by default. Change `OUTPUT_DIR` in `app.py` if needed.
- **Temp files**: Cleaned up automatically after each job.
