"""Limpieza de los datos crudos (plan 7.1 a 7.3) segun el contrato v0.2 (docs/contrato/contrato_datos.csv).

Uso:
    python scripts/02_limpieza.py --solo-partido 3995374   # escribe en data/interim/muestra/
    python scripts/02_limpieza.py                          # todos los partidos de partidos.parquet, en data/interim/

Arma partidos, eventos, frames_360, frames_360_evento, alineaciones, posiciones, team_match_stats,
player_match_stats y team_match_stats_liga. Tipo, origen y relleno de cada columna salen del contrato
(aplicar_contrato); las derivadas (x, y, pass_completed, n_visibles_*, ...) se calculan en las funciones limpiar_*.
Una columna cruda que no existe solo se crea vacia si el contrato dice puede_faltar; si no, la corrida se detiene.
Los partidos que no pasan los filtros de calidad (7.1) se excluyen, se imprimen y quedan en partidos_excluidos.csv.
Todas las tablas usan solo los partidos que pasaron, menos team_match_stats_liga (linea base de toda la liga;
con --solo-partido deja solo las filas de ese partido). No se borran filas por criterios de analisis: solo se marcan.

Antes de escribir, cada tabla pasa por contrato.validar(); cada partido debe tener eventos, frames 360 (las dos
tablas), filas en player_match_stats, home_team_id, away_team_id y equipo_id no nulos, equipo_id igual al local o al
visitante, exactamente el local y el visitante en alineaciones y team_match_stats, y al menos un evento con
es_equipo_analizado no nulo; y ninguna tabla puede tener llaves duplicadas ni huerfanos. Un hueco de cobertura
detiene toda la corrida: no excluye el partido (decision del usuario para este PR). Si algo falla no se escribe
nada. Si todo pasa, escribe en una carpeta temporal y reemplaza archivo por archivo, despues de comprobar que ningun
destino esta bloqueado. Junto con
las tablas escribe calidad_limpieza.csv (filas crudas y limpias, llaves duplicadas, huerfanos y columnas creadas
vacias por tabla) y cobertura_360_por_partido.csv (eventos con frame en total, tacticos y del equipo
analizado, frames sin conteo y frames que cumplen la regla provisional de Lee para C19, solo informativa).

Codigos de salida: 0 si todo se escribio; 1 si hay un error de datos, contrato, cobertura o escritura (salvo un
reemplazo a medias, no se escribe nada); 2 si el partido pedido con --solo-partido no existe o esta excluido.
"""
import contextlib
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile
from array import array
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # contrato.py esta en scripts/
import contrato  # noqa: E402
from contrato import ADMINISTRATIVOS  # noqa: E402

RAW = ROOT / "data" / "raw" / "parquet"
INTERIM = ROOT / "data" / "interim"
ANCHO, ALTO = 120.0, 80.0  # cancha de StatsBomb, en yardas
# filtros de calidad de partidos (plan 7.1)
# NoVidError, IncVidError y PoorVidError son valores de collection_status, asi que pedir Complete ya los deja fuera
PARTIDO_OK = {"play_status": "Normal", "match_status": "available", "collection_status": "Complete",
              "match_status_360": "available"}
# llave de cada tabla (docs/contrato/<tabla>.md); se usa para ordenar y para el reporte de calidad
LLAVES = {
    "partidos": ["match_id"],
    "eventos": ["match_id", "index"],
    "frames_360": ["match_id", "event_uuid", "jugador_idx"],
    "frames_360_evento": ["match_id", "event_uuid"],
    "alineaciones": ["match_id", "team_id", "player_id"],
    "posiciones": ["match_id", "team_id", "player_id", "posicion_idx"],
    "team_match_stats": ["match_id", "team_id"],
    "player_match_stats": ["match_id", "team_id", "player_id"],
    "team_match_stats_liga": ["match_id", "team_id"],
}
# tablas padre para contar huerfanos: (padre, columnas en la hija, columnas en el padre)
_ALINEACION = ("alineaciones", ("match_id", "team_id", "player_id"), ("match_id", "team_id", "player_id"))
PADRES = {
    "eventos": (("partidos", ("match_id",), ("match_id",)),),
    "alineaciones": (("partidos", ("match_id",), ("match_id",)),),
    "posiciones": (("partidos", ("match_id",), ("match_id",)), _ALINEACION),
    "team_match_stats": (("partidos", ("match_id",), ("match_id",)),),
    "player_match_stats": (("partidos", ("match_id",), ("match_id",)), _ALINEACION),
    "frames_360": (("eventos", ("match_id", "event_uuid"), ("match_id", "id")),),
    "frames_360_evento": (("eventos", ("match_id", "event_uuid"), ("match_id", "id")),),
}
# errores de datos que se pasan a ErrorLimpieza con la tabla (JSONDecodeError es un ValueError)
ERRORES_DATOS = (ValueError, TypeError, KeyError, IndexError)
FINES = ("pass.end_location", "carry.end_location", "shot.end_location", "goalkeeper.end_location")
FIN_Z = "shot.end_location"  # el contrato toma end_z solo del tiro
# columnas crudas de eventos que usan las derivadas; el resto se lee solo si es origen del contrato
USADAS_EVENTOS = ("match_id", "index", "location", *FINES, "type.name", "pass.outcome.name",
                  "ball_receipt.outcome.name", "minute", "second", "team.id")
