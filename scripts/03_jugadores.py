"""Bloque de jugadores (plan 14.5, Pato): role_group, minutos, formacion por periodo, onces iniciales y cambios.

Uso:
    python scripts/03_jugadores.py --solo-partido 3995374   # lee data/interim/muestra/, escribe en data/processed/jugadores/muestra/
    python scripts/03_jugadores.py                          # lee data/interim/, escribe en data/processed/jugadores/
    python scripts/03_jugadores.py --explorar               # ademas imprime los valores de start_reason y end_reason

Lee de data/interim: partidos, eventos, posiciones, tactics_lineup (02_auxiliares.py) y player_match_stats.
Cada metrica es una funcion que recibe DataFrames y devuelve otro DataFrame.

Decisiones (a declarar en el framework; todas son propuesta hasta que Lee las confirme):
  - Equipo analizado = partidos.equipo_id. Todo se atribuye con team_id (plan 7.3.8).
  - Solo cuentan los periodos 1 y 2. Tiempo extra (3 y 4) y penales (5) quedan fuera: el inicio de 3 y 4 no esta verificado (C9).
  - Reloj: `posiciones.from/to` vienen en reloj corrido (2.o tiempo empieza en 00:45:00). Los minutos se suman por periodo
    con el Half End de `eventos`; nunca se resta to - from directo. `to` nulo = silbatazo final (C9).
  - Las ventanas de los cambios usan `timestamp` (segundos desde el inicio del periodo), asi nunca cruzan el descanso.
  - Cambios en el mismo (partido, periodo, minuto) son un solo momento de cambio.
  - Este script calcula su propio marcador y superioridad numerica desde `eventos` (no depende de 03_contexto.py).
  - No incluye PPDA ni presiones altas: falta fijar la zona del PPDA y el umbral de presion alta en el framework.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))  # contrato.py esta en scripts/
from contrato import ADMINISTRATIVOS  # noqa: E402

INICIO_PERIODO = {1: 0.0, 2: 2700.0}   # reloj corrido de posiciones (segundos); 3 y 4 sin verificar
PERIODOS_VALIDOS = (1, 2)
VENTANA_S = 900          # 15 min (plan 8 y J2)
MIN_VENTANA_S = 480      # 8 min por lado, propuesta mia: ventanas mas cortas se descartan
MIN_CELDA = 15           # n minimo para estratificar por marcador, propuesta mia
ROJAS = ("Red Card", "Second Yellow")   # VERIFICAR con value_counts de foul_committed_card_name
GRUPOS = [(1, 1, "portero"), (2, 8, "defensa"), (9, 16, "medio"), (17, 21, "extremo_mediapunta"), (22, 25, "delantero")]
METRICAS = ["xg_favor", "xg_contra", "xg_dif", "obv_equipo", "obv_rival", "obv_neto", "posesion_eventos"]
COLS_EVENTOS = ["match_id", "index", "period", "timestamp", "minute", "second", "type_name", "team_id",
                "possession_team_id", "player_id", "position_id", "tactics_formation", "shot_statsbomb_xg",
                "shot_type_name", "shot_outcome_name", "obv_total_net", "foul_committed_card_name",
                "bad_behaviour_card_name", "substitution_outcome_name", "substitution_replacement_id"]
COLS_PARTIDOS = ["match_id", "match_date", "equipo_id", "es_local", "fase", "torneo"]
COLS_MINUTOS_PMS = ("player_match_minutes", "minutes")   # VERIFICAR el nombre en el contrato de player_match_stats


# ---------- utilidades ----------

def hms_a_seg(serie):
    # Texto HH:MM:SS.mmm a segundos (float); nulo da NaN.
    s = serie.astype("string").str.strip()
    if s.isna().all():
        return pd.Series(np.nan, index=serie.index, dtype="float64")
    p = s.str.split(":", expand=True)
    h, m, seg = (pd.to_numeric(p[i], errors="coerce") for i in range(3))
    return (h * 3600 + m * 60 + seg).astype("float64")


def asignar_role_group(df, col="position_id"):
    # Agrega role_group segun position_id: portero 1; defensa 2-8; medio 9-16; extremo_mediapunta 17-21; delantero 22-25.
    out = df.copy()
    pid = out[col].astype("Int64")
    grupo = pd.Series(pd.NA, index=out.index, dtype="string")
    for lo, hi, nombre in GRUPOS:
        grupo = grupo.mask(pid.between(lo, hi).fillna(False).astype(bool), nombre)
    out["role_group"] = grupo
    return out


def duraciones_periodo(eventos):
    # Duracion de cada periodo (segundos) = timestamp del Half End; una fila por (match_id, period).
    he = eventos.loc[eventos["type_name"] == "Half End", ["match_id", "period", "timestamp"]].copy()
    he["dur_s"] = hms_a_seg(he["timestamp"])
    return he.groupby(["match_id", "period"], as_index=False)["dur_s"].max()


def _dict_duraciones(duraciones):
    return {(int(m), int(p)): float(d) for m, p, d in duraciones.itertuples(index=False) if pd.notna(d)}


def preparar_eventos(eventos, partidos):
    # Eventos de los partidos analizados con contexto: es_eq, ts_s, score_state, numerical_state, es_roja.
    p = partidos[COLS_PARTIDOS]
    ev = eventos.merge(p, on="match_id", how="inner", validate="many_to_one")
    ev = ev.sort_values(["match_id", "index"]).reset_index(drop=True)
    ev["ts_s"] = hms_a_seg(ev["timestamp"])
    ev["es_eq"] = (ev["team_id"] == ev["equipo_id"]).fillna(False).astype(bool)
    juego = ev["period"].isin([1, 2, 3, 4])   # los penales (5) no cuentan para el marcador
    gol = ((ev["type_name"] == "Shot") & (ev["shot_outcome_name"] == "Goal") & juego) | (ev["type_name"] == "Own Goal For")
    carta = ev["foul_committed_card_name"].isin(ROJAS) | ev["bad_behaviour_card_name"].isin(ROJAS)
    ev["es_roja"] = carta & juego

    def previos(flag):   # acumulado antes del evento (sin contarlo)
        f = flag.astype(int)
        return f.groupby(ev["match_id"]).cumsum() - f

    dif = previos(gol & ev["es_eq"]) - previos(gol & ~ev["es_eq"])
    sup = previos(ev["es_roja"] & ~ev["es_eq"]) - previos(ev["es_roja"] & ev["es_eq"])
    ev["dif_goles"] = dif
    ev["score_state"] = np.select([dif > 0, dif < 0], ["ganando", "perdiendo"], default="empatando")
    ev["numerical_state"] = np.select([sup > 0, sup < 0], ["superioridad", "inferioridad"], default="igualdad")
    return ev


# ---------- J1: role_group y minutos ----------

def minutos_por_tramo(posiciones, duraciones):
    # Minutos de cada tramo de posicion, sumados por periodo (periodos 1 y 2). `to` nulo = hasta el final del 2.o tiempo.
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
    # Minutos por jugador y partido (equipo analizado) y su rol principal (el grupo con mas minutos en ese partido).
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
    # Porcentaje de minutos en posiciones 7, 8, 12 y 16 (carrileros y volantes por banda): limite a declarar.
    amb = tr["position_id"].isin([7, 8, 12, 16])
    return float(tr.loc[amb, "minutos"].sum() / tr["minutos"].sum() * 100)


# ---------- J2a: formacion por periodo y onces ----------

def formacion_por_periodo(eventos, partidos):
    # Formacion predominante (mas minutos) por (partido, periodo): vigente desde cada Starting XI o Tactical Shift hasta el siguiente.
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


def onces_iniciales(tactics_lineup, eventos, partidos):
    # Titulares por partido (Starting XI del equipo analizado), jugadores nuevos frente al partido anterior y titularidades.
    xi = eventos.loc[eventos["type_name"] == "Starting XI", ["match_id", "index", "team_id"]].merge(
        partidos[["match_id", "equipo_id"]], on="match_id")
    xi = xi[xi["team_id"] == xi["equipo_id"]][["match_id", "index"]]
    t = tactics_lineup.merge(xi, on=["match_id", "index"])
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
    return onces, tit.reset_index(drop=True)


# ---------- J2b: cambios ----------

def cambios_individuales(ev, posiciones):
    # Una fila por sustitucion del equipo analizado, con rol de quien sale y de quien entra.
    cam = ev[(ev["type_name"] == "Substitution") & ev["es_eq"] & ev["period"].isin([1, 2, 3, 4])].copy()
    pos = asignar_role_group(posiciones)
    primero = pos[pos["posicion_idx"] == 0].drop_duplicates(["match_id", "player_id"])
    rol_entra = {(int(m), int(j)): g for m, j, g in zip(primero["match_id"], primero["player_id"], primero["role_group"])
                 if pd.notna(g)}
    cam["role_entra"] = [rol_entra.get((int(m), int(j))) if pd.notna(j) else None
                         for m, j in zip(cam["match_id"], cam["substitution_replacement_id"])]
    cam["role_sale"] = asignar_role_group(cam, "position_id")["role_group"]   # VERIFICAR: position_id del evento es el de quien sale
    cam["tipo_cambio"] = np.where(cam["substitution_outcome_name"].astype("string").str.contains("Injury", na=False),
                                  "lesion", "tactico")
    cols = ["match_id", "index", "period", "minute", "ts_s", "player_id", "substitution_replacement_id", "role_sale",
            "role_entra", "tipo_cambio", "score_state", "numerical_state", "dif_goles", "es_local", "fase", "torneo"]
    return cam[cols].rename(columns={"player_id": "sale_id", "substitution_replacement_id": "entra_id"}).reset_index(drop=True)


def momentos_de_cambio(cambios):
    # Cambios del mismo (partido, periodo, minuto) cuentan como un solo momento.
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
    # Metricas de una ventana, escaladas a 15 min (xg y obv); la posesion es proporcion de eventos y no se escala.
    k = VENTANA_S / disponible_s
    tiro = (w["type_name"] == "Shot") & (w["shot_type_name"] != "Penalty")   # np_xg: sin penales
    xf = float(w.loc[tiro & w["es_eq"], "shot_statsbomb_xg"].sum()) * k
    xc = float(w.loc[tiro & ~w["es_eq"], "shot_statsbomb_xg"].sum()) * k
    of = float(w.loc[w["es_eq"], "obv_total_net"].sum()) * k
    oc = float(w.loc[~w["es_eq"], "obv_total_net"].sum()) * k
    juego = w[~w["type_name"].isin(ADMINISTRATIVOS)]
    pos = float((juego["possession_team_id"] == juego["equipo_id"]).mean()) if len(juego) else np.nan
    return {"xg_favor": xf, "xg_contra": xc, "xg_dif": xf - xc, "obv_equipo": of, "obv_rival": oc, "obv_neto": of - oc,
            "posesion_eventos": pos}


def cambio_en_rendimiento(momentos, ev, duraciones):
    # Metricas en los 15 min antes y despues de cada momento de cambio, con su motivo de exclusion si no aplica.
    # No es causal: los cambios responden al estado del partido.
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
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return np.nan, np.nan, np.nan
    medias = np.random.default_rng(seed).choice(x, size=(n_boot, len(x)), replace=True).mean(axis=1)
    return float(x.mean()), float(np.percentile(medias, 2.5)), float(np.percentile(medias, 97.5))


def resumen_rendimiento(cambio):
    # Media de cada delta con IC 95% (bootstrap) y n; estratificado por marcador solo si n >= MIN_CELDA.
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
    # Analisis A: cuando cambia Jardine segun marcador, localia, fase y superioridad; y matriz de roles que salen y entran.
    filas = []
    for dim in ("score_state", "es_local", "fase", "numerical_state"):
        for cat, g in momentos.groupby(dim, observed=True):
            filas.append({"dimension": dim, "categoria": str(cat), "n_momentos": len(g), "n_cambios": int(g["n_cambios"].sum()),
                          "minuto_mediano": g["minute"].median(), "minuto_p25": g["minute"].quantile(.25),
                          "minuto_p75": g["minute"].quantile(.75)})
    matriz = pd.crosstab(cambios["role_sale"], cambios["role_entra"]).reset_index()
    return pd.DataFrame(filas), matriz


# ---------- validaciones ----------

def validar(minutos, tramos, formaciones, cambios, posiciones, partidos, pms, duraciones):
    # Lista de avisos; vacia si todo cuadra. No detienen la corrida.
    avisos = []
    if tramos["minutos"].isna().any():
        avisos.append(f"{int(tramos['minutos'].isna().sum())} tramos sin minutos calculados (falta Half End o periodo)")
    if (tramos["minutos"] < 0).any():
        avisos.append("hay tramos con minutos negativos")
    if not formaciones.empty and not formaciones["digitos_suman_10"].all():
        malas = formaciones.loc[~formaciones["digitos_suman_10"], "formacion"].unique().tolist()
        avisos.append(f"formaciones cuyos digitos no suman 10: {malas}")
    # suma de minutos del equipo contra 11 x duracion
    dur = _dict_duraciones(duraciones)
    ratios = []
    for mid, g in minutos.groupby("match_id"):
        esperado = 11 * sum(dur.get((int(mid), p), 0) for p in PERIODOS_VALIDOS) / 60
        if esperado:
            ratios.append((int(mid), g["minutos"].sum() / esperado))
    raros = [(m, round(r, 3)) for m, r in ratios if r < 0.85 or r > 1.01]
    if raros:
        avisos.append(f"partidos con suma de minutos fuera de 85%-101% de 11 x duracion (rojas o error): {raros[:10]}")
    # sustituciones contra jugadores que entran
    n_ev = cambios.groupby("match_id").size()
    pos = posiciones.merge(partidos[["match_id", "equipo_id"]], on="match_id")
    pos = pos[(pos["team_id"] == pos["equipo_id"]) & (pos["posicion_idx"] == 0)]
    n_on = pos[pos["start_reason"].astype("string").str.contains("Substitution", na=False)].groupby("match_id").size()
    cmp_ = pd.concat([n_ev.rename("eventos"), n_on.rename("lineups")], axis=1).fillna(0)
    malos = cmp_[cmp_["eventos"] != cmp_["lineups"]]
    if len(malos):
        avisos.append(f"{len(malos)} partidos donde Substitution (eventos) no coincide con entradas en posiciones: "
                      f"{malos.head(5).astype(int).to_dict('index')}. Revisar los textos de start_reason con --explorar")
    # minutos contra player_match_stats
    col = next((c for c in COLS_MINUTOS_PMS if pms is not None and c in pms.columns), None)
    if col is None:
        avisos.append("VERIFICAR: no encontre la columna de minutos en player_match_stats; no se comparo")
    else:
        c = minutos.merge(pms[["match_id", "team_id", "player_id", col]], on=["match_id", "team_id", "player_id"], how="left")
        dif = (c["minutos"] - c[col].astype(float)).abs()
        n = int((dif > 1.5).sum())
        if n:
            avisos.append(f"{n} de {len(c)} jugadores-partido con minutos que difieren mas de 1.5 min de player_match_stats "
                          "(esperable en el partido con tiempo extra)")
    return avisos


# ---------- main ----------

def escribir(salida, tablas):
    salida.mkdir(parents=True, exist_ok=True)
    for nombre, df in tablas.items():
        df.to_parquet(salida / f"{nombre}.parquet", compression="zstd", index=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solo-partido", type=int, metavar="MATCH_ID")
    ap.add_argument("--explorar", action="store_true", help="imprime los valores de start_reason, end_reason y tarjetas")
    args = ap.parse_args()
    solo = args.solo_partido is not None
    base = ROOT / "data" / "interim" / ("muestra" if solo else "")
    salida = ROOT / "data" / "processed" / "jugadores" / ("muestra" if solo else "")
    otro = ROOT / "data" / "raw" / "parquet" 

    partidos = pd.read_parquet(base / "partidos.parquet", columns=COLS_PARTIDOS)
    ids = partidos["match_id"].astype(int).tolist()
    eventos = pd.read_parquet(base / "eventos.parquet", columns=COLS_EVENTOS, filters=[("match_id", "in", ids)])
    posiciones = pd.read_parquet(base / "posiciones.parquet")
    tactics = pd.read_parquet(otro / "lineups.parquet")
    pms_ruta = base / "player_match_stats.parquet"
    pms = pd.read_parquet(pms_ruta) if pms_ruta.exists() else None

    if args.explorar:
        for c in ("start_reason", "end_reason"):
            print(f"\n{c}:\n{posiciones[c].value_counts(dropna=False).to_string()}")
        for c in ("foul_committed_card_name", "bad_behaviour_card_name", "substitution_outcome_name"):
            print(f"\n{c}:\n{eventos[c].value_counts(dropna=False).to_string()}")

    ev = preparar_eventos(eventos, partidos)
    duraciones = duraciones_periodo(eventos)
    minutos, tramos = minutos_jugados(posiciones, eventos, partidos)
    formaciones = formacion_por_periodo(eventos, partidos)
    onces, titularidades = onces_iniciales(tactics, eventos, partidos)
    cambios = cambios_individuales(ev, posiciones)
    momentos = momentos_de_cambio(cambios)
    rendimiento = cambio_en_rendimiento(momentos, ev, duraciones)
    resumen = resumen_rendimiento(rendimiento)
    resumen_a, matriz_roles = resumen_cambios(momentos, cambios)

    avisos = validar(minutos, tramos, formaciones, cambios, posiciones, partidos, pms, duraciones)
    escribir(salida, {"minutos_jugados": minutos, "formacion_por_periodo": formaciones, "onces_iniciales": onces,
                      "titularidades": titularidades, "cambios_individuales": cambios, "momentos_de_cambio": momentos,
                      "cambio_en_rendimiento": rendimiento, "resumen_rendimiento": resumen,
                      "resumen_cambios": resumen_a, "matriz_roles_cambios": matriz_roles})

    print(f"Jugadores-partido: {len(minutos)}; formaciones por periodo: {len(formaciones)}; onces: {len(onces)}")
    print(f"Minutos en posiciones ambiguas (7, 8, 12, 16): {pct_minutos_ambiguos(tramos):.1f}% (declarar como limite)")
    print(f"Momentos de cambio: {len(momentos)} (validos para antes/despues: {int(rendimiento['valido'].sum())})")
    print("Exclusiones:", rendimiento.loc[~rendimiento["valido"], "motivo_exclusion"].value_counts().to_dict())
    if avisos:
        print("\nREVISAR:")
        for a in avisos:
            print(f"   - {a}")
    else:
        print("\nValidaciones: todo cuadra")
    print(f"Escrito en {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
