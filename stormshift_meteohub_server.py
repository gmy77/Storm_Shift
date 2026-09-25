#!/usr/bin/env python3
"""Server locale StormShift per servire radar METEOHUB alla dashboard."""

from __future__ import annotations

import base64
import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from time import monotonic

import fsspec
import numpy as np
import xarray as xr
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response


BASE_DIR = Path(__file__).resolve().parent
# La dashboard sta in public/: la stessa cartella che il Worker Cloudflare
# serve come asset statici, cosi' il file e' uno solo per le due versioni.
DASHBOARD_FILE = BASE_DIR / "public" / "index.html"
METAGRAM_FILE = BASE_DIR / "public" / "metagram.html"
ARCO_RADAR_URL = "https://meteohub.agenziaitaliameteo.it/api/arco/radar.zarr"
FVG_BOUNDS = {"lat_min": 45.55, "lat_max": 46.70, "lon_min": 12.30, "lon_max": 13.95}
MAX_AGE_SECONDS = 300
SAMPLE_STEP = 4
DATASET_FAILURE_RESET_THRESHOLD = 3
RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW_SECONDS = 60.0

app = FastAPI(title="StormShift MeteoHub Bridge", docs_url=None, redoc_url=None)
_radar_cache: dict[str, object] = {"loaded_at": 0.0, "payload": None}
_loop_cache: dict[str, object] = {"loaded_at": 0.0, "minutes": None, "payload": None}
_dataset_failures = {"count": 0}
_request_log: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Limita le richieste per IP per proteggere le credenziali ARCO da abusi."""
    # Dietro Cloudflare (Tunnel o Worker) request.client e' sempre lo stesso
    # proxy: l'IP vero del visitatore arriva in CF-Connecting-IP. Senza, il
    # limite diventava uno solo per tutti i visitatori insieme.
    client_ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
    now = monotonic()
    log = _request_log[client_ip]
    while log and now - log[0] > RATE_LIMIT_WINDOW_SECONDS:
        log.popleft()
    if len(log) >= RATE_LIMIT_REQUESTS:
        return JSONResponse(status_code=429, content={"detail": "Troppe richieste, riprova tra poco."})
    log.append(now)
    return await call_next(request)


def reset_dataset_cache_on_repeated_failure() -> None:
    """Forza la riapertura del dataset ARCO dopo fallimenti ripetuti (es. sessione scaduta)."""
    _dataset_failures["count"] += 1
    if _dataset_failures["count"] >= DATASET_FAILURE_RESET_THRESHOLD:
        radar_dataset.cache_clear()
        fvg_indexes.cache_clear()
        _dataset_failures["count"] = 0


def mark_dataset_healthy() -> None:
    _dataset_failures["count"] = 0


def get_arco_credentials() -> tuple[str, str]:
    """Credenziali ARCO: prima le variabili d'ambiente, poi il vault Windows.

    Nel Container Cloudflare le passa il Worker dai suoi segreti
    (METEOHUB_EMAIL, METEOHUB_ARCO_ACCESS_KEY). Sul PC restano nel Windows
    Credential Manager: il modulo che lo usa si importa solo li', perche'
    carica DLL di Windows e su Linux fallirebbe gia' all'import.
    """
    email = os.environ.get("METEOHUB_EMAIL", "").strip()
    access_key = os.environ.get("METEOHUB_ARCO_ACCESS_KEY", "").strip()
    if email and access_key:
        return email, access_key
    if sys.platform != "win32":
        raise RuntimeError(
            "Credenziali METEOHUB mancanti: servono le variabili d'ambiente "
            "METEOHUB_EMAIL e METEOHUB_ARCO_ACCESS_KEY (segreti del Worker)."
        )
    from stormshift_meteohub_secrets import get_arco_credentials as from_vault

    return from_vault()


@lru_cache(maxsize=1)
def radar_dataset() -> xr.Dataset:
    """Apre il dataset ARCO con autenticazione Basic senza esporre i segreti."""
    email, access_key = get_arco_credentials()
    authorization = base64.b64encode(f"{email}:{access_key}".encode()).decode()
    store = fsspec.get_mapper(
        ARCO_RADAR_URL,
        client_kwargs={"headers": {"Authorization": f"Basic {authorization}"}},
    )
    return xr.open_zarr(store, consolidated=True)


@lru_cache(maxsize=1)
def fvg_indexes() -> tuple[slice, slice]:
    """Calcola una sola volta il rettangolo di griglia che contiene il FVG."""
    dataset = radar_dataset()
    latitudes = dataset["lat"].values
    longitudes = dataset["lon"].values
    inside = (
        (latitudes >= FVG_BOUNDS["lat_min"])
        & (latitudes <= FVG_BOUNDS["lat_max"])
        & (longitudes >= FVG_BOUNDS["lon_min"])
        & (longitudes <= FVG_BOUNDS["lon_max"])
    )
    rows, columns = np.where(inside)
    if not len(rows):
        raise RuntimeError("La griglia radar non copre il rettangolo FVG configurato.")
    return slice(rows.min(), rows.max() + 1), slice(columns.min(), columns.max() + 1)


def latest_populated_index(dataset: xr.Dataset, y_slice: slice, x_slice: slice) -> int:
    """Trova l'ultimo frame disponibile fino all'ora corrente, evitando date future vuote."""
    now = np.datetime64(datetime.now(timezone.utc).replace(tzinfo=None))
    upper = min(int(dataset.time.searchsorted(now, side="right")) - 1, dataset.sizes["time"] - 1)
    if upper < 0:
        raise RuntimeError("L'archivio radar non contiene ancora dati utilizzabili.")

    # I frame sono a cinque minuti: una ricerca oraria limita le letture remote.
    first_valid = None
    for index in range(upper, max(-1, upper - 7 * 24 * 12), -12):
        sample = dataset["RR"].isel(time=index, y=y_slice, x=x_slice).values
        if np.isfinite(sample).any():
            first_valid = index
            break
    if first_valid is None:
        raise RuntimeError("Nessun frame radar valido trovato negli ultimi sette giorni.")
    for index in range(min(upper, first_valid + 11), first_valid - 1, -1):
        sample = dataset["RR"].isel(time=index, y=y_slice, x=x_slice).values
        if np.isfinite(sample).any():
            return index
    return first_valid


def frame_payload(dataset: xr.Dataset, time_index: int, y_slice: slice, x_slice: slice) -> dict[str, object]:
    """Trasforma un singolo frame radar in una griglia JSON FVG compatta."""
    frame = dataset["RR"].isel(time=time_index, y=y_slice, x=x_slice)
    latitudes = dataset["lat"].isel(y=y_slice, x=x_slice).values[::SAMPLE_STEP, ::SAMPLE_STEP]
    longitudes = dataset["lon"].isel(y=y_slice, x=x_slice).values[::SAMPLE_STEP, ::SAMPLE_STEP]
    values = frame.values[::SAMPLE_STEP, ::SAMPLE_STEP]
    values = np.where(np.isfinite(values), values, -1).round(2)
    return {
        "timestamp": np.datetime_as_string(frame.time.values, unit="m") + "Z",
        "units": "kg m-2 h-1",
        "step": SAMPLE_STEP,
        "latitudes": latitudes.round(4).tolist(),
        "longitudes": longitudes.round(4).tolist(),
        "values": values.tolist(),
    }


def radar_payload() -> dict[str, object]:
    """Restituisce l'ultimo frame FVG decimato, adatto al browser."""
    cache_age = monotonic() - float(_radar_cache["loaded_at"])
    cached_payload = _radar_cache["payload"]
    if isinstance(cached_payload, dict) and cache_age < MAX_AGE_SECONDS:
        return cached_payload

    try:
        dataset = radar_dataset()
        y_slice, x_slice = fvg_indexes()
        time_index = latest_populated_index(dataset, y_slice, x_slice)
        payload = frame_payload(dataset, time_index, y_slice, x_slice)
    except Exception:
        reset_dataset_cache_on_repeated_failure()
        raise
    mark_dataset_healthy()
    _radar_cache["loaded_at"] = monotonic()
    _radar_cache["payload"] = payload
    return payload


