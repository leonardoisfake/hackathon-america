"""Cliente de la API de Hudl StatsBomb (Liga MX).

Las credenciales salen de SB_USER y SB_PASS (entorno o archivo .env). Cada respuesta se
guarda en data/raw/<slug>.json y no se vuelve a pedir. Hay un reintento ante timeout o 5xx.
"""
import json
import os
import re
import time
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

BASE_URL = "https://data.statsbomb.com/api"
TIMEOUT = 120
ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "data" / "raw"

# season_id de Liga MX (competition_id 73): Apertura 2021 a Clausura 2025
TEMPORADAS_RETO = [108, 235, 281, 317]


class SBAuthError(Exception):
    # 401 o 403: la API rechazo las credenciales.

    def __init__(self, status, url):
        super().__init__(f"HTTP {status} en {url}: credenciales rechazadas")
        self.status = status
        self.url = url


class SBHTTPError(Exception):
    # Respuesta distinta de 200 (los 401 y 403 lanzan SBAuthError).

    def __init__(self, status, url):
        super().__init__(f"HTTP {status} en {url}")
        self.status = status
        self.url = url


def _leer_env_archivo(ruta=ROOT / ".env"):
    valores = {}
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            valores[k.strip()] = v.strip().strip('"').strip("'")
    return valores


def _credenciales():
    user, pwd = os.environ.get("SB_USER"), os.environ.get("SB_PASS")
    if not (user and pwd):
        archivo = _leer_env_archivo()
        user = user or archivo.get("SB_USER")
        pwd = pwd or archivo.get("SB_PASS")
    if not (user and pwd):
        raise RuntimeError("Faltan SB_USER / SB_PASS (variables de entorno o archivo .env).")
    return HTTPBasicAuth(user, pwd)


def _slug(path, params=None):
    s = path.strip("/")
    if params:
        s += "_" + "_".join(f"{k}-{v}" for k, v in sorted(params.items()))
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)


def en_cache(path, params=None):
    # True si la respuesta ya esta en data/raw y fetch no llamara a la API.
    return (RAW_DIR / f"{_slug(path, params)}.json").exists()


def ruta_cache(path, params=None):
    return RAW_DIR / f"{_slug(path, params)}.json"


def verificar_credenciales():
    # Lanza RuntimeError si faltan SB_USER / SB_PASS (no imprime valores).
    _credenciales()


def fetch(path, params=None):
    # JSON de `path` (relativo a BASE_URL), tomado de la cache si existe.
    cache = RAW_DIR / f"{_slug(path, params)}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cache.unlink()  # cache corrupta: se borra y se vuelve a pedir

    url = f"{BASE_URL}/{path.lstrip('/')}"
    auth = _credenciales()
    resp = None
    for intento in range(2):
        try:
            resp = requests.get(url, params=params, auth=auth, timeout=TIMEOUT)
        except requests.exceptions.Timeout:
            if intento == 0:
                time.sleep(2)
                continue
            raise
        if resp.status_code >= 500 and intento == 0:
            time.sleep(2)
            continue
        break

    if resp.status_code in (401, 403):
        raise SBAuthError(resp.status_code, url)
    if resp.status_code != 200:
        raise SBHTTPError(resp.status_code, url)
    data = resp.json()
    if isinstance(data, list) and data:  # solo se cachean listas con elementos
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_name(cache.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, cache)  # evita dejar un JSON a medias si se corta la escritura
    return data


def competitions():
    return fetch("v4/competitions")


def matches(comp_id, season_id):
    return fetch(f"v6/competitions/{comp_id}/seasons/{season_id}/matches")


def lineups(match_id):
    return fetch(f"v5/lineups/{match_id}")


def events(match_id):
    return fetch(f"v11/events/{match_id}")


def frames_360(match_id):
    return fetch(f"v2/360-frames/{match_id}")


def player_match_stats(match_id):
    return fetch(f"v8/matches/{match_id}/player-stats")


def player_season_stats(comp_id, season_id):
    return fetch(f"v7/competitions/{comp_id}/seasons/{season_id}/player-stats")


def team_match_stats(match_id):
    return fetch(f"v4/matches/{match_id}/team-stats")


def team_season_stats(comp_id, season_id):
    return fetch(f"v4/competitions/{comp_id}/seasons/{season_id}/team-stats")


def player_mapping(comp_id, season_id):
    return fetch("v1/player-mapping", {"competition-id": comp_id, "season-id": season_id})
