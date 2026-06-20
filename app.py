import os
import sys
import uuid
import threading
import subprocess
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_file
import yt_dlp

app = Flask(__name__)

BASE_DIR   = Path(__file__).parent
WORK_DIR   = BASE_DIR / "temp_work"
OUTPUT_DIR = Path.home() / "Downloads"
WORK_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

jobs: dict[str, dict] = {}


def find_ffmpeg():
    import shutil as _sh
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).exists():
            return str(exe), str(Path(exe).parent)
    except Exception:
        pass
    found = _sh.which("ffmpeg")
    if found:
        return str(found), str(Path(found).parent)
    for c in [r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]:
        if Path(c).exists():
            return c, str(Path(c).parent)
    return None, None


FFMPEG_EXE, FFMPEG_DIR = find_ffmpeg()


def update_job(job_id, **kwargs):
    jobs[job_id].update(kwargs)


def run_ffmpeg(*args, **kwargs):
    return subprocess.run([FFMPEG_EXE or "ffmpeg", *args], **kwargs)


def separate_vocals(audio_wav: Path, out_dir: Path) -> Path:
    """
    Run Demucs vocal separation by calling it as a Python library directly,
    bypassing torchaudio.load() entirely by pre-loading with soundfile.
    """
    import torch
    import soundfile as sf
    import numpy as np
    from demucs.pretrained import get_model
    from demucs.apply import apply_model

    # Load audio with soundfile (no torchaudio needed)
    data, samplerate = sf.read(str(audio_wav), dtype="float32", always_2d=True)
    # soundfile gives (samples, channels) — torch wants (batch, channels, samples)
    wav = torch.from_numpy(data.T).unsqueeze(0)  # (1, C, T)

    # Load the htdemucs model
    model = get_model("htdemucs")
    model.eval()

    # Resample if needed
    if samplerate != model.samplerate:
        import torchaudio.functional as F
        wav = F.resample(wav, samplerate, model.samplerate)

    # Match model's expected channel count
    if wav.shape[1] == 1 and model.audio_channels == 2:
        wav = wav.repeat(1, 2, 1)
    elif wav.shape[1] == 2 and model.audio_channels == 1:
        wav = wav.mean(dim=1, keepdim=True)

    # Run separation
    with torch.no_grad():
        sources = apply_model(model, wav, device="cpu", progress=False)
    # sources shape: (batch, stems, channels, time)
    # stems order from model.sources e.g. ['drums','bass','other','vocals']
    stem_names = model.sources
    vocals_idx = stem_names.index("vocals")
    vocals = sources[0, vocals_idx]  # (channels, time)

    # Save vocals as WAV using soundfile
    vocals_wav = out_dir / "vocals.wav"
    vocals_np = vocals.numpy().T  # (time, channels)
    sf.write(str(vocals_wav), vocals_np, model.samplerate)
    return vocals_wav


def process_video(job_id: str, url: str):
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    output_filename = "video_vocals_only.mp4"

    try:
        if not FFMPEG_EXE:
            raise EnvironmentError("ffmpeg not found. Run: pip install imageio-ffmpeg")

        # 1. Download
        update_job(job_id, status="downloading", progress=10,
                   message="Downloading video\u2026")
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(job_dir / "original.%(ext)s"),
            "ffmpeg_location": FFMPEG_DIR,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "video").strip()
            safe_title = "".join(
                c for c in title if c.isalnum() or c in " _-"
            ).strip() or "video"

        original = next(job_dir.glob("original.*"), None)
        if not original:
            raise FileNotFoundError("Download failed.")

        update_job(job_id, progress=30, message="Video downloaded. Extracting audio\u2026")

        # 2. Extract audio as WAV via ffmpeg
        audio_wav = job_dir / "audio.wav"
        run_ffmpeg("-y", "-i", str(original),
                   "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                   str(audio_wav),
                   check=True, capture_output=True)

        update_job(job_id, progress=45,
                   message="Running AI vocal separation \u2014 may take a few minutes\u2026")

        # 3. Separate vocals (pure Python, no torchaudio.load)
        vocals_dir = job_dir / "vocals"
        vocals_dir.mkdir(exist_ok=True)
        vocals_wav = separate_vocals(audio_wav, vocals_dir)

        update_job(job_id, progress=75, message="Vocals isolated. Merging back into video\u2026")

        # 4. Mux
        output_filename = f"{safe_title}_vocals_only.mp4"
        output_path = OUTPUT_DIR / output_filename
        run_ffmpeg("-y",
                   "-i", str(original),
                   "-i", str(vocals_wav),
                   "-map", "0:v:0",
                   "-map", "1:a:0",
                   "-c:v", "copy",
                   "-c:a", "aac", "-b:a", "192k",
                   "-shortest",
                   str(output_path),
                   check=True, capture_output=True)

        update_job(job_id, progress=95, message="Finalising\u2026")

    except Exception as exc:
        update_job(job_id, status="error", progress=0, message=f"Error: {exc}")
        return
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)

    update_job(job_id, status="done", progress=100,
               message="Done! File saved to your Downloads folder.",
               filename=output_filename,
               filepath=str(output_path))


@app.route("/")
def index():
    return (BASE_DIR / "index.html").read_text(encoding="utf-8")


@app.route("/debug")
def debug():
    import shutil as _sh
    lines = [
        f"Python: {sys.executable}",
        f"FFMPEG_EXE: {FFMPEG_EXE}",
    ]
    for pkg in ("torch", "torchaudio", "demucs", "soundfile", "imageio_ffmpeg"):
        try:
            m = __import__(pkg)
            lines.append(f"{pkg}: {getattr(m, '__version__', 'ok')}")
        except ImportError as e:
            lines.append(f"{pkg}: MISSING — {e}")
    return "<pre>" + "\n".join(lines) + "</pre>"


@app.route("/api/start", methods=["POST"])
def start():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify(error="No URL provided"), 400
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "progress": 0, "message": "Queued\u2026"}
    threading.Thread(target=process_video, args=(job_id, url), daemon=True).start()
    return jsonify(job_id=job_id)


@app.route("/api/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify(error="Unknown job"), 404
    return jsonify(job)


@app.route("/api/download/<job_id>")
def download(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        return jsonify(error="Not ready"), 400
    return send_file(job["filepath"], as_attachment=True,
                     download_name=job["filename"])


if __name__ == "__main__":
    print(f"[{'OK' if FFMPEG_EXE else '!!'}] FFmpeg: {FFMPEG_EXE or 'NOT FOUND'}")
    print("     Diagnostics: http://localhost:5000/debug")
    app.run(debug=True, port=5000)