UMBRAL_C19 = 10  # provisional de Lee (C19): actor visible y al menos 10 jugadores visibles; solo informativo
COLS_TRAMO = ("position_id", "position", "from", "to", "from_period", "to_period", "start_reason", "end_reason",
              "counterpart_id", "counterpart_name")


class ErrorLimpieza(Exception):
    pass


@contextlib.contextmanager
def _contexto(donde):
    # Pasa un error de datos a ErrorLimpieza con la tabla (y la columna o el match_id si se conocen).
    try:
        yield
    except ERRORES_DATOS as e:
        raise ErrorLimpieza(f"{donde}: {type(e).__name__}: {e}") from e


def leer_raw(nombre, match_ids=None, columnas=None):
    # Lee <nombre>.parquet o sus partes <nombre>__*.parquet de data/raw/parquet, solo con los match_id y columnas pedidos.
    archivos = sorted(glob.glob(str(RAW / f"{nombre}__*.parquet"))) or [str(RAW / f"{nombre}.parquet")]
    filtro = [("match_id", "in", [int(i) for i in match_ids])] if match_ids is not None else None
    tablas = []
    for a in archivos:
        print(f"lee {Path(a).name}")
        cols = None if columnas is None else [x for x in pq.read_schema(a).names if x in columnas]
        tablas.append(pq.read_table(a, columns=cols, filters=filtro))
    t = pa.concat_tables(tablas, promote_options="permissive")
    del tablas
    return t.to_pandas()


def _json(valor):
    # Texto JSON a lista o dict; una lista ya parseada pasa tal cual y el nulo da None.
    if isinstance(valor, str):
        return json.loads(valor)
    if isinstance(valor, (list, np.ndarray)):
        return valor
    if pd.api.types.is_scalar(valor) and pd.isna(valor):
        return None
    raise TypeError(f"se esperaba texto JSON, lista o nulo y llego {type(valor).__name__}")


def _lista(valor):
    lst = _json(valor)
    if lst is None:
        return []
    if not isinstance(lst, (list, np.ndarray)):
        raise TypeError(f"se esperaba una lista y llego {type(lst).__name__}")
    return lst


def _coords(serie, n):
    # Primeros n elementos de cada lista [x, y(, z)] guardada como texto JSON, en una matriz; NaN si falta.
    out = np.full((len(serie), n), np.nan)
    for k, v in enumerate(serie.to_numpy(dtype=object)):
        try:
            lst = _json(v)
            if lst is not None:
                m = min(len(lst), n)
                out[k, :m] = lst[:m]
        except ERRORES_DATOS as e:
            raise ValueError(f"fila {k} ({str(v)[:60]!r}): {e}") from e
    return out


def _es_booleana(s):
    return pd.api.types.is_bool_dtype(s.dtype) or (s.dtype == object and pd.api.types.infer_dtype(s) == "boolean")


def _a_numero(s, tipo):
    if _es_booleana(s):
        raise TypeError(f"la serie es booleana ({s.dtype}) y el contrato pide {tipo}")
    out = pd.to_numeric(s, errors="coerce")
    malos = s.notna() & out.isna()
    if malos.any():
        raise ValueError(f"{int(malos.sum())} valores no nulos no se pueden convertir a {tipo}, "
                         f"por ejemplo {s[malos].unique()[:5].tolist()}")
    return out.astype(tipo)


def _cast(s, tipo):
    if tipo in ("Int64", "float64"):
        return _a_numero(s, tipo)
    if tipo == "boolean":
        return s.astype("boolean")
    if tipo == "string":
        return s.astype("string").str.strip()
    if tipo == "category":
        return s.astype("string").str.strip().astype("category")
    if tipo == "datetime64[us]":
        # un numero se leeria como epoch sin avisar; las fechas deben llegar como texto ISO o como fecha
        if pd.api.types.is_numeric_dtype(s.dtype) or (
                s.dtype == object and pd.api.types.infer_dtype(s) in ("integer", "floating", "mixed-integer-float", "boolean")):
            raise TypeError(f"las fechas llegan como numeros ({s.dtype}) y se esperaba texto ISO 8601")
        out = pd.to_datetime(s, format="ISO8601")
        if isinstance(out.dtype, pd.DatetimeTZDtype):
            raise ValueError(f"las fechas traen zona horaria ({out.dtype.tz}) y el contrato las pide sin zona")
        return out.astype("datetime64[us]")
    raise ValueError(f"tipo desconocido en el contrato: {tipo}")


def _vacia(n, tipo, indice):
    return pd.Series(pd.array([pd.NA] * n, dtype=tipo if tipo != "category" else "string"), index=indice).pipe(
        lambda s: s.astype("category") if tipo == "category" else s)


