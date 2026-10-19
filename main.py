import os
import logging
import json
import urllib.request
import urllib.error
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, FileResponse
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dental_transcriptor")

app = FastAPI(title="DentiVoice")
MAX_AUDIO_BYTES = 25 * 1024 * 1024

@app.get("/", response_class=HTMLResponse)
async def home():
    with open("index.html", "r", encoding="utf-8") as page:
        return page.read()

@app.get("/favicon.svg")
async def favicon():
    return FileResponse("favicon.svg", media_type="image/svg+xml")

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/save-transcript")
async def save_transcript(payload: dict):
    transcript = str(payload.get("transcript", "")).strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="No hay una transcripción para guardar.")
    if len(transcript) > 50000:
        raise HTTPException(status_code=413, detail="La transcripción supera el límite permitido.")

    sheets_url = os.getenv("GOOGLE_SHEETS_WEB_APP_URL")
    sheets_secret = os.getenv("GOOGLE_SHEETS_SHARED_SECRET")
    if not sheets_url or not sheets_secret:
        raise HTTPException(status_code=503, detail="La conexión con Google Sheets todavía no está configurada.")

    body = json.dumps({"secret": sheets_secret, "transcript": transcript}).encode("utf-8")
    request = urllib.request.Request(
        sheets_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "Google Sheets no pudo guardar el dictado."))
        return {"ok": True, "message": "Dictado guardado en Google Sheets."}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Google Sheets save error (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="No fue posible guardar el dictado en Google Sheets. Inténtalo de nuevo.")

@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(status_code=500, detail="Falta configurar la clave del servicio.")
    mime = (audio.content_type or "").split(";")[0].lower().strip()
    allowed = {"audio/webm", "audio/mp4", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/ogg", "audio/aac", "audio/flac", "audio/m4a"}
    if mime not in allowed:
        raise HTTPException(status_code=415, detail="Formato de audio no compatible.")
    data = await audio.read(MAX_AUDIO_BYTES + 1)
    await audio.close()
    if not data:
        raise HTTPException(status_code=400, detail="La grabación está vacía.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="El audio supera el límite de 25 MB.")
    prompt = """Transcribe literalmente y en español el audio dictado por un odontólogo después de una consulta. Devuelve únicamente la transcripción, sin títulos, resúmenes, interpretaciones ni formato de historia clínica. Conserva el contenido, orden y sentido exactos. Reconoce términos odontológicos, procedimientos, materiales, medicamentos y anatomía dental. Conserva los números de dientes tal como se dictan. No inventes ni completes datos por contexto. Si algo no se entiende, escribe [inaudible]. Usa puntuación razonable sin reescribir."""
    logger.info("Transcription request received: mime=%s bytes=%s model=%s", mime, len(data), os.getenv("GEMINI_MODEL", "gemini-3.8-flash"))
    try:
        client = genai.Client(api_key=key)
        result = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
            contents=[prompt, types.Part.from_bytes(data=data, mime_type=mime)],
            config=types.GenerateContentConfig(temperature=0),
        )
        text = (result.text or "").strip()
        if not text:
            raise HTTPException(status_code=502, detail="El servicio no devolvió una transcripción.")
        return {"transcript": text}
    except HTTPException:
        raise
    except Exception as exc:
        # Log technical diagnostics only; never log the audio, transcript, or API key.
        message = str(exc).replace(key, "[REDACTED]")[:500]
        logger.error("Gemini API error (%s): %s", type(exc).__name__, message)
        raise HTTPException(status_code=502, detail="No fue posible transcribir el audio. Inténtalo de nuevo.")
    finally:
        del data
