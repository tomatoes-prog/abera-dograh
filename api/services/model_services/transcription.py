"""Transcribe an uploaded file directly with a configured provider."""

import asyncio
import json
import tempfile
from pathlib import Path

import aiofiles
import httpx
from fastapi import HTTPException, UploadFile

from api.services.configuration.ai_model_configuration import (
    get_resolved_ai_model_configuration,
)
from api.utils.url_security import validate_user_configured_service_url

MAX_AUDIO_BYTES = 25 * 1024 * 1024
_AUDIO_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".mp4",
    ".m4a",
    ".ogg",
    ".flac",
    ".webm",
    ".mpeg",
    ".mpga",
}


def _key(config) -> str | None:
    key = getattr(config, "api_key", None)
    return key[0] if isinstance(key, list) and key else key


async def _duration(path: str) -> float:
    process = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=10)
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    try:
        duration = float(json.loads(output)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            422, "No se pudo leer el audio. Revisa su formato."
        ) from None
    if process.returncode != 0 or not 0 < duration <= 3600:
        raise HTTPException(422, "El audio debe durar entre un segundo y una hora.")
    return duration


async def _file_chunks(path: str):
    async with aiofiles.open(path, "rb") as source:
        while chunk := await source.read(64 * 1024):
            yield chunk


async def transcribe_uploaded_audio(
    *,
    organization_id: int,
    file: UploadFile,
    language: str,
) -> dict:
    filename = Path(file.filename or "audio.wav").name
    if Path(filename).suffix.lower() not in _AUDIO_EXTENSIONS:
        raise HTTPException(422, "Usa un archivo WAV, MP3, M4A, OGG, FLAC o WebM.")
    if len(language) > 16:
        raise HTTPException(422, "El código de idioma no es válido.")
    config = (
        await get_resolved_ai_model_configuration(organization_id=organization_id)
    ).effective
    stt = config.stt
    provider = getattr(stt, "provider", None)
    key = _key(stt)
    if provider not in {"openai", "deepgram", "elevenlabs"} or not key:
        # Realtime configurations have no standalone STT. Their OpenAI key can
        # authorize file transcription, without involving the live voice model.
        candidates = [config.realtime, config.llm]
        fallback = next(
            (
                item
                for item in candidates
                if getattr(item, "provider", None) in {"openai", "openai_realtime"}
                and _key(item)
            ),
            None,
        )
        if fallback is None:
            raise HTTPException(
                422,
                "Configura OpenAI, Deepgram o ElevenLabs para transcribir archivos de audio.",
            )
        provider, key = "openai", _key(fallback)
        stt = None
        base_url = getattr(fallback, "base_url", None) or "https://api.openai.com/v1"
    else:
        base_url = getattr(stt, "base_url", None) or "https://api.openai.com/v1"

    with tempfile.TemporaryDirectory(prefix="abera-transcription-") as temp_dir:
        path = str(Path(temp_dir) / ("audio" + Path(filename).suffix.lower()))
        size = 0
        async with aiofiles.open(path, "wb") as destination:
            while chunk := await file.read(64 * 1024):
                size += len(chunk)
                if size > MAX_AUDIO_BYTES:
                    raise HTTPException(413, "El audio supera el límite de 25 MB.")
                await destination.write(chunk)
        if not size:
            raise HTTPException(422, "El archivo de audio está vacío.")
        duration = await _duration(path)
        lang = None if language in {"auto", "multi", "unknown", ""} else language
        async with httpx.AsyncClient(
            timeout=90, follow_redirects=False, trust_env=False
        ) as client:
            if provider == "deepgram":
                params = {
                    "model": getattr(stt, "model", "nova-3"),
                    "smart_format": "true",
                }
                if str(params["model"]).startswith("flux"):
                    params["model"] = (
                        "nova-3"  # Flux is live-only; use its batch counterpart.
                    )
                params.update(
                    {"language": lang} if lang else {"detect_language": "true"}
                )
                deepgram_url = (
                    getattr(stt, "base_url", None) or "https://api.deepgram.com"
                )
                validate_user_configured_service_url(
                    deepgram_url, field_name="base_url"
                )
                response = await client.post(
                    deepgram_url.rstrip("/") + "/v1/listen",
                    params=params,
                    headers={
                        "Authorization": f"Token {key}",
                        "Content-Type": file.content_type or "application/octet-stream",
                    },
                    content=_file_chunks(path),
                )
            else:
                with open(path, "rb") as source:
                    files = {
                        "file": (
                            filename,
                            source,
                            file.content_type or "application/octet-stream",
                        )
                    }
                    if provider == "elevenlabs":
                        data = {"model_id": getattr(stt, "model", "scribe_v1")}
                        if lang:
                            data["language_code"] = lang
                        response = await client.post(
                            "https://api.elevenlabs.io/v1/speech-to-text",
                            headers={"xi-api-key": key},
                            data=data,
                            files=files,
                        )
                    else:
                        validate_user_configured_service_url(
                            base_url, field_name="base_url"
                        )
                        data = {
                            "model": getattr(stt, "model", "gpt-4o-mini-transcribe"),
                            "response_format": "json",
                        }
                        if lang:
                            data["language"] = lang
                        response = await client.post(
                            base_url.rstrip("/") + "/audio/transcriptions",
                            headers={"Authorization": f"Bearer {key}"},
                            data=data,
                            files=files,
                        )
            if response.status_code >= 400:
                status = 429 if response.status_code == 429 else 502
                raise HTTPException(
                    status,
                    "El proveedor no pudo transcribir el audio. Revisa la API key y el saldo.",
                )
            response.raise_for_status()
            result = response.json()
        if provider == "deepgram":
            transcript = result["results"]["channels"][0]["alternatives"][0][
                "transcript"
            ]
        else:
            transcript = result.get("text", "")
        return {
            "transcript": transcript,
            "duration_seconds": duration,
            "language": lang,
            "provider": provider,
        }
