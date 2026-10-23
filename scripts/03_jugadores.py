"""Bloque de jugadores: role_group, minutos, formación por periodo, onces iniciales y cambios.

Genera tablas procesadas que explican la participación e impacto táctico de los jugadores:
1. minutos_jugados: Minutos reales en cancha por jugador, ajustando el reloj corrido a los periodos.
2. formacion_por_periodo: La táctica predominante (mayor % de minutos) por mitad de partido.
3. onces_iniciales: El XI titular alineado en cada partido y los cambios respecto al juego anterior.
4. titularidades: Porcentaje de partidos en los que cada jugador inició como titular.
5. cambios_individuales: Registro exacto de quién entra, quién sale, sus roles (ej. defensa por medio) y el contexto.
6. momentos_de_cambio: Agrupación de sustituciones simultáneas en "ventanas" tácticas.
7. cambio_en_rendimiento: Evolución del partido evaluando 15 minutos ANTES y 15 minutos DESPUÉS de un cambio.
8. resumen_rendimiento: Intervalos de confianza sobre el impacto de los cambios en xG, OBV y Posesión.
9. resumen_cambios: Tendencias del DT al realizar sustituciones (minutos típicos, estado del marcador).

Uso:
    python scripts/03_jugadores.py --solo-partido 3995374   # procesa una muestra
    python scripts/03_jugadores.py                          # procesa toda la liga
    python scripts/03_jugadores.py --ver                    # imprime tablas de resumen en consola
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from contrato import ADMINISTRATIVOS  # noqa: E402

INICIO_PERIODO = {1: 0.0, 2: 2700.0}
PERIODOS_VALIDOS = (1, 2)
VENTANA_S = 900          # Ventana de 15 min de evaluación pre y post cambio
MIN_VENTANA_S = 480      # Mínimo de 8 min para considerar válida una ventana de evaluación
MIN_CELDA = 15           # Mínimo de casos necesarios para desagregar métricas de rendimiento
ROJAS = ("Red Card", "Second Yellow")
GRUPOS = [(1, 1, "portero"), (2, 8, "defensa"), (9, 16, "medio"), (17, 21, "extremo_mediapunta"), (22, 25, "delantero")]

# Métricas que se evalúan 15 min antes y 15 min después de un cambio:
# xg_favor / xg_contra = Expected Goals (probabilidad de gol de los tiros generados/concedidos).
# xg_dif = Diferencia neta de Expected Goals.
# obv_equipo / obv_rival = Objective Value (valor agregado por todas las acciones con el balón).
# obv_neto = Dominio del partido medido en valor de acciones.
# posesion_eventos = Porcentaje de eventos del partido controlados por el equipo.
METRICAS = ["xg_favor", "xg_contra", "xg_dif", "obv_equipo", "obv_rival", "obv_neto", "posesion_eventos"]

COLS_EVENTOS = ["match_id", "index", "period", "timestamp", "minute", "second", "type_name", "team_id",
                "possession_team_id", "player_id", "position_id", "tactics_formation", "shot_statsbomb_xg",
                "shot_type_name", "shot_outcome_name", "obv_total_net", "foul_committed_card_name",
                "bad_behaviour_card_name", "substitution_outcome_name", "substitution_replacement_id"]
COLS_PARTIDOS = ["match_id", "match_date", "equipo_id", "es_local", "fase", "torneo"]


# ---------- utilidades ----------

def hms_a_seg(serie):
    """Convierte texto HH:MM:SS.mmm a segundos continuos."""
    s = serie.astype("string").str.strip()
    if s.isna().all():
        return pd.Series(np.nan, index=serie.index, dtype="float64")
    p = s.str.split(":", expand=True)
    h, m, seg = (pd.to_numeric(p[i], errors="coerce") for i in range(3))
    return (h * 3600 + m * 60 + seg).astype("float64")


def asignar_role_group(df, col="position_id"):
    """Clasifica position_ids granulares de StatsBomb en 5 roles macro tácticos."""
    out = df.copy()
    pid = out[col].astype("Int64")
    grupo = pd.Series(pd.NA, index=out.index, dtype="string")
    for lo, hi, nombre in GRUPOS:
        grupo = grupo.mask(pid.between(lo, hi).fillna(False).astype(bool), nombre)
    out["role_group"] = grupo
    return out


def duraciones_periodo(eventos):
    """Calcula la duración real en segundos de cada periodo usando el evento Half End."""
    he = eventos.loc[eventos["type_name"] == "Half End", ["match_id", "period", "timestamp"]].copy()
    he["dur_s"] = hms_a_seg(he["timestamp"])
    return he.groupby(["match_id", "period"], as_index=False)["dur_s"].max()


def _dict_duraciones(duraciones):
    return {(int(m), int(p)): float(d) for m, p, d in duraciones.itertuples(index=False) if pd.notna(d)}


def preparar_eventos(eventos, partidos, ctx_eventos=None):
    """Cruza eventos con metadatos del partido y establece el marcador y estado numérico oficial."""
    p = partidos[COLS_PARTIDOS]
    ev = eventos.merge(p, on="match_id", how="inner", validate="many_to_one")
    ev = ev.sort_values(["match_id", "index"]).reset_index(drop=True)
    ev["ts_s"] = hms_a_seg(ev["timestamp"])
    ev["es_eq"] = (ev["team_id"] == ev["equipo_id"]).fillna(False).astype(bool)
    juego = ev["period"].isin([1, 2, 3, 4])
    carta = ev["foul_committed_card_name"].isin(ROJAS) | ev["bad_behaviour_card_name"].isin(ROJAS)
    ev["es_roja"] = carta & juego

    if ctx_eventos is not None:
        # Usa la fuente de verdad del módulo de contexto para no tener discrepancias de rojas fuera de cancha
        cols_ctx = ["match_id", "index", "goal_diff", "score_state", "numerical_state_cat"]
        ctx_sub = ctx_eventos[[c for c in cols_ctx if c in ctx_eventos.columns]]
        ev = ev.merge(ctx_sub, on=["match_id", "index"], how="left", validate="one_to_one")
        ev["dif_goles"] = ev["goal_diff"]
        ev["score_state"] = ev["score_state"].astype("string")
        ev["numerical_state"] = ev["numerical_state_cat"].astype("string")
    else:
        # Cálculo de respaldo local
        def previos(flag):
            f = flag.astype(int)
            return f.groupby(ev["match_id"]).cumsum() - f

        gol = ((ev["type_name"] == "Shot") & (ev["shot_outcome_name"] == "Goal") & juego) | (ev["type_name"] == "Own Goal For")
        dif = previos(gol & ev["es_eq"]) - previos(gol & ~ev["es_eq"])
        sup = previos(ev["es_roja"] & ~ev["es_eq"]) - previos(ev["es_roja"] & ev["es_eq"])
        ev["dif_goles"] = dif
        ev["score_state"] = np.select([dif > 0, dif < 0], ["ganando", "perdiendo"], default="empatando")
        ev["numerical_state"] = np.select([sup > 0, sup < 0], ["superioridad", "inferioridad"], default="igualdad")

    return ev


# ---------- J1: role_group y minutos ----------

def minutos_por_tramo(posiciones, duraciones):
    """Calcula minutos exactos fragmentando participaciones que cruzan entre periodos."""
    dur = _dict_duraciones(duraciones)
    pos = posiciones.rename(columns={"from": "desde", "to": "hasta"}).copy()
    pos["desde_s"] = hms_a_seg(pos["desde"])
    pos["hasta_s"] = hms_a_seg(pos["hasta"])
    total = []
    for r in pos.itertuples(index=False):
        mid = int(r.match_id)
        if pd.isna(r.from_period) or pd.isna(r.desde_s):
            total.append(np.nan)
            continue
        fp = int(r.from_period)
        if pd.isna(r.hasta_s):
            tp = None
            jugados = [p for p in PERIODOS_VALIDOS if (mid, p) in dur]
            ultimo = max(jugados) if jugados else None
        else:
            tp = None if pd.isna(r.to_period) else int(r.to_period)
            ultimo = min(tp if tp is not None else fp, max(PERIODOS_VALIDOS))
        if ultimo is None:
            total.append(np.nan)
            continue
        seg, completo = 0.0, True
        for p in range(fp, ultimo + 1):
            if p not in INICIO_PERIODO:
                continue
            if (mid, p) not in dur:
                completo = False
                break
            ini = INICIO_PERIODO[p]
            fin = ini + dur[(mid, p)]
            lo = r.desde_s if p == fp else ini
            hi = r.hasta_s if (tp is not None and p == tp) else fin
            seg += max(0.0, min(hi, fin) - max(lo, ini))
        total.append(seg / 60 if completo else np.nan)
    pos["minutos"] = total
    return pos


def minutos_jugados(posiciones, eventos, partidos):
    """Agrega los tramos para obtener minutos totales por jugador y determina su rol principal en el partido."""
    tr = minutos_por_tramo(posiciones, duraciones_periodo(eventos))
    tr = tr.merge(partidos[["match_id", "equipo_id"]], on="match_id", validate="many_to_one")
    tr = asignar_role_group(tr[tr["team_id"] == tr["equipo_id"]])
    llave = ["match_id", "team_id", "player_id"]
    por_rol = tr.groupby(llave + ["role_group"], as_index=False)["minutos"].sum()
    total = por_rol.groupby(llave, as_index=False)["minutos"].sum()
    principal = (por_rol.sort_values("minutos", ascending=False).drop_duplicates(llave)[llave + ["role_group"]]
                 .rename(columns={"role_group": "role_principal"}))
    sin_dato = tr.groupby(llave)["minutos"].apply(lambda s: int(s.isna().sum())).rename("tramos_sin_minutos").reset_index()
    out = total.merge(principal, on=llave, how="left").merge(sin_dato, on=llave, how="left")
    return out.sort_values(llave).reset_index(drop=True), tr


def pct_minutos_ambiguos(tr):
    """Mide qué porcentaje del juego recae en posiciones tácticas difusas (carrileros y volantes de banda)."""
    amb = tr["position_id"].isin([7, 8, 12, 16])
    return float(tr.loc[amb, "minutos"].sum() / tr["minutos"].sum() * 100)


# ---------- J2a: formacion por periodo y onces ----------

def formacion_por_periodo(eventos, partidos):
    """Determina la formación base (por mayor cantidad de minutos) para cada mitad de juego."""
    dur = _dict_duraciones(duraciones_periodo(eventos))
    f = eventos[eventos["type_name"].isin(["Starting XI", "Tactical Shift"])].merge(
        partidos[["match_id", "equipo_id"]], on="match_id")
    f = f[(f["team_id"] == f["equipo_id"]) & f["period"].isin(PERIODOS_VALIDOS) & f["tactics_formation"].notna()].copy()
    f["reloj"] = f["period"].map(INICIO_PERIODO) + hms_a_seg(f["timestamp"])
    filas = []
    for mid, g in f.sort_values(["match_id", "reloj"]).groupby("match_id"):
        cambios = list(zip(g["reloj"], g["tactics_formation"].astype(int)))
        for p in PERIODOS_VALIDOS:
            if (int(mid), p) not in dur:
                continue
            ini = INICIO_PERIODO[p]
            fin = ini + dur[(int(mid), p)]
            puntos = [ini] + [t for t, _ in cambios if ini < t < fin] + [fin]
            minutos = {}
            secuencia = []
            for a, b in zip(puntos[:-1], puntos[1:]):
                vigentes = [fm for t, fm in cambios if t <= a]
                if not vigentes:
                    continue
                fm = vigentes[-1]
                minutos[fm] = minutos.get(fm, 0.0) + (b - a) / 60
                if not secuencia or secuencia[-1] != fm:
                    secuencia.append(fm)
            if not minutos:
                continue
            pred = max(minutos, key=minutos.get)
            filas.append({"match_id": int(mid), "period": p, "formacion": pred, "minutos_formacion": minutos[pred],
                          "minutos_periodo": (fin - ini) / 60, "n_formaciones": len(minutos),
                          "secuencia": ">".join(map(str, secuencia)),
                          "digitos_suman_10": sum(int(c) for c in str(pred)) == 10})
    return pd.DataFrame(filas)


def _titulares_de_tactics(tactics_lineup, eventos, partidos):
    if tactics_lineup is None or not {"match_id", "index", "player_id"} <= set(tactics_lineup.columns):
        return pd.DataFrame(columns=["match_id", "player_id"])
    xi = eventos.loc[eventos["type_name"] == "Starting XI", ["match_id", "index", "team_id"]].merge(
        partidos[["match_id", "equipo_id"]], on="match_id")
    xi = xi[xi["team_id"] == xi["equipo_id"]][["match_id", "index"]]
    return tactics_lineup.merge(xi, on=["match_id", "index"])[["match_id", "player_id"]]


def _titulares_de_posiciones(posiciones, partidos):
    pos = posiciones.merge(partidos[["match_id", "equipo_id"]], on="match_id")
    pos = pos[(pos["team_id"] == pos["equipo_id"]) & (pos["posicion_idx"] == 0)
              & pos["start_reason"].astype("string").str.contains("Starting", na=False)]
    return pos[["match_id", "player_id"]]


def onces_iniciales(posiciones, partidos, tactics_lineup=None, eventos=None):
    """Extrae la alineación inicial y calcula cuántos cambios nominales hubo frente al partido anterior."""
    t = _titulares_de_tactics(tactics_lineup, eventos, partidos)
    fuente = "tactics_lineup"
    if t.empty:
        t = _titulares_de_posiciones(posiciones, partidos)
        fuente = "posiciones"
    titulares = t.groupby("match_id")["player_id"].apply(lambda s: frozenset(int(x) for x in s))
    orden = partidos.sort_values(["match_date", "match_id"])[["match_id", "match_date", "fase", "torneo"]]
    filas, previo = [], None
    for r in orden.itertuples(index=False):
        if r.match_id not in titulares.index:
            continue
        actual = titulares[r.match_id]
        filas.append({"match_id": r.match_id, "match_date": r.match_date, "fase": r.fase, "torneo": r.torneo,
                      "n_titulares": len(actual), "cambios_vs_previo": None if previo is None else len(actual - previo),
                      "once": ",".join(map(str, sorted(actual)))})
        previo = actual
    onces = pd.DataFrame(filas)
    tit = (t.groupby("player_id")["match_id"].nunique().rename("partidos_titular").reset_index()
           .sort_values("partidos_titular", ascending=False))
    tit["pct_partidos"] = (100 * tit["partidos_titular"] / len(onces)).round(1)
    return onces, tit.reset_index(drop=True), fuente


def peso_posiciones(tramos):
    """Distribución global de minutos por position_id específico (sin agrupar)."""
    p = tramos.groupby("position_id", as_index=False)["minutos"].sum()
    p["pct_minutos"] = (100 * p["minutos"] / p["minutos"].sum()).round(2)
    return p.sort_values("pct_minutos", ascending=False).reset_index(drop=True)


# ---------- J2b: cambios ----------

def cambios_individuales(ev, posiciones):
    """Detalle de cada sustitución, estableciendo el rol táctico del que entra vs. el del que sale."""
    cam = ev[(ev["type_name"] == "Substitution") & ev["es_eq"] & ev["period"].isin([1, 2, 3, 4])].copy()
    pos = asignar_role_group(posiciones)
    primero = pos[pos["posicion_idx"] == 0].drop_duplicates(["match_id", "player_id"])
    rol_entra = {(int(m), int(j)): g for m, j, g in zip(primero["match_id"], primero["player_id"], primero["role_group"])
                 if pd.notna(g)}
    cam["role_entra"] = [rol_entra.get((int(m), int(j))) if pd.notna(j) else None
                         for m, j in zip(cam["match_id"], cam["substitution_replacement_id"])]
    cam["role_sale"] = asignar_role_group(cam, "position_id")["role_group"]
    cam["tipo_cambio"] = np.where(cam["substitution_outcome_name"].astype("string").str.contains("Injury", na=False),
                                  "lesion", "tactico")
    cols = ["match_id", "index", "period", "minute", "ts_s", "player_id", "substitution_replacement_id", "role_sale",
            "role_entra", "tipo_cambio", "score_state", "numerical_state", "dif_goles", "es_local", "fase", "torneo"]
    return cam[cols].rename(columns={"player_id": "sale_id", "substitution_replacement_id": "entra_id"}).reset_index(drop=True)


def momentos_de_cambio(cambios):
    """Agrupa sustituciones ocurridas en el mismo minuto (ej. cambio doble o triple)."""
    llave = ["match_id", "period", "minute"]
    m = cambios.sort_values(llave + ["index"]).groupby(llave, as_index=False).agg(
        idx_evento=("index", "first"), ts_s=("ts_s", "first"), n_cambios=("index", "size"),
        tipo_cambio=("tipo_cambio", lambda s: "lesion" if (s == "lesion").any() else "tactico"),
        roles_salen=("role_sale", lambda s: ",".join(s.dropna().astype(str))),
        roles_entran=("role_entra", lambda s: ",".join(s.dropna().astype(str))),
        score_state=("score_state", "first"), numerical_state=("numerical_state", "first"),
        dif_goles=("dif_goles", "first"), es_local=("es_local", "first"), fase=("fase", "first"),
        torneo=("torneo", "first"))
    return m


def _metricas_ventana(w, disponible_s):
    """
    Extrapola métricas avanzadas (xG y OBV) hacia un estándar de 15 minutos 
    para poder comparar justamente fragmentos que pudieron durar ligeramente menos.
    """
    k = VENTANA_S / disponible_s
    tiro = (w["type_name"] == "Shot") & (w["shot_type_name"] != "Penalty")
    xf = float(w.loc[tiro & w["es_eq"], "shot_statsbomb_xg"].sum()) * k
    xc = float(w.loc[tiro & ~w["es_eq"], "shot_statsbomb_xg"].sum()) * k
    of = float(w.loc[w["es_eq"], "obv_total_net"].sum()) * k
    oc = float(w.loc[~w["es_eq"], "obv_total_net"].sum()) * k
    juego = w[~w["type_name"].isin(ADMINISTRATIVOS)]
    pos = float((juego["possession_team_id"] == juego["equipo_id"]).mean()) if len(juego) else np.nan
    return {"xg_favor": xf, "xg_contra": xc, "xg_dif": xf - xc, "obv_equipo": of, "obv_rival": oc, "obv_neto": of - oc,
            "posesion_eventos": pos}


def cambio_en_rendimiento(momentos, ev, duraciones):
    """
    Mide la evolución métrica 15 minutos ANTES y 15 minutos DESPUÉS de un 'momento_de_cambio'.
    Descarta ventanas sucias (ej. expulsiones cruzadas o que cruzan finales de tiempo).
    """
    dur = _dict_duraciones(duraciones)
    por_partido = {m: g for m, g in ev.groupby("match_id")}
    filas = []
    for r in momentos.itertuples(index=False):
        fila = {c: getattr(r, c) for c in ("match_id", "period", "minute", "ts_s", "n_cambios", "tipo_cambio", "score_state",
                                           "numerical_state", "dif_goles", "es_local", "fase", "torneo")}
        d = dur.get((int(r.match_id), int(r.period)))
        motivo = None
        if r.period not in PERIODOS_VALIDOS:
            motivo = "tiempo extra"
        elif d is None:
            motivo = "sin Half End"
        elif r.tipo_cambio != "tactico":
            motivo = "lesion"
        else:
            disp_pre, disp_post = min(VENTANA_S, r.ts_s), min(VENTANA_S, d - r.ts_s)
            if min(disp_pre, disp_post) < MIN_VENTANA_S:
                motivo = "ventana corta"
        if motivo is None:
            g = por_partido[r.match_id]
            g = g[g["period"] == r.period]
            pre = g[(g["ts_s"] >= r.ts_s - VENTANA_S) & (g["ts_s"] < r.ts_s)]
            post = g[(g["ts_s"] >= r.ts_s) & (g["ts_s"] < r.ts_s + VENTANA_S)]
            if pd.concat([pre, post])["es_roja"].any():
                motivo = "roja en ventana"
            else:
                mp, mq = _metricas_ventana(pre, disp_pre), _metricas_ventana(post, disp_post)
                for k in METRICAS:
                    fila[f"{k}_pre"], fila[f"{k}_post"], fila[f"delta_{k}"] = mp[k], mq[k], mq[k] - mp[k]
        fila["motivo_exclusion"] = motivo
        fila["valido"] = motivo is None
        filas.append(fila)
    return pd.DataFrame(filas)


def bootstrap_ic(x, n_boot=5000, seed=0):
    """Genera márgenes (límites inferior y superior) de error estadístico (95% confianza) con remuestreo."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    medias = np.random.default_rng(seed).choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return float(x.mean()), float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5))