def aplicar_contrato(df, ctx, tabla, especiales, filas_crudas=None):
    # Arma la tabla limpia columna por columna segun el contrato; `especiales` trae las que ya vienen calculadas.
    # filas_crudas: filas leidas del crudo, si son mas que las de `df` (partidos antes de excluir).
    ctx["crudas"][tabla] = len(df) if filas_crudas is None else filas_crudas
    c = ctx["contrato"]
    c = c[c["tabla"] == tabla]
    out, vacias = {}, []
    for _, f in c.iterrows():
        nombre, tipo, origen = f["columna"], f["tipo"], str(f["origen"])
        if nombre in especiales:
            serie = especiales[nombre]
        else:
            # el origen del contrato es el nombre de la columna cruda; si no esta, se prueba con el nombre de la columna
            crudo = origen if origen in df.columns else (nombre if nombre in df.columns else None)
            if crudo is None and not f["puede_faltar"]:
                raise ErrorLimpieza(f"{tabla}.{nombre}: no existe la columna cruda (origen {origen!r}) "
                                    "y el contrato no la marca como puede_faltar")
            serie = None if crudo is None else df[crudo]
        if serie is None:
            serie = _vacia(len(df), tipo, df.index)
            vacias.append(nombre)
        else:
            try:
                serie = _cast(serie, tipo)
            except (ValueError, TypeError) as e:
                raise ErrorLimpieza(f"{tabla}.{nombre} (origen {origen!r}, tipo {tipo}): {e}") from e
        if pd.notna(f["relleno"]) and f["relleno"] == "False":
            serie = serie.fillna(False)
        out[nombre] = serie
    ctx["vacias"][tabla] = vacias
    if vacias:
        print(f"{tabla}: columnas creadas vacias ({len(vacias)}): {vacias}")
    return pd.DataFrame(out, index=df.index)


@_contexto("partidos")
def limpiar_partidos(match_ids, ctx):
    # Devuelve los partidos que pasan los filtros y la lista de excluidos (match_id, campo, valor).
    raw = leer_raw("partidos", match_ids)
    excluidos = []
    with _contexto("partidos (filtros 7.1)"):
        for campo, esperado in PARTIDO_OK.items():
            # un nulo no es el valor esperado, asi que tambien excluye
            malo = (raw[campo].astype("string").str.strip() != esperado).fillna(True).to_numpy(dtype=bool)
            for mid, valor in raw.loc[malo, ["match_id", campo]].itertuples(index=False):
                excluidos.append((int(mid), campo, valor))
    fuera = {e[0] for e in excluidos}
    ok = raw[~raw["match_id"].isin(fuera)]
    repetidos = sorted(ok.loc[ok["match_id"].duplicated(keep=False), "match_id"].unique().tolist())
    if repetidos:
        raise ErrorLimpieza(f"partidos: match_id repetido en partidos.parquet despues de filtrar: {repetidos}")
    partidos =aplicar_contrato(ok, ctx, "partidos", {}, filas_crudas=len(raw)).sort_values(LLAVES["partidos"])
    return partidos.reset_index(drop=True), pd.DataFrame(excluidos, columns=["match_id", "campo", "valor"])


@_contexto("eventos")
def limpiar_eventos(match_ids, partidos, ctx):
    c = ctx["contrato"]
    c = c[c["tabla"] == "eventos"]
    columnas = set(c["origen"].astype(str)) | set(c["columna"]) | set(USADAS_EVENTOS)
    raw = leer_raw("events", match_ids, columnas)
    # leer_raw descarta en silencio las columnas pedidas que no existen; las que usan las derivadas no pueden faltar
    faltan = [x for x in USADAS_EVENTOS if x not in raw.columns]
    if faltan:
        raise ErrorLimpieza(f"eventos: faltan columnas crudas que usan las derivadas: {faltan}")
    raw = raw.sort_values(LLAVES["eventos"]).reset_index(drop=True)
    esp = {}
    with _contexto("eventos.location"):
        loc = _coords(raw["location"], 2)
    esp["x"] = pd.Series(loc[:, 0], index=raw.index)
    esp["y"] = pd.Series(loc[:, 1], index=raw.index)
    del loc
    # cada evento tiene a lo sumo un destino (contrato, C2); end_z sale solo del tiro
    fin = np.full((len(raw), 3), np.nan)
    n_destinos = np.zeros(len(raw), dtype="int8")
    for col in FINES:
        with _contexto(f"eventos.{col}"):
            nuevo = _coords(raw[col], 3)
        tiene = ~np.isnan(nuevo).all(axis=1)
        n_destinos += tiene
        fin[tiene, :2] = nuevo[tiene, :2]
        if col == FIN_Z:
            fin[:, 2] = nuevo[:, 2]
        del nuevo, tiene
    varios = n_destinos > 1
    if varios.any():
        ejemplos = raw.loc[varios, ["match_id", "index"]].head(5).values.tolist()
        raise ErrorLimpieza(f"eventos: {int(varios.sum())} eventos tienen mas de un destino no nulo en {FINES}; "
                            f"el contrato admite uno solo. Ejemplos (match_id, index): {ejemplos}")
    for eje, i in (("end_x", 0), ("end_y", 1), ("end_z", 2)):
        esp[eje] = pd.Series(fin[:, i], index=raw.index)
    del fin, n_destinos
    with _contexto("eventos"):
        tipo = raw["type.name"].astype("string").str.strip()
        # resultado vacio = exito (plan 7.3.2); nulo si el evento no es del tipo
        es_pase = (tipo == "Pass").fillna(False).to_numpy(dtype=bool)
        es_recepcion = (tipo == "Ball Receipt*").fillna(False).to_numpy(dtype=bool)
        esp["pass_completed"] = raw["pass.outcome.name"].isna().astype("boolean").where(es_pase)
        esp["receipt_ok"] = raw["ball_receipt.outcome.name"].isna().astype("boolean").where(es_recepcion)
        esp["match_second"] = raw["minute"].astype("Int64") * 60 + raw["second"].astype("Int64")
        esp["es_administrativo"] = tipo.isin(ADMINISTRATIVOS)
        p = partidos.set_index("match_id")
        for col in ("torneo", "fase", "es_play_in", "es_final"):
            esp[col] = raw["match_id"].map(p[col].astype(object))
        equipo = raw["match_id"].map(p["equipo_id"].astype(object))
        es_eq = raw["team.id"].astype("Int64") == equipo.astype("Int64")
    esp["es_equipo_analizado"] = es_eq
    # el rival ataca en sentido contrario: se voltea la cancha para ver todo desde el equipo analizado
    sin_equipo = es_eq.isna().to_numpy()
    propio = es_eq.fillna(False).to_numpy(dtype=bool)
    for base, tope in (("x", ANCHO), ("y", ALTO), ("end_x", ANCHO), ("end_y", ALTO)):
        v = esp[base].to_numpy()
        esp[f"{base}_eq"] = pd.Series(np.where(sin_equipo, np.nan, np.where(propio, v, tope - v)), index=raw.index)
    return aplicar_contrato(raw, ctx, "eventos", esp)


