"""Provider-owned voice catalogs, with tenant-scoped credentials."""

from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from api.services.configuration.ai_model_configuration import (
    get_resolved_ai_model_configuration,
)
from api.services.configuration.options.sarvam import SARVAM_V2_VOICES, SARVAM_V3_VOICES
from api.utils.url_security import validate_user_configured_service_url


def _voice(identifier: str, name: str | None = None, **properties) -> dict:
    preview = properties.get("preview_url")
    if preview and urlparse(preview).scheme != "https":
        properties["preview_url"] = None
    return {"voice_id": identifier, "name": name or identifier, **properties}


def _api_key(config) -> str | None:
    value = getattr(config, "api_key", None)
    return value[0] if isinstance(value, list) and value else value


def _language(value: str | None) -> str | None:
    if not value:
        return None
    value = value.lower().replace("_", "-")
    return {"eng": "en", "spa": "es", "deu": "de", "fra": "fr", "hin": "hi"}.get(
        value, value
    )


def filter_catalogue(voices: list[dict], **filters) -> dict:
    facets = {
        field + "s": sorted({str(voice[field]) for voice in voices if voice.get(field)})
        for field in ("gender", "accent", "language")
    }
    result = []
    for voice in voices:
        if (
            filters.get("q")
            and filters["q"].casefold()
            not in " ".join(
                str(voice.get(field) or "")
                for field in ("name", "voice_id", "description", "accent", "language")
            ).casefold()
        ):
            continue
        if any(
            filters.get(field)
            and str(voice.get(field) or "").casefold() != filters[field].casefold()
            for field in ("gender", "accent")
        ):
            continue
        language = _language(filters.get("language"))
        voice_language = _language(voice.get("language"))
        if (
            language
            and voice_language
            and language.split("-")[0] != voice_language.split("-")[0]
        ):
            continue
        result.append(voice)
    return {"voices": result, "facets": facets}


async def get_direct_voices(
    *,
    organization_id: int,
    provider: str,
    model: str | None = None,
    language: str | None = None,
    q: str | None = None,
    gender: str | None = None,
    accent: str | None = None,
    api_key: str | None = None,
) -> dict:
    if provider == "dograh":
        raise HTTPException(
            422,
            "Elige un proveedor propio; los servicios de Dograh están desactivados.",
        )
    if provider == "sarvam":
        names = SARVAM_V3_VOICES if model == "bulbul:v3" else SARVAM_V2_VOICES
        return {
            "provider": provider,
            **filter_catalogue(
                [_voice(name, name.capitalize()) for name in names],
                language=language,
                q=q,
                gender=gender,
                accent=accent,
            ),
        }

    resolved = await get_resolved_ai_model_configuration(
        organization_id=organization_id
    )
    tts = resolved.effective.tts
    saved = tts if getattr(tts, "provider", None) == provider else None
    # Masked UI placeholders never go to a provider as if they were credentials.
    if not api_key or "*" in api_key:
        api_key = _api_key(saved)
    if provider != "rime" and not api_key:
        raise HTTPException(
            422, "Configura la API key de este proveedor para consultar sus voces."
        )

    voices: list[dict] = []
    async with httpx.AsyncClient(
        timeout=15, follow_redirects=False, trust_env=False
    ) as client:
        if provider in {"elevenlabs", "cartesia"}:
            params: dict = (
                {"page_size": 100}
                if provider == "elevenlabs"
                else {"limit": 100, "expand[]": "preview_file_url"}
            )
            if q:
                params["search" if provider == "elevenlabs" else "q"] = q
            if provider == "elevenlabs":
                url, headers = (
                    "https://api.elevenlabs.io/v2/voices",
                    {"xi-api-key": api_key},
                )
            else:
                url, headers = (
                    "https://api.cartesia.ai/voices",
                    {
                        "Authorization": f"Bearer {api_key}",
                        "Cartesia-Version": "2026-08-14",
                    },
                )
            for _page in range(20):
                response = await client.get(url, headers=headers, params=params)
                _check_response(response)
                payload = response.json()
                for item in payload.get(
                    "voices" if provider == "elevenlabs" else "data", []
                ):
                    labels = item.get("labels") or {}
                    accents = item.get("accents") or []
                    native_accent = next(
                        (a.get("accent") for a in accents if a.get("is_native")), None
                    )
                    voices.append(
                        _voice(
                            item.get("voice_id") or item["id"],
                            item.get("name"),
                            description=item.get("description"),
                            gender=item.get("gender") or labels.get("gender"),
                            accent=native_accent or labels.get("accent"),
                            language=item.get("language") or labels.get("language"),
                            preview_url=item.get("preview_url")
                            or item.get("preview_file_url"),
                        )
                    )
                cursor = payload.get(
                    "next_page_token" if provider == "elevenlabs" else "next_page"
                )
                if not payload.get("has_more") or not cursor:
                    break
                params[
                    "next_page_token" if provider == "elevenlabs" else "starting_after"
                ] = cursor
            else:
                raise HTTPException(
                    422,
                    "Hay demasiadas voces. Usa la búsqueda para reducir el catálogo.",
                )
        elif provider == "deepgram":
            base_url = getattr(saved, "base_url", None) or "https://api.deepgram.com"
            validate_user_configured_service_url(base_url, field_name="base_url")
            response = await client.get(
                base_url.rstrip("/") + "/v1/models",
                headers={"Authorization": f"Token {api_key}"},
            )
            _check_response(response)
            for item in response.json().get("tts", []):
                if model and item.get("architecture") != model:
                    continue
                metadata = item.get("metadata") or {}
                tags = metadata.get("tags") or []
                voices.append(
                    _voice(
                        item["canonical_name"],
                        item.get("name"),
                        gender=next(
                            (
                                tag
                                for tag in tags
                                if tag in {"masculine", "feminine", "neutral"}
                            ),
                            None,
                        ),
                        accent=metadata.get("accent"),
                        language=(item.get("languages") or [None])[0],
                        description=", ".join(tags),
                        preview_url=metadata.get("sample"),
                    )
                )
        elif provider == "rime":
            response = await client.get(
                "https://users.rime.ai/data/voices/voice_details.json"
            )
            _check_response(response)
            for item in response.json():
                if model and item.get("modelId") != model:
                    continue
                voices.append(
                    _voice(
                        item["speaker"],
                        item["speaker"].capitalize(),
                        gender=(item.get("gender") or "").lower() or None,
                        accent=item.get("dialect") or item.get("country"),
                        language=_language(item.get("lang")),
                        description=", ".join(item.get("genre") or []),
                    )
                )
        else:
            raise HTTPException(
                422, "Este proveedor admite escribir el ID de voz manualmente."
            )
    return {
        "provider": provider,
        **filter_catalogue(
            voices,
            language=language,
            q=q,
            gender=gender,
            accent=accent,
        ),
    }


def _check_response(response: httpx.Response) -> None:
    if response.status_code in {401, 403}:
        raise HTTPException(
            422, "El proveedor rechazó la API key. Revisa sus permisos."
        )
    if response.status_code == 429:
        raise HTTPException(
            429, "El proveedor alcanzó su límite de consultas. Inténtalo más tarde."
        )
    if response.status_code != 200:
        raise HTTPException(
            502, "No se pudo consultar el catálogo de voces del proveedor."
        )