def resumen_rendimiento(cambio):
    """
    Sintetiza la efectividad promedio de los cambios.
    Aísla las métricas según el estado del marcador al momento de cambiar (ej. impacto al ir 'perdiendo').
    """
    v = cambio[cambio["valido"]]
    filas = []
    for grupo, sub in [("todos", v)] + [(s, v[v["score_state"] == s]) for s in ("ganando", "empatando", "perdiendo")]:
        for k in METRICAS:
            col = f"delta_{k}"
            if len(sub) >= MIN_CELDA or grupo == "todos":
                media, lo, hi = bootstrap_ic(sub[col]) if len(sub) else (np.nan,) * 3
                nota = "" if len(sub) >= MIN_CELDA else "n bajo: solo indicio"
            else:
                media = lo = hi = np.nan
                nota = f"n < {MIN_CELDA}: no se estratifica"
            filas.append({"score_state": grupo, "metrica": k, "n": len(sub), "media_delta": media, "ic95_inf": lo,
                          "ic95_sup": hi, "nota": nota})
    return pd.DataFrame(filas)


def resumen_cambios(momentos, cambios):
    """Analiza las tendencias conductuales (tiempos típicos y sustituciones posición por posición)."""
    filas = []
    for dim in ("score_state", "es_local", "fase", "numerical_state"):
        for cat, g in momentos.groupby(dim, observed=True):
            filas.append({"dimension": dim, "categoria": str(cat), "n_momentos": len(g), "n_cambios": int(g["n_cambios"].sum()),
                          "minuto_mediano": g["minute"].median(), "minuto_p25": g["minute"].quantile(.25),
                          "minuto_p75": g["minute"].quantile(.75)})
    matriz = pd.crosstab(cambios["role_sale"], cambios["role_entra"]).reset_index()
    return pd.DataFrame(filas), matriz