def _shoelace(lista_plana):
    if lista_plana is None or len(lista_plana) < 6:
        return np.nan
    pts = np.asarray(lista_plana, dtype="float64").reshape(-1, 2)
    x, y = pts[:, 0], pts[:, 1]
    # mismo calculo que np.roll(v, -1), sin su costo fijo en arreglos chicos
    return float(abs(np.dot(x, np.concatenate((y[1:], y[:1]))) - np.dot(y, np.concatenate((x[1:], x[:1])))) / 2)


def _uuid(serie):
    return serie.astype("string").str.strip()


def _de_eventos(llave, eventos, columna):
    # Columna de `eventos` para cada fila de `llave` (match_id, event_uuid); nulo si el evento no esta en `eventos`.
    ev = eventos[["match_id", "id", columna]].rename(columns={"id": "event_uuid"})
    unido = llave.merge(ev, how="left", on=["match_id", "event_uuid"], validate="many_to_one")
    return pd.Series(unido[columna].array, index=llave.index)


@_contexto("frames_360")
def limpiar_frames_360(raw, eventos, ctx):
    # se arma por columnas (array en lugar de una tupla por jugador) para no duplicar la memoria
    n, teammate, actor, keeper, x, y = [], [], [], [], array("d"), array("d")
    for mid, ff in zip(raw["match_id"], raw["freeze_frame"]):
        with _contexto(f"frames_360.freeze_frame, match_id {mid}"):
            jugadores = _lista(ff)
            n.append(len(jugadores))
            for j in jugadores:
                loc = j.get("location")
                # lista o ndarray; con menos de 2 valores queda NaN
                if loc is None or len(loc) < 2:
                    loc = (None, None)
                teammate.append(j.get("teammate"))
                actor.append(j.get("actor"))
                keeper.append(j.get("keeper"))
                x.append(np.nan if loc[0] is None else loc[0])
                y.append(np.nan if loc[1] is None else loc[1])
    n = np.asarray(n, dtype="int64")
    df = pd.DataFrame({
        "match_id": np.repeat(raw["match_id"].to_numpy(), n),
        "event_uuid": np.repeat(_uuid(raw["event_uuid"]).to_numpy(dtype=object), n),
        "jugador_idx": np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n),
        "teammate": pd.array(teammate, dtype="boolean"), "actor": pd.array(actor, dtype="boolean"),
        "keeper": pd.array(keeper, dtype="boolean"), "x": np.frombuffer(x, dtype="float64"),
        "y": np.frombuffer(y, dtype="float64"),
    })
    del n, teammate, actor, keeper, x, y
    with _contexto("frames_360 (union con eventos por match_id, event_uuid)"):
        llave = pd.DataFrame({"match_id": df["match_id"].astype("Int64"), "event_uuid": df["event_uuid"].astype("string")})
        ev = _de_eventos(llave, eventos, "es_equipo_analizado")
    del llave
    # del equipo analizado si el evento lo es y el jugador es compañero, o si ninguno de los dos; nulo si falta algo
    esp = {"es_equipo_analizado": df["teammate"] == ev}
    del ev
    return aplicar_contrato(df, ctx, "frames_360", esp).sort_values(LLAVES["frames_360"]).reset_index(drop=True)