def radar_loop_payload(minutes: int) -> dict[str, object]:
    """Restituisce una sequenza radar FVG a cinque minuti per l'animazione."""
    cache_age = monotonic() - float(_loop_cache["loaded_at"])
    cached_payload = _loop_cache["payload"]
    if (
        isinstance(cached_payload, dict)
        and _loop_cache["minutes"] == minutes
        and cache_age < MAX_AGE_SECONDS
    ):
        return cached_payload

    latest = radar_payload()
    try:
        dataset = radar_dataset()
        y_slice, x_slice = fvg_indexes()
        timestamp = np.datetime64(str(latest["timestamp"]).removesuffix("Z"))
        latest_index = int(dataset.time.searchsorted(timestamp, side="left"))
        frame_count = minutes // 5 + 1
        start_index = max(0, latest_index - frame_count + 1)
        frames = [
            frame_payload(dataset, index, y_slice, x_slice)
            for index in range(start_index, latest_index + 1)
        ]
    except Exception:
        reset_dataset_cache_on_repeated_failure()
        raise
    mark_dataset_healthy()
    payload = {"interval_minutes": 5, "frames": frames}
    _loop_cache["loaded_at"] = monotonic()
    _loop_cache["minutes"] = minutes
    _loop_cache["payload"] = payload
    return payload


@app.api_route("/", methods=["GET", "HEAD"])
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_FILE)


@app.api_route("/metagram.html", methods=["GET", "HEAD"])
def metagram() -> FileResponse:
    return FileResponse(METAGRAM_FILE)


@app.get("/api/health")
def health() -> dict[str, object]:
    try:
        radar_dataset()
    except Exception as error:
        reset_dataset_cache_on_repeated_failure()
        raise HTTPException(status_code=503, detail="Archivio ARCO non disponibile.") from error
    mark_dataset_healthy()
    return {"status": "ok", "source": "METEOHUB ARCO radar.zarr"}


@app.get("/api/radar/latest")
def latest_radar() -> dict[str, object]:
    try:
        return radar_payload()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Frame radar non disponibile.") from error


@app.get("/api/radar/loop")
def radar_loop(minutes: int = Query(default=60, ge=15, le=120, multiple_of=5)) -> dict[str, object]:
    try:
        return radar_loop_payload(minutes)
    except Exception as error:
        raise HTTPException(status_code=503, detail="Sequenza radar non disponibile.") from error


@app.get("/robots.txt", include_in_schema=False)
def robots() -> PlainTextResponse:
    """Tiene i crawler fuori dagli endpoint API (che consumano ARCO)."""
    return PlainTextResponse(
        "User-agent: *\n"
        "Disallow: /api/\n"
        "Allow: /\n"
        "Sitemap: https://stormshift.gimmycloud.net/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap() -> Response:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        '  <url><loc>https://stormshift.gimmycloud.net/</loc></url>\n'
        '</urlset>\n'
    )
    return Response(content=xml, media_type="application/xml")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