# ---------- main ----------

def escribir(salida, tablas):
    """Guarda las métricas resultantes en formato parquet."""
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, df in tablas.items():
        df.to_parquet(salida / f"{nombre}.parquet", compression="zstd", index=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solo-partido", type=int, metavar="MATCH_ID")
    ap.add_argument("--ver", action="store_true", help="imprime resumen de rendimiento y patrones de cambio")
    args = ap.parse_args()
    solo = args.solo_partido is not None

    base = ROOT / "data" / "interim" / ("muestra" if solo else "")
    salida = ROOT / "data" / "processed" / "jugadores" / ("muestra" if solo else "")
    base_proc = ROOT / "data" / "processed" / ("muestra" if solo else "")

    partidos = pd.read_parquet(base / "partidos.parquet", columns=COLS_PARTIDOS)
    ids = partidos["match_id"].astype(int).tolist()
    eventos = pd.read_parquet(base / "eventos.parquet", columns=COLS_EVENTOS, filters=[("match_id", "in", ids)])
    posiciones = pd.read_parquet(base / "posiciones.parquet")
    tactics_ruta = base / "tactics_lineup.parquet"
    tactics = pd.read_parquet(tactics_ruta) if tactics_ruta.exists() else None

    # Asegurando el uso unificado del estado del partido (marcador/rojas)
    ruta_ctx = base_proc / "contexto_eventos.parquet"
    if not ruta_ctx.exists() and solo:
        ruta_ctx = ROOT / "data" / "processed" / "contexto_eventos.parquet"
    ctx_eventos = pd.read_parquet(ruta_ctx) if ruta_ctx.exists() else None

    ev = preparar_eventos(eventos, partidos, ctx_eventos)
    duraciones = duraciones_periodo(eventos)
    minutos, tramos = minutos_jugados(posiciones, eventos, partidos)
    formaciones = formacion_por_periodo(eventos, partidos)
    onces, titularidades, fuente_onces = onces_iniciales(posiciones, partidos, tactics, eventos)
    cambios = cambios_individuales(ev, posiciones)
    momentos = momentos_de_cambio(cambios)
    rendimiento = cambio_en_rendimiento(momentos, ev, duraciones)
    resumen = resumen_rendimiento(rendimiento)
    resumen_a, matriz_roles = resumen_cambios(momentos, cambios)
    peso = peso_posiciones(tramos)

    escribir(salida, {
        "peso_posiciones": peso,
        "tramos_posicion": tramos[["match_id", "team_id", "player_id", "posicion_idx", "position_id", "role_group", "minutos"]],
        "minutos_jugados": minutos, "formacion_por_periodo": formaciones, "onces_iniciales": onces,
        "titularidades": titularidades, "cambios_individuales": cambios, "momentos_de_cambio": momentos,
        "cambio_en_rendimiento": rendimiento, "resumen_rendimiento": resumen,
        "resumen_cambios": resumen_a, "matriz_roles_cambios": matriz_roles
    })

    # --- Explica en consola la riqueza de los datos obtenidos ---
    print("\n--- RESUMEN TÁCTICO Y DE RENDIMIENTO OBTENIDO ---")
    print(f"[✓] Jugadores y Minutos: Se generaron métricas reales ajustadas para {len(minutos)} registros jugador-partido.")
    print(f"[✓] Formaciones: {len(formaciones)} disposiciones base identificadas por cada mitad de juego.")
    print(f"[✓] Onces Iniciales: Alineaciones iniciales mapeadas para {len(onces)} juegos usando {fuente_onces}.")
    print(f"[✓] Estilos Nominales: El {pct_minutos_ambiguos(tramos):.1f}% del tiempo operó con carrileros/volantes de banda.")
    print(f"\n--- ANÁLISIS DE IMPACTO DE LOS CAMBIOS ---")
    print(f"[✓] Se detectaron {len(momentos)} ventanas en las que el DT ajustó piezas tácticas.")
    print(f"    - Ventanas Válidas: {int(rendimiento['valido'].sum())} cumplen los requisitos de limpieza "
          "(mín. 8 min disponibles, 0 tarjetas rojas post-cambio) para medir su impacto aisladamente.")
    print("    - Qué se evaluó: Evolución de Expected Goals (xG), Dominio Cualitativo del Balón (OBV Neto)")
    print("      y Control de Posesión; comparando sistemáticamente los 15 minutos ANTES vs. los 15 minutos DESPUÉS del cambio.")

    if args.ver:
        pd.set_option("display.width", 200)
        print("\n--- TABLA: INTERVALOS DE IMPACTO DEL CAMBIO SEGÚN EL MARCADOR ---")
        print(resumen.to_string(index=False))
        print("\n--- MATRIZ: PATRONES Y TENDENCIAS DEL ENTRENADOR ---")
        print(resumen_a.to_string(index=False))

    print(f"\n=> Procesamiento finalizado. Todas las tablas guardadas en: {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())