@_contexto("frames_360_evento")
def limpiar_frames_360_evento(raw, eventos, partidos, ctx):
    with _contexto("frames_360_evento (union con eventos por match_id, event_uuid)"):
        llave = pd.DataFrame({"match_id": raw["match_id"].astype("Int64"), "event_uuid": _uuid(raw["event_uuid"])})
        equipo = _de_eventos(llave, eventos, "team_id").astype(object)
    # el rival es el otro equipo del partido, no cualquier team_id distinto al del evento
    p = partidos.set_index("match_id")
    local = raw["match_id"].map(p["home_team_id"].astype(object))
    visita = raw["match_id"].map(p["away_team_id"].astype(object))
    n_eq, n_riv = [], []
    for mid, t, loc, vis, vp in zip(raw["match_id"], equipo, local, visita, raw["visible_player_counts"]):
        with _contexto(f"frames_360_evento.visible_player_counts, match_id {mid}"):
            conteos = _lista(vp)
            if len(conteos) == 0 or pd.isna(t):
                n_eq.append(pd.NA)
                n_riv.append(pd.NA)
                continue
            rival = None
            if not (pd.isna(loc) or pd.isna(vis)):
                rival = vis if t == loc else (loc if t == vis else None)
            n_eq.append(sum(c["count"] for c in conteos if c["team_id"] == t))
            n_riv.append(pd.NA if rival is None else sum(c["count"] for c in conteos if c["team_id"] == rival))
    with _contexto("frames_360_evento.visible_area"):
        area = raw["visible_area"].map(lambda v: _shoelace(_json(v))).astype("float64")
    esp = {
        "visible_area_yd2": area,
        "n_visibles_equipo": pd.Series(n_eq, index=raw.index).astype("Int64"),
        "n_visibles_rival": pd.Series(n_riv, index=raw.index).astype("Int64"),
    }
    return aplicar_contrato(raw, ctx, "frames_360_evento", esp).sort_values(LLAVES["frames_360_evento"]).reset_index(drop=True)


def _extraer_lineups(raw):
    # Una fila por jugador (alineaciones) y una por tramo de posicion (posiciones), desde el JSON de `lineup`.
    jugadores, tramos = [], []
    for mid, tid, tname, lineup in zip(raw["match_id"], raw["team_id"], raw["team_name"], raw["lineup"]):
        with _contexto(f"alineaciones/posiciones (lineup), match_id {mid}, team_id {tid}"):
            for j in _lista(lineup):
                stats, pais = j.get("stats") or {}, j.get("country") or {}
                hops = (j.get("skills") or {}).get("HOPS") or {}
                jugadores.append({
                    "match_id": mid, "team_id": tid, "team_name": tname, "player_id": j["player_id"],
                    "player_name": j.get("player_name"), "player_nickname": j.get("player_nickname"),
                    "birth_date": j.get("birth_date"), "player_gender": j.get("player_gender"),
                    "player_height": j.get("player_height"), "player_weight": j.get("player_weight"),
                    "jersey_number": j.get("jersey_number"), "country_id": pais.get("id"), "country_name": pais.get("name"),
                    **{f"stats_{k}": stats.get(k) for k in ("goals", "assists", "own_goals", "penalties_scored",
                                                           "penalties_missed", "penalties_saved")},
                    "skills_hops_rating": hops.get("rating"), "skills_hops_raw_rating": hops.get("raw_rating"),
                })
                for i, pos in enumerate(j.get("positions") or []):
                    tramos.append({"match_id": mid, "team_id": tid, "player_id": j["player_id"], "posicion_idx": i,
                                   **{k: pos.get(k) for k in COLS_TRAMO}})
    tramos = pd.DataFrame(tramos, columns=["match_id", "team_id", "player_id", "posicion_idx", *COLS_TRAMO])
    return pd.DataFrame(jugadores), tramos


@_contexto("alineaciones/posiciones")
def limpiar_alineaciones_y_posiciones(match_ids, ctx):
    jugadores, tramos = _extraer_lineups(leer_raw("lineups", match_ids))
    return (aplicar_contrato(jugadores, ctx, "alineaciones", {}).sort_values(LLAVES["alineaciones"]).reset_index(drop=True),
            aplicar_contrato(tramos, ctx, "posiciones", {}).sort_values(LLAVES["posiciones"]).reset_index(drop=True))


def limpiar_stats(tabla, match_ids, ctx):
    # El crudo se llama igual que la tabla; account_id no esta en el contrato, asi que aplicar_contrato lo descarta.
    with _contexto(tabla):
        raw = leer_raw(tabla, match_ids)
        return aplicar_contrato(raw, ctx, tabla, {}).sort_values(LLAVES[tabla]).reset_index(drop=True)


