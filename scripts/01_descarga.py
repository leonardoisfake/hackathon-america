"""Descarga los partidos de un entrenador y los guarda en parquet crudo (por defecto, Jardine con America).

Uso:
    python scripts/01_descarga.py                          # los 91 partidos de Jardine
    python scripts/01_descarga.py --linea-base             # ademas, team_match_stats de toda la liga
    python scripts/01_descarga.py --solo-partido 3995374   # prueba con un partido
    python scripts/01_descarga.py --limite 3               # prueba con los primeros 3 partidos

Salida con los ids por defecto: data/raw/parquet/ (partidos, events, frames_360, lineups,
team_match_stats, player_match_stats y, con --linea-base, team_match_stats_liga) y
docs/inventario_descarga.md. Con otros ids: data/raw/parquet/m{manager}_t{team}/ y
docs/inventario_descarga_m{manager}_t{team}.md. En modo prueba: data/raw/parquet_prueba/ y
docs/inventario_descarga_prueba.md.

Un parquet de mas de 50 MB se parte por torneo (events__Apertura_2023.parquet), porque GitHub
avisa desde ese tamano. Se puede reanudar: sb_api no vuelve a pedir lo que ya esta en data/raw/*.json.
Las listas y dicts quedan como texto JSON; la limpieza los parsea.

Codigos de salida: 0 bien; 1 hubo fallos o el resultado no cuadra con lo esperado;
2 credenciales faltantes o rechazadas, o filtro vacio.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

# sb_api.py esta en la raiz del proyecto, no en scripts/.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sb_api  # noqa: E402

COMP_ID = 73  # Liga MX
ETAPAS_REGULARES = {1, 42, 44}  # competition_stage.id: Regular Season, Apertura y Clausura; el resto es liguilla
ETAPA_PLAY_IN = 2
MANAGER_DEFAULT, TEAM_DEFAULT = 1000116, 1229
ESPERADO_DEFAULT = {"partidos": 91, "liguilla": 25, "es_final": 8}
PARQUET_DIR = ROOT / "data" / "raw" / "parquet"
PARQUET_PRUEBA_DIR = ROOT / "data" / "raw" / "parquet_prueba"
DOCS_DIR = ROOT / "docs"
LIMITE_MB = 50  # GitHub avisa desde 50 MB por archivo
ZSTD_NIVEL = 9

# endpoint -> (ruta, funcion de sb_api)
ENDPOINTS_PARTIDO = {
    "events": ("v11/events/{}", sb_api.events),
    "frames_360": ("v2/360-frames/{}", sb_api.frames_360),
    "lineups": ("v5/lineups/{}", sb_api.lineups),
    "team_match_stats": ("v4/matches/{}/team-stats", sb_api.team_match_stats),
    "player_match_stats": ("v8/matches/{}/player-stats", sb_api.player_match_stats),
}

# tabla -> {columna: motivo} de columnas que se guardaron como texto
CONVERTIDAS = {}


def log(msg):
    print(msg, flush=True)


def etiqueta_torneo(fecha):
    # julio a diciembre es Apertura, enero a junio Clausura (plan 7.3.17)
    f = pd.to_datetime(fecha)
    return f"{'Apertura' if f.month >= 7 else 'Clausura'} {f.year}"


def slug_torneo(torneo):
    return re.sub(r"[^A-Za-z0-9]+", "_", torneo).strip("_")


def _registrar(tabla, col, motivo):
    CONVERTIDAS.setdefault(tabla, {}).setdefault(col, motivo)


def a_texto_json(df, tabla):
    # Pasa las columnas con listas o dicts a texto JSON.
    for c in df.columns:
        if df[c].dtype == object and df[c].map(lambda v: isinstance(v, (list, dict))).any():
            df[c] = df[c].map(lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
            _registrar(tabla, c, "lista o dict -> texto JSON")
    return df


def _serializar(v):
    if v is None or (isinstance(v, float) and v != v):
        return None
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)


def a_arrow(df, tabla):
    # Convierte a tabla arrow; las columnas de tipos mezclados pasan a texto (json.dumps en lo que no es texto).
    try:
        return pa.Table.from_pandas(df, preserve_index=False)
    except (pa.ArrowInvalid, pa.ArrowTypeError):
        for c in df.columns:
            try:
                pa.array(df[c])
            except (pa.ArrowInvalid, pa.ArrowTypeError):
                df[c] = df[c].map(_serializar)
                _registrar(tabla, c, "tipos mezclados -> texto")
        return pa.Table.from_pandas(df, preserve_index=False)


def unir_tablas(tablas, tabla):
    # Une las tablas de varios partidos; si una columna cambia de tipo entre partidos, la pasa a texto.
    try:
        return pa.concat_tables(tablas, promote_options="permissive")
    except (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError):
        tipos = {}
        for t in tablas:
            for campo in t.schema:
                tipos.setdefault(campo.name, set()).add(str(campo.type))
        conflicto = {n for n, ts in tipos.items() if len(ts - {"null"}) > 1}
        nuevas = []
        for t in tablas:
            for n in conflicto & set(t.schema.names):
                i = t.schema.get_field_index(n)
                t = t.set_column(i, n, t.column(i).cast(pa.string()))
            nuevas.append(t)
        for n in conflicto:
            _registrar(tabla, n, "tipos distintos entre partidos -> texto")
        return pa.concat_tables(nuevas, promote_options="permissive")


def aplanar(registros, match_id, tabla, extra=None):
    df = pd.json_normalize(registros, sep=".")
    df["match_id"] = match_id
    df = df[["match_id"] + [c for c in df.columns if c != "match_id"]]
    for k, v in (extra or {}).items():
        df[k] = v
    return a_texto_json(df, tabla)


def md_tabla(df):
    if df.empty:
        return "_(vacio)_\n"
    cols = [str(c) for c in df.columns]
    filas = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in df.itertuples(index=False):
        filas.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |")
    return "\n".join(filas) + "\n"


def escribir_atomico(tabla, ruta):
    # Escribe a .tmp y luego os.replace, para no dejar parquet a medias.
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    pq.write_table(tabla, tmp, compression="zstd", compression_level=ZSTD_NIVEL)
    os.replace(tmp, ruta)
    return ruta.stat().st_size / 1e6


def escribir_tabla(nombre, tabla, salida, torneo_por_match=None):
    # Escribe nombre.parquet y, si pasa de LIMITE_MB, lo parte por torneo. Devuelve [(archivo, MB)].
    unico = salida / f"{nombre}.parquet"
    viejas = sorted(salida.glob(f"{nombre}__*.parquet"))
    mb = escribir_atomico(tabla, unico)
    if mb <= LIMITE_MB or not torneo_por_match:
        for v in viejas:
            v.unlink()
        return [(unico.name, mb)]
    unico.unlink()
    for v in viejas:
        v.unlink()
    por_torneo = pd.Series(torneo_por_match)
    salida_archivos = []
    ids = tabla.column("match_id")
    for torneo in sorted(por_torneo.unique()):
        match_ids = pa.array([int(i) for i in por_torneo[por_torneo == torneo].index])
        parte = tabla.filter(pc.is_in(ids, value_set=match_ids))
        nombre_parte = f"{nombre}__{slug_torneo(torneo)}.parquet"
        salida_archivos.append((nombre_parte, escribir_atomico(parte, salida / nombre_parte)))
    return salida_archivos


def cargar_matches_liga():
    partes = [pd.json_normalize(sb_api.matches(COMP_ID, sid), sep=".") for sid in sb_api.TEMPORADAS_RETO]
    df = pd.concat(partes, ignore_index=True)
    df["torneo"] = df["match_date"].map(etiqueta_torneo)
    df["fase"] = df["competition_stage.id"].map(lambda i: "regular" if i in ETAPAS_REGULARES else "liguilla")
    df["es_play_in"] = df["competition_stage.id"] == ETAPA_PLAY_IN
    df["es_final"] = marcar_finales(df)
    return df


def marcar_finales(df):
    """Marca los dos ultimos partidos de eliminacion directa del torneo entre el mismo par de equipos.

    No se usa la etiqueta de stage: hay Play-In marcados como Final y una vuelta de final como
    Semi-finals (plan 7.3.16).
    """
    es_final = pd.Series(False, index=df.index)
    h, a = "home_team.home_team_id", "away_team.away_team_id"
    for _, g in df[df["fase"] == "liguilla"].groupby("torneo"):
        g = g.sort_values(["match_date", "kick_off"])
        par = frozenset((g.iloc[-1][h], g.iloc[-1][a]))
        mismos = g[[frozenset((x, y)) == par for x, y in zip(g[h], g[a])]]
        es_final.loc[mismos.tail(2).index] = True
    return es_final


def _managers(r, lado):
    m = r.get(f"{lado}_team.managers")
    return m if isinstance(m, list) else []


def seleccionar_partidos(liga, manager_id, team_id):
    # Devuelve (D1, excluidos): los partidos del entrenador con el equipo que pasan los filtros de calidad, con columnas derivadas, y los descartados con su motivo.
    filas, excluidos, otros = [], [], []
    for r in liga.to_dict("records"):
        for lado, otro in (("home", "away"), ("away", "home")):
            if r[f"{lado}_team.{lado}_team_id"] != team_id:
                continue
            managers = _managers(r, lado)
            if manager_id not in [m.get("id") for m in managers]:
                otros.append((r, managers))
                continue
            motivos = []
            for campo, esperado in (("match_status", "available"), ("collection_status", "Complete"),
                                    ("play_status", "Normal"), ("match_status_360", "available")):
                if r.get(campo) != esperado:
                    motivos.append(f"{campo}={r.get(campo)}")
            if motivos:
                excluidos.append({"match_id": r["match_id"], "fecha": r["match_date"], "motivo": ", ".join(motivos)})
                continue
            rivales = _managers(r, otro)
            gf, gc = r[f"{lado}_score"], r[f"{otro}_score"]
            r = dict(r)
            r.update({
                "entrenador_id": manager_id,
                "equipo_id": team_id,
                "es_local": lado == "home",
                "rival_id": r[f"{otro}_team.{otro}_team_id"],
                "rival_nombre": r[f"{otro}_team.{otro}_team_name"],
                "entrenador_rival": " / ".join(str(m.get("name")).strip() for m in rivales),
                "entrenador_rival_id": rivales[0].get("id") if rivales else None,
                "rival_coentrenador": len(rivales) > 1,
                "goles_favor": gf,
                "goles_contra": gc,
                "resultado": "G" if gf > gc else ("E" if gf == gc else "P"),
                "coentrenador": len(managers) > 1,
            })
            filas.append(r)
    d1 = pd.DataFrame(filas)
    if not d1.empty:
        d1 = d1.sort_values(["match_date", "kick_off"]).reset_index(drop=True)
        d1["entrenador_rival_id"] = d1["entrenador_rival_id"].astype("Int64")
        # partidos del equipo dentro del periodo del entrenador pero con otro manager
        desde, hasta = d1["match_date"].min(), d1["match_date"].max()
        for r, managers in otros:
            if desde <= r["match_date"] <= hasta:
                nombres = " / ".join(str(m.get("name")).strip() for m in managers) or "sin dato"
                excluidos.append({"match_id": r["match_id"], "fecha": r["match_date"],
                                  "motivo": f"excluido: otro manager ({nombres})"})
    return d1, excluidos


def traer(clave, match_id, pausa):
    # Llama a un endpoint por partido; hace una pausa solo si hubo descarga real.
    plantilla, funcion = ENDPOINTS_PARTIDO[clave]
    nuevo = not sb_api.en_cache(plantilla.format(match_id))
    data = funcion(match_id)
    if nuevo:
        time.sleep(pausa)
    return data, nuevo


def descargar_partido(m, pausa):
    # Descarga y aplana los 5 endpoints de un partido. Devuelve (tablas, resumen).
    mid = int(m["match_id"])
    nuevo, datos = False, {}
    for clave in ENDPOINTS_PARTIDO:
        datos[clave], n = traer(clave, mid, pausa)
        nuevo = nuevo or n
    tablas = {clave: a_arrow(aplanar(data, mid, clave), clave) for clave, data in datos.items()}
    ids = {e["id"] for e in datos["events"]}
    uuids = {f["event_uuid"] for f in datos["frames_360"]}
    ruta_ev = sb_api.ruta_cache(ENDPOINTS_PARTIDO["events"][0].format(mid))
    resumen = {
        "eventos": len(datos["events"]),
        "frames_360": len(datos["frames_360"]),
        "eventos_con_360": len(ids & uuids),
        "descargado": datetime.fromtimestamp(ruta_ev.stat().st_mtime).strftime("%Y-%m-%d"),
        "desde_cache": not nuevo,
    }
    return tablas, resumen


def descargar_linea_base(liga, limite_ids, pausa, salida):
    # team_match_stats de todos los partidos available + Complete + Normal. Devuelve (info, fallidos, excluidos).
    disponibles = liga[liga["match_status"] == "available"]
    excl = []
    ok_mask = (disponibles["collection_status"] == "Complete") & (disponibles["play_status"] == "Normal")
    for r in disponibles[~ok_mask].to_dict("records"):
        excl.append({"match_id": r["match_id"], "fecha": r["match_date"],
                     "motivo": f"linea base: collection_status={r['collection_status']}, play_status={r['play_status']}"})
    base = disponibles[ok_mask]
    if limite_ids is not None:
        base = base[base["match_id"].isin(limite_ids)]
    tablas, fallidos = [], []
    n = len(base)
    log(f"\nLinea base: team_match_stats de {n} partidos ({len(excl)} excluidos por status)")
    t0 = time.time()
    for i, r in enumerate(base.to_dict("records"), start=1):
        mid = int(r["match_id"])
        nuevo = not sb_api.en_cache(f"v4/matches/{mid}/team-stats")
        try:
            data = sb_api.team_match_stats(mid)
        except (sb_api.SBHTTPError, OSError) as e:
            fallidos.append({"match_id": mid, "fecha": r["match_date"], "motivo": f"linea base: {e}"})
            log(f"  [{i}/{n}] {mid} FALLO: {e}")
            continue
        extra = {"torneo": r["torneo"], "fase": r["fase"], "es_play_in": bool(r["es_play_in"]),
                 "es_final": bool(r["es_final"]), "match_date": r["match_date"], "match_week": r.get("match_week")}
        tablas.append(a_arrow(aplanar(data, mid, "team_match_stats_liga", extra), "team_match_stats_liga"))
        if nuevo:
            time.sleep(pausa)
        if i % 200 == 0 or i == n:
            log(f"  [{i}/{n}] {time.time() - t0:.0f}s")
    info = None
    if tablas:
        t = unir_tablas(tablas, "team_match_stats_liga")
        archivos = escribir_tabla("team_match_stats_liga", t, salida)
        log(f"  team_match_stats_liga: {t.num_rows} filas, {t.num_columns} columnas")
        info = (t.num_rows, t.num_columns, archivos, len(excl))
    return info, fallidos, excl


def escribir_inventario(ruta, args, modo, d1, excluidos, fallidos, resumenes, conteos, base_info, chequeo):
    L = [f"# Inventario de descarga{' (prueba)' if modo == 'prueba' else ''}", ""]
    L.append(f"- Fecha de ejecucion: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    L.append(f"- Entrenador `manager_id` {args.manager_id}, equipo `team_id` {args.team_id}")
    L.append(f"- Temporadas: {', '.join(str(s) for s in sb_api.TEMPORADAS_RETO)}")
    L.append(f"- Modo: {modo}")
    L.append(f"- Partidos en D1: {len(d1)}")
    L.append("")
    if chequeo is not None:
        L.append("## Esperado contra obtenido")
        L.append("")
        L.append(md_tabla(pd.DataFrame(chequeo)))
        if any(c["estado"] != "ok" for c in chequeo):
            L.append("**ADVERTENCIA: el resultado no cuadra con lo esperado.**\n")
    L.append("## Filas por tabla")
    L.append("")
    tabla = pd.DataFrame([{"tabla": k, "filas": v[0], "columnas": v[1], "mb": f"{sum(a[1] for a in v[2]):.1f}",
                           "archivos": ", ".join(f"{a[0]} ({a[1]:.1f} MB)" for a in v[2])} for k, v in conteos.items()])
    L.append(md_tabla(tabla))
    if base_info:
        L.append(f"Linea base: {base_info[0]} filas, {base_info[1]} columnas, "
                 f"{', '.join(f'{a[0]} ({a[1]:.1f} MB)' for a in base_info[2])}. "
                 f"Excluidos por Complete/Normal: {base_info[3]} (se listan abajo si los hay).\n")
    L.append("## Partidos por torneo y fase")
    L.append("")
    if len(d1):
        ct = pd.crosstab(d1["torneo"], d1["fase"]).reset_index()
        ct["es_final"] = ct["torneo"].map(d1.groupby("torneo")["es_final"].sum())
        L.append(md_tabla(ct))
    L.append("## Cobertura 360")
    L.append("")
    if resumenes:
        tot_ev = sum(r["eventos"] for r in resumenes.values())
        tot_360 = sum(r["eventos_con_360"] for r in resumenes.values())
        pcts = [100 * r["eventos_con_360"] / r["eventos"] for r in resumenes.values() if r["eventos"]]
        L.append(f"- Eventos con frame 360 (`id` = `event_uuid`): {tot_360} de {tot_ev} ({100 * tot_360 / tot_ev:.1f}%)")
        L.append(f"- Por partido: minimo {min(pcts):.1f}%, maximo {max(pcts):.1f}%")
        L.append("")
    L.append("## Columnas convertidas a texto")
    L.append("")
    if CONVERTIDAS:
        filas = [{"tabla": t, "columna": c, "motivo": m} for t, cols in CONVERTIDAS.items() for c, m in cols.items()]
        L.append(md_tabla(pd.DataFrame(filas)))
    else:
        L.append("Ninguna.\n")
    L.append("## Partidos excluidos o fallidos")
    L.append("")
    exc = pd.DataFrame(excluidos + fallidos)
    L.append(md_tabla(exc) if len(exc) else "Ninguno.\n")
    L.append("## Detalle por partido")
    L.append("")
    det = []
    for r in d1.to_dict("records"):
        s = resumenes.get(int(r["match_id"]))
        if s is None:
            continue
        det.append({
            "match_id": r["match_id"], "fecha": r["match_date"], "torneo": r["torneo"], "fase": r["fase"],
            "es_final": r["es_final"], "rival": r["rival_nombre"], "res": f"{r['goles_favor']}-{r['goles_contra']}",
            "eventos": s["eventos"], "frames": s["frames_360"],
            "pct_360": f"{100 * s['eventos_con_360'] / s['eventos']:.1f}" if s["eventos"] else "",
            "last_updated_360": r.get("last_updated_360"), "descargado": s["descargado"],
        })
    L.append(md_tabla(pd.DataFrame(det)))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n".join(L), encoding="utf-8")


def parsear():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--manager-id", type=int, default=MANAGER_DEFAULT, help="default: Andre Jardine")
    p.add_argument("--team-id", type=int, default=TEAM_DEFAULT, help="default: America")
    p.add_argument("--solo-partido", type=int, metavar="MATCH_ID", help="prueba con un solo partido")
    p.add_argument("--limite", type=int, metavar="N", help="prueba con los primeros N partidos")
    p.add_argument("--linea-base", action="store_true", help="descarga team_match_stats de toda la liga (D6)")
    p.add_argument("--pausa", type=float, default=0.3, help="segundos entre llamadas HTTP reales")
    return p.parse_args()


def rutas_salida(args, prueba):
    por_defecto = (args.manager_id, args.team_id) == (MANAGER_DEFAULT, TEAM_DEFAULT)
    if prueba:
        return PARQUET_PRUEBA_DIR, DOCS_DIR / "inventario_descarga_prueba.md"
    if por_defecto:
        return PARQUET_DIR, DOCS_DIR / "inventario_descarga.md"
    sufijo = f"m{args.manager_id}_t{args.team_id}"
    return PARQUET_DIR / sufijo, DOCS_DIR / f"inventario_descarga_{sufijo}.md"


def main():
    args = parsear()
    try:
        sb_api.verificar_credenciales()
    except RuntimeError:
        log("ERROR: faltan SB_USER / SB_PASS. Definelas como variables de entorno o en el archivo .env de la raiz.")
        return 2
    try:
        return correr(args)
    except sb_api.SBAuthError as e:
        log(f"ERROR: credenciales rechazadas por la API (HTTP {e.status}). Revisa SB_USER / SB_PASS.")
        return 2


def correr(args):
    prueba = args.solo_partido is not None or args.limite is not None
    modo = "prueba" if prueba else "completo"
    salida, ruta_inv = rutas_salida(args, prueba)

    log("Cargando matches de las temporadas del reto...")
    liga = cargar_matches_liga()
    d1, excluidos = seleccionar_partidos(liga, args.manager_id, args.team_id)
    if d1.empty:
        log("ERROR: ningun partido cumple el filtro (manager_id / team_id / status).")
        return 2
    if args.solo_partido is not None:
        d1 = d1[d1["match_id"] == args.solo_partido].reset_index(drop=True)
        if d1.empty:
            log(f"ERROR: el match_id {args.solo_partido} no pertenece a D1.")
            return 2
    elif args.limite is not None:
        d1 = d1.head(args.limite).reset_index(drop=True)
    n_sin_status = sum(1 for e in excluidos if "otro manager" not in e["motivo"])
    log(f"D1: {len(d1)} partidos ({n_sin_status} excluidos por status, {len(excluidos) - n_sin_status} con otro manager). Modo: {modo}")

    acum = {k: [] for k in ENDPOINTS_PARTIDO}
    resumenes, fallidos = {}, []
    n, t_inicio = len(d1), time.time()
    for i, m in enumerate(d1.to_dict("records"), start=1):
        t0 = time.time()
        mid = int(m["match_id"])
        etiqueta = f"[{i}/{n}] {mid} {m['match_date']} vs {m['rival_nombre']}"
        try:
            tablas, resumen = descargar_partido(m, args.pausa)
        except (sb_api.SBHTTPError, OSError) as e:
            fallidos.append({"match_id": mid, "fecha": m["match_date"], "motivo": f"fallo de descarga: {e}"})
            log(f"{etiqueta} FALLO: {e}")
            continue
        for k, t in tablas.items():
            acum[k].append(t)
        resumenes[mid] = resumen
        origen = "cache" if resumen["desde_cache"] else "descarga"
        log(f"{etiqueta} {origen} {time.time() - t0:.1f}s ({resumen['eventos']} eventos)")

    conteos = {}
    d1_ok = d1[d1["match_id"].isin(resumenes)].copy()
    torneo_por_match = dict(zip(d1_ok["match_id"], d1_ok["torneo"]))
    tabla_partidos = a_arrow(a_texto_json(d1_ok.copy(), "partidos"), "partidos")
    _guardar(conteos, "partidos", tabla_partidos, salida, torneo_por_match)
    for k, ts in acum.items():
        if ts:
            _guardar(conteos, k, unir_tablas(ts, k), salida, torneo_por_match)

    base_info, excl_base = None, []
    if args.linea_base:
        ids = set(d1["match_id"]) if prueba else None
        base_info, f_base, excl_base = descargar_linea_base(liga, ids, args.pausa, salida)
        fallidos += f_base

    chequeo = None
    if not prueba and (args.manager_id, args.team_id) == (MANAGER_DEFAULT, TEAM_DEFAULT):
        obtenido = {"partidos": len(d1_ok), "liguilla": int((d1_ok["fase"] == "liguilla").sum()),
                    "es_final": int(d1_ok["es_final"].sum())}
        chequeo = [{"concepto": k, "esperado": ESPERADO_DEFAULT[k], "obtenido": obtenido[k],
                    "estado": "ok" if obtenido[k] == ESPERADO_DEFAULT[k] else "NO CUADRA"} for k in ESPERADO_DEFAULT]

    escribir_inventario(ruta_inv, args, modo, d1_ok, excluidos + excl_base, fallidos, resumenes, conteos, base_info, chequeo)
    log(f"\nListo en {time.time() - t_inicio:.0f}s. Parquet en {salida.relative_to(ROOT).as_posix()}/, inventario en {ruta_inv.relative_to(ROOT).as_posix()}")
    codigo = 0
    if fallidos:
        log(f"ATENCION: {len(fallidos)} fallos; vuelve a correr el script para reintentar (la cache evita repetir lo ya bajado).")
        codigo = 1
    if chequeo and any(c["estado"] != "ok" for c in chequeo):
        log("ADVERTENCIA: el resultado no cuadra con lo esperado (91 partidos, 25 de liguilla, 8 con es_final):")
        for c in chequeo:
            log(f"  {c['concepto']}: esperado {c['esperado']}, obtenido {c['obtenido']}")
        codigo = 1
    return codigo


def _guardar(conteos, nombre, tabla, salida, torneo_por_match):
    archivos = escribir_tabla(nombre, tabla, salida, torneo_por_match)
    detalle = ", ".join(f"{a} {mb:.1f} MB" for a, mb in archivos)
    log(f"  {nombre}: {tabla.num_rows} filas, {tabla.num_columns} columnas -> {detalle}")
    conteos[nombre] = (tabla.num_rows, tabla.num_columns, archivos)


if __name__ == "__main__":
    sys.exit(main())