def revisar_cobertura(t):
    # Lista de huecos por partido: filas en las tablas por partido, ids de equipo no nulos, los mismos 2 equipos
    # (local y visitante) en alineaciones y team_match_stats, y eventos con es_equipo_analizado no nulo.
    filas = {n: t[n]["match_id"].value_counts()
             for n in ("eventos", "frames_360", "frames_360_evento", "player_match_stats")}
    equipos = {n: t[n][["match_id", "team_id"]].dropna().drop_duplicates().groupby("match_id")["team_id"].agg(set)
               for n in ("alineaciones", "team_match_stats")}
    ev = t["eventos"]
    con_equipo = ev.loc[ev["es_equipo_analizado"].notna().to_numpy(dtype=bool), "match_id"].value_counts()
    huecos = []
    for r in t["partidos"][["match_id", "home_team_id", "away_team_id", "equipo_id"]].itertuples(index=False):
        mid = r.match_id
        faltas = [f"sin filas en {n}" for n, s in filas.items() if s.get(mid, 0) == 0]
        faltas += [f"{c} nulo" for c in ("home_team_id", "away_team_id", "equipo_id") if pd.isna(getattr(r, c))]
        esperado = {int(x) for x in (r.home_team_id, r.away_team_id) if not pd.isna(x)}
        for n, s in equipos.items():
            vistos = {int(x) for x in s.get(mid, set())}
            if vistos != esperado or len(vistos) != 2:
                faltas.append(f"equipos en {n}: {sorted(vistos)}; se esperan local y visitante {sorted(esperado)}")
        if not pd.isna(r.equipo_id) and r.equipo_id not in esperado:
            faltas.append(f"equipo_id {r.equipo_id} no es local ni visitante")
        if con_equipo.get(mid, 0) == 0:
            faltas.append("sin eventos con es_equipo_analizado no nulo")
        if faltas:
            huecos.append(f"match_id {mid}: {', '.join(faltas)}")
    return huecos


def _en(hija, padre):
    # Mascara: filas de `hija` cuya llave esta en `padre` (dos DataFrames con el mismo numero de columnas, en el mismo orden y con tipos compatibles; los nombres pueden diferir).
    # Una llave hija con algun nulo cuenta como no encontrada.
    completa = hija.notna().all(axis=1).to_numpy()
    return pd.MultiIndex.from_frame(hija).isin(pd.MultiIndex.from_frame(padre)) & completa


def reporte_calidad(t, ctx):
    # Una fila por tabla. filas_descartadas = filas_crudas - filas, y solo puede venir de C18 (partidos excluidos).
    # padre y huerfanos_por_padre van en el orden de PADRES; huerfanos cuenta las filas que faltan en algun padre.
    filas = []
    for nombre, df in t.items():
        llave = LLAVES[nombre]
        padres, por_padre, huerfanos = [], [], pd.NA
        if nombre in PADRES:
            sueltas = np.zeros(len(df), dtype=bool)
            for padre, cols_hija, cols_padre in PADRES[nombre]:
                fuera = ~_en(df[list(cols_hija)], t[padre][list(cols_padre)])
                sueltas |= fuera
                padres.append(padre)
                por_padre.append(f"{padre}: {int(fuera.sum())}")
            huerfanos = int(sueltas.sum())
        crudas = ctx["crudas"][nombre]
        filas.append({"tabla": nombre, "filas_crudas": crudas, "filas": len(df), "filas_descartadas": crudas - len(df),
                      "columnas": len(df.columns), "llave": ", ".join(llave),
                      "llaves_duplicadas": int(df.duplicated(llave).sum()), "padre": "; ".join(padres),
                      "huerfanos": huerfanos, "huerfanos_por_padre": "; ".join(por_padre),
                      "columnas_creadas_vacias": " ".join(ctx["vacias"].get(nombre, []))})
    return pd.DataFrame(filas).astype({"huerfanos": "Int64"})


def _pct(parte, total):
    return (100 * parte / total.where(total > 0)).round(2)


def reporte_cobertura_360(t):
    # Por partido: eventos con frame en total, sin administrativos y del equipo analizado; frames sin conteo; y
    # frames_umbral_provisional, que aplica la regla provisional de Lee para C19 (actor visible y al menos
    # UMBRAL_C19 jugadores visibles). Ese umbral no filtra nada: es solo informativo y cada metrica pone el suyo.
    ev, fe, f360 = t["eventos"], t["frames_360_evento"], t["frames_360"]
    ids = t["partidos"]["match_id"]
    con_frame = _en(ev[["match_id", "id"]], fe[["match_id", "event_uuid"]])
    tactico = ~ev["es_administrativo"].fillna(False).to_numpy(dtype=bool)
    del_equipo = ev["es_equipo_analizado"].fillna(False).to_numpy(dtype=bool)
    sin_conteo = fe["n_visibles_equipo"].isna() | fe["n_visibles_rival"].isna()
    actor = f360.loc[f360["actor"].fillna(False).to_numpy(dtype=bool), ["match_id", "event_uuid"]]
    umbral = (_en(fe[["match_id", "event_uuid"]], actor)
              & (fe["n_visibles_equipo"] + fe["n_visibles_rival"] >= UMBRAL_C19).fillna(False).to_numpy(dtype=bool))
    por_partido = lambda mascara: pd.Series(mascara, index=ev.index).groupby(ev["match_id"]).sum()
    out = pd.DataFrame({
        "eventos": ev.groupby("match_id").size(),
        "eventos_con_frame": por_partido(con_frame),
        "eventos_tacticos": por_partido(tactico),
        "tacticos_con_frame": por_partido(tactico & con_frame),
        "eventos_equipo_analizado": por_partido(del_equipo),
        "equipo_con_frame": por_partido(del_equipo & con_frame),
        "frames_sin_conteo": sin_conteo.groupby(fe["match_id"]).sum(),
        "frames_umbral_provisional": pd.Series(umbral, index=fe.index).groupby(fe["match_id"]).sum(),
    }).reindex(ids).fillna(0).astype("int64")
    out.insert(2, "pct_con_frame", _pct(out["eventos_con_frame"], out["eventos"]))
    out.insert(4, "pct_tacticos_con_frame", _pct(out.pop("tacticos_con_frame"), out["eventos_tacticos"]))
    out.insert(6, "pct_equipo_con_frame", _pct(out.pop("equipo_con_frame"), out["eventos_equipo_analizado"]))
    return out.rename_axis("match_id").reset_index()


def _bloqueados(salida, archivos):
    # Destinos que ya existen y no se pueden abrir para escribir (en Windows, abiertos en Excel o en otro proceso).
    # Es heuristico: no detecta procesos que solo impiden borrar; el respaldo es conservar la carpeta temporal.
    malos = []
    for archivo in archivos:
        destino = salida / archivo
        if destino.exists():
            try:
                with open(destino, "r+b"):
                    pass
            except OSError as e:
                malos.append(f"{archivo} ({e.strerror or e})")
    return malos


def escribir(salida, tablas, csvs):
    # Escribe todo en una carpeta temporal dentro de `salida` y despues reemplaza archivo por archivo.
    # La carpeta temporal solo se borra si no se reemplazo nada o si se reemplazo todo; a medias se conserva.
    # Las temporales viejas de corridas anteriores se borran solo despues de un reemplazo completo.
    archivos = [f"{n}.parquet" for n in tablas] + list(csvs)
    try:
        salida.mkdir(parents=True, exist_ok=True)
        # las tablas del contrato que escriben otros scripts (las auxiliares de 02_auxiliares.py) no son ajenas
        del_contrato = {f"{t}.parquet" for t in contrato.cargar()["tabla"].unique()}
        ajenos = sorted(x.name for x in salida.glob("*.parquet") if x.name not in archivos and x.name not in del_contrato)
        if ajenos:
            print(f"AVISO: {salida} tiene parquet que no son tablas del contrato (no se borran): {ajenos}", file=sys.stderr)
        tmp = Path(tempfile.mkdtemp(prefix=".tmp_limpieza_", dir=salida))
    except OSError as e:
        raise ErrorLimpieza(f"no se pudo preparar {salida}: {e}") from e
    reemplazados = []
    try:
        try:
            for nombre, df in tablas.items():
                df.to_parquet(tmp / f"{nombre}.parquet", compression="zstd", index=False)
            for archivo, df in csvs.items():
                df.to_csv(tmp / archivo, index=False)
        except (OSError, *ERRORES_DATOS) as e:
            raise ErrorLimpieza(f"no se pudo escribir en la carpeta temporal {tmp}; no se reemplazo nada: "
                                f"{type(e).__name__}: {e}") from e
        bloqueados = _bloqueados(salida, archivos)
        if bloqueados:
            raise ErrorLimpieza(f"no se reemplazo nada en {salida}: estos destinos estan bloqueados o no se pueden "
                                f"escribir: {bloqueados}. Cierralos (por ejemplo en Excel) y vuelve a correr.")
        for archivo in archivos:
            try:
                os.replace(tmp / archivo, salida / archivo)
            except OSError as e:
                if not reemplazados:
                    raise ErrorLimpieza(f"no se reemplazo nada en {salida}: fallo {archivo} ({e})") from e
                raise ErrorLimpieza(
                    f"el reemplazo quedo a medias en {salida}: ya se reemplazaron {reemplazados}; faltan "
                    f"{archivos[len(reemplazados):]} ({e}). Los que faltan siguen en la carpeta temporal {tmp}, que no "
                    "se borro: copialos a mano o vuelve a correr la limpieza.") from e
            except KeyboardInterrupt:
                if reemplazados:
                    print(f"AVISO: interrumpido a medias; ya se reemplazaron {reemplazados} y el resto sigue en la "
                          f"carpeta temporal {tmp}, que no se borro.", file=sys.stderr)
                raise
            reemplazados.append(archivo)
    finally:
        if not 0 < len(reemplazados) < len(archivos):
            shutil.rmtree(tmp, ignore_errors=True)
            if tmp.exists():
                print(f"AVISO: no se pudo borrar la carpeta temporal {tmp}", file=sys.stderr)
    for vieja in salida.glob(".tmp_limpieza_*"):
        if vieja.is_dir() and vieja != tmp:
            shutil.rmtree(vieja, ignore_errors=True)
            if vieja.exists():
                print(f"AVISO: no se pudo borrar la carpeta temporal vieja {vieja}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--solo-partido", type=int, metavar="MATCH_ID", help="limpia un partido y escribe en data/interim/muestra/")
    args = p.parse_args()
    ids = [args.solo_partido] if args.solo_partido is not None else None
    salida = INTERIM / "muestra" if ids else INTERIM
    ctx = {"contrato": contrato.cargar(), "vacias": {}, "crudas": {}}

    try:
        partidos, excluidos = limpiar_partidos(ids, ctx)
        for mid, campo, valor in excluidos.itertuples(index=False):
            print(f"EXCLUIDO match_id {mid}: {campo} = {valor!r}")
        if partidos.empty:
            if ids is None:
                raise ErrorLimpieza(f"ningun partido pasa los filtros de calidad ({len(set(excluidos['match_id']))} "
                                    "excluidos, ver arriba); no hay nada que limpiar")
            if excluidos.empty:
                print(f"ERROR: match_id {ids[0]} no esta en partidos.parquet", file=sys.stderr)
            else:
                print(f"ERROR: match_id {ids[0]} no pasa los filtros de calidad (ver arriba)", file=sys.stderr)
            return 2
        if ids is None:
            ids = partidos["match_id"].tolist()
        eventos = limpiar_eventos(ids, partidos, ctx)
        raw360 = leer_raw("frames_360", ids)
        resultado = {
            "partidos": partidos,
            "eventos": eventos,
            "frames_360": limpiar_frames_360(raw360, eventos, ctx),
            "frames_360_evento": limpiar_frames_360_evento(raw360, eventos, partidos, ctx),
        }
        del raw360
        resultado["alineaciones"], resultado["posiciones"] = limpiar_alineaciones_y_posiciones(ids, ctx)
        resultado["team_match_stats"] = limpiar_stats("team_match_stats", ids, ctx)
        resultado["player_match_stats"] = limpiar_stats("player_match_stats", ids, ctx)
        # la linea base de la liga no se filtra por los partidos de Jardine; solo la muestra se recorta a un partido
        resultado["team_match_stats_liga"] = limpiar_stats(
            "team_match_stats_liga", [args.solo_partido] if args.solo_partido is not None else None, ctx)
    except ErrorLimpieza as e:
        print(f"ERROR: {e}\nNo se escribio nada.", file=sys.stderr)
        return 1

    malos = {}
    for nombre, df in resultado.items():
        informe = contrato.validar(df, nombre)
        if not informe["ok"]:
            malos[nombre] = {k: informe[k] for k in ("faltantes", "sobrantes", "tipo_incorrecto", "nulos_con_relleno")
                             if informe[k]}
    if malos:
        for nombre, detalle in malos.items():
            print(f"ERROR: {nombre} no cumple el contrato: {detalle}", file=sys.stderr)
        print("No se escribio nada.", file=sys.stderr)
        return 1
    huecos = revisar_cobertura(resultado)
    if huecos:
        print(f"ERROR: {len(huecos)} partidos sin cobertura completa:", file=sys.stderr)
        for h in huecos:
            print(f"   {h}", file=sys.stderr)
        print("No se escribio nada.", file=sys.stderr)
        return 1
    calidad = reporte_calidad(resultado, ctx)
    sucias = calidad[(calidad["llaves_duplicadas"] > 0) | (calidad["huerfanos"].fillna(0) > 0)]
    if not sucias.empty:
        print(f"ERROR: {len(sucias)} tablas con llaves duplicadas o huerfanos:", file=sys.stderr)
        for r in sucias.itertuples(index=False):
            print(f"   {r.tabla}: {r.llaves_duplicadas} llaves duplicadas en ({r.llave}); "
                  f"huerfanos {r.huerfanos_por_padre or 'sin padre'}", file=sys.stderr)
        print("No se escribio nada.", file=sys.stderr)
        return 1

    cobertura = reporte_cobertura_360(resultado)
    try:
        escribir(salida, resultado, {"partidos_excluidos.csv": excluidos, "calidad_limpieza.csv": calidad,
                                     "cobertura_360_por_partido.csv": cobertura})
    except ErrorLimpieza as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"Calidad: {int(calidad['llaves_duplicadas'].sum())} llaves duplicadas, "
          f"{int(calidad['huerfanos'].sum())} huerfanos, {len(excluidos['match_id'].unique())} partidos excluidos")
    total, con = int(cobertura["eventos"].sum()), int(cobertura["eventos_con_frame"].sum())
    pct = f"{100 * con / total:.1f}%" if total else "sin eventos"
    print(f"360: {con:,} de {total:,} eventos con frame ({pct}), "
          f"{int(cobertura['frames_sin_conteo'].sum()):,} frames sin conteo; "
          f"{int(cobertura['frames_umbral_provisional'].sum()):,} frames cumplen la regla provisional de Lee para C19 "
          f"(actor visible y al menos {UMBRAL_C19} visibles; solo informativa, no filtra nada)")
    print(f"Escrito en {salida.relative_to(ROOT).as_posix()}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
