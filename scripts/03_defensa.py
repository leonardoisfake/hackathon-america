"""Fase 3, defensa: presión y defensa del América de Jardine (fichas B5 y D1 a D5 de Lee).

Lee eventos, partidos, team_match_stats y team_match_stats_liga de data/interim/ y
contexto_eventos de data/processed/ (sale de 03_contexto.py, que va antes).
Escribe en data/processed/:

  defensa_partidos       una fila por partido (91): D1 a D5 y B5 resumidos, con
                         numeradores, denominadores y la referencia de StatsBomb
  defensa_periodos       una fila por partido y periodo 1 a 4: D1, D2 y D4
  defensa_fases_presion  una fila por fase de presión (B5), en dos variantes
  defensa_perdidas       una fila por pérdida del EQ en juego abierto (D3)
  defensa_transiciones   una fila por cambio de posesión en juego abierto (D5)
  defensa_zonas          acciones defensivas del EQ por partido, acción y cell_6x5 (E1)
  defensa_liga           promedios defensivos de StatsBomb por equipo y torneo (fase
                         regular), con ranking dentro del torneo
  balon_parado_posesiones  una fila por posesión de balón parado, a favor y en contra (P1)
  balon_parado_tiros       una fila por tiro sin penal de los dos equipos, con origen y zona (P2)
  balon_parado_partidos    una fila por partido, lado y tipo (corner, tiro libre, saque de
                           banda y juego abierto), con la referencia de StatsBomb (P1 y P2)

Las tablas por evento traen la llave (match_id, index) del evento de referencia y el
contexto de contexto_eventos en ese evento. Las ventanas de segundos usan timestamp
dentro del mismo periodo (convención de la sección 1 de las fichas).

Códigos de salida: 0 si todo pasó (y se escribió, cuando se pidió); 1 si falló una
validación dura, falta un dato o falló la escritura. Si algo falla no se escribe nada.
"""

import argparse
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa

RAIZ = Path(__file__).resolve().parent.parent
INTERIM = RAIZ / "data" / "interim"
PROCESSED = RAIZ / "data" / "processed"

MANAGER_ID = 1000116
EQ = 1229
N_PARTIDOS = 91

# Umbrales de la sección 2 de las fichas (yardas, cancha de 120 x 80)
X_PRESION_ALTA = 80        # D1: últimos 40 yd de la cancha rival (punto por confirmar 1)
X_PRESION_ALTA_M = 120 - 40 / 0.9144   # D1: últimos 40 m, como dice el framework de Pato (76.26 yd)
X_MITAD_RIVAL = 60         # D1: referencia de StatsBomb (fhalf)
X_PPDA = 48                # D2: 40% del largo; pases del rival con x <= 120 - 48
VENTANA = 5                # D3 y D5: segundos
FASE_GAP = 10              # B5: segundos entre intentos
FASE_MIN = 3               # B5: intentos por fase

JUEGO_ABIERTO = [1, 5, 6, 7, 8]      # play_pattern_id; 2, 3, 4 = balón parado; 9 fuera de ambos
BALON_PARADO = [2, 3, 4]
POSICIONES_DEFENSAS = range(2, 9)    # D4, variante: position_id 2 a 8
TIPOS_BP = {2: "Corner", 3: "Free Kick", 4: "Throw In"}           # P1: play_pattern_id -> tipo
SAQUES = {"Corner": "Corner", "Free Kick": "Free Kick", "Throw-in": "Throw In"}   # pass_type_name -> tipo
AREA_X, AREA_Y0, AREA_Y1 = 102, 18, 62                             # P2: área grande

CONTEXTO = ["score_state", "numerical_state_cat", "minute_bin", "rival_strength_tercil", "stage"]

SALIDAS = ["defensa_partidos", "defensa_periodos", "defensa_fases_presion", "defensa_perdidas",
           "defensa_transiciones", "defensa_zonas", "defensa_liga",
           "balon_parado_posesiones", "balon_parado_tiros", "balon_parado_partidos"]

# Categorías fijas, para que no cambien entre corridas (como en 03_contexto.py)
CATEGORIAS = {
    "variante": ["intentos", "solo_pressure"],
    "tipo_perdida": ["Pass", "Miscontrol", "Dispossessed", "Dribble"],
    "tipo": ["defensiva", "ofensiva"],
    "accion": ["presion", "entrada", "intercepcion", "recuperacion", "bloqueo", "despeje", "falta"],
    "lado": ["a_favor", "en_contra"],
    "set_piece_type": ["Corner", "Free Kick", "Throw In", "Juego abierto"],
    "origen": ["balon_parado", "juego_abierto"],
    "zona_remate": ["area_chica", "area_grande", "fuera_del_area"],
}
PATRONES = {1: "Regular Play", 2: "From Corner", 3: "From Free Kick", 4: "From Throw In", 5: "Other",
            6: "From Counter", 7: "From Goal Kick", 8: "From Keeper", 9: "From Kick Off"}

ERRORES_ESCRITURA = (OSError, ValueError, TypeError, pa.lib.ArrowException)


class ErrorDefensa(Exception):
    pass


# ---------------------------------------------------------------- lectura y preparación

def leer(carpeta, nombre, columnas=None):
    ruta = carpeta / f"{nombre}.parquet"
    if not ruta.exists():
        antes = "03_contexto.py" if carpeta == PROCESSED else "02_limpieza.py"
        raise ErrorDefensa(f"no existe {ruta}; corre antes {antes}")
    try:
        return pd.read_parquet(ruta, columns=columnas)
    except (OSError, ValueError, KeyError) as e:
        raise ErrorDefensa(f"no se pudo leer {nombre}: {type(e).__name__}: {e}") from e


def fijar_categorias(tablas):
    for df in tablas.values():
        for col, cats in CATEGORIAS.items():
            if col in df.columns:
                df[col] = pd.Categorical(df[col].astype("string"), categories=cats)
    return tablas


def b(serie):
    # bandera boolean con nulos -> bool simple (convención: falta = False)
    return serie.fillna(False).astype(bool)


def preparar(ev, partidos):
    ev = ev[ev["match_id"].isin(partidos["match_id"]) & ev["period"].between(1, 4)]
    ev = ev.sort_values(["match_id", "index"]).reset_index(drop=True)
    ev["t"] = pd.to_timedelta(ev["timestamp"]).dt.total_seconds()
    t = ev["type_name"].astype("string")
    duelo = ev["duel_type_name"].astype("string")
    ev["es_eq"] = ev["team_id"] == EQ
    ev["es_adm"] = b(ev["es_administrativo"])
    ev["juego_abierto"] = ev["play_pattern_id"].isin(JUEGO_ABIERTO).fillna(False).astype(bool)
    ev["es_presion"] = t == "Pressure"
    ev["es_entrada"] = (t == "Duel") & (duelo == "Tackle")
    ev["es_intercepcion"] = t == "Interception"
    ev["es_falta"] = t == "Foul Committed"
    ev["es_recuperacion"] = t == "Ball Recovery"
    ev["es_bloqueo"] = t == "Block"
    ev["es_despeje"] = t == "Clearance"
    ev["es_cp"] = b(ev["counterpress"])
    ev["es_tiro_np"] = (t == "Shot") & ~ev["shot_type_name"].astype("string").eq("Penalty").fillna(False)
    ev["es_perdida_tipo"] = (
        (t == "Dispossessed") | (t == "Miscontrol")
        | ((t == "Pass") & ev["pass_outcome_name"].notna())
        | ((t == "Dribble") & (ev["dribble_outcome_name"].astype("string") == "Incomplete"))
    ).fillna(False).astype(bool)
    return marcar_balon_parado(ev)


def posesiones(ev):
    """Una fila por posesión no administrativa: equipo, periodo, inicio, patrón de juego."""
    na = ev[~ev["es_adm"]]
    pos = na.groupby(["match_id", "possession"], as_index=False).agg(
        pos_team=("possession_team_id", "first"), period=("period", "first"),
        index_inicio=("index", "first"), t_inicio=("t", "first"),
        play_pattern_id=("play_pattern_id", "first"))
    return pos.sort_values(["match_id", "index_inicio"]).reset_index(drop=True)


def siguiente_inicio(izq, inicios, estricto=True):
    """Para cada fila de izq (match_id, index), el primer inicio de posesión de `inicios` después."""
    izq = izq.sort_values("index")
    der = inicios[["match_id", "index_inicio", "t_inicio", "period", "pos_team"]].rename(
        columns={"period": "period_sig", "pos_team": "team_sig"}).sort_values("index_inicio")
    return pd.merge_asof(izq, der, left_on="index", right_on="index_inicio", by="match_id",
                         direction="forward", allow_exact_matches=not estricto)


def recupera(izq, pos, t_ref="t", estricto=True):
    """True si el EQ abre una posesión en el mismo periodo a <= VENTANA s de t_ref."""
    m = siguiente_inicio(izq, pos[pos["pos_team"] == EQ], estricto)
    ok = (m["period_sig"] == m["period"]) & ((m["t_inicio"] - m[t_ref]) <= VENTANA)
    return m.assign(regain_5s=ok.fillna(False).astype(bool))


def con_contexto(df, ctx, col_index="index"):
    return df.merge(ctx[["match_id", "index"] + CONTEXTO].rename(columns={"index": col_index}),
                    on=["match_id", col_index], how="left")


# ---------------------------------------------------------------- D1, D2 y D4 por partido y periodo

def d1_d2_d4(ev, por):
    """Agrega D1, D2 y D4 al nivel `por` (["match_id"] o ["match_id", "period"])."""
    eq, rv = ev["es_eq"], ~ev["es_eq"]
    g = lambda m: ev[m].groupby(por)

    pres = eq & ev["es_presion"]
    d = pd.DataFrame({
        "presiones": g(pres).size(),
        "presiones_altas": g(pres & (ev["x"] >= X_PRESION_ALTA)).size(),
        "presiones_altas_40m": g(pres & (ev["x"] >= X_PRESION_ALTA_M)).size(),
        "presiones_mitad_rival": g(pres & (ev["x"] >= X_MITAD_RIVAL)).size(),
        "press_height": g(pres).x.mean(),
    })

    # D2: pases del rival en la zona de ataque del EQ (x <= 72 en coordenadas del rival)
    pase_rival = rv & (ev["type_name"] == "Pass") & (ev["x"] <= 120 - X_PPDA)
    acciones = eq & (ev["es_entrada"] | ev["es_intercepcion"] | ev["es_falta"]) & (ev["x"] >= X_PPDA)
    d["ppda_pases_rival"] = g(pase_rival).size()
    d["ppda_pases_rival_ja"] = g(pase_rival & ev["juego_abierto"]).size()
    d["ppda_acciones"] = g(acciones).size()

    # D4: acciones defensivas sin portero, sin balón parado y sin Pressure
    linea = (eq & (ev["es_entrada"] | ev["es_intercepcion"] | ev["es_bloqueo"] | ev["es_despeje"] | ev["es_recuperacion"])
             & ~ev["play_pattern_id"].isin(BALON_PARADO).fillna(False) & (ev["position_id"] != 1).fillna(True)
             & ev["x"].notna())
    d["acciones_linea"] = g(linea).size()
    d["defensive_line_height"] = g(linea).x.mean()
    defensas = linea & ev["position_id"].isin(POSICIONES_DEFENSAS).fillna(False)
    d["acciones_linea_defensas"] = g(defensas).size()
    d["defensive_line_height_defensas"] = g(defensas).x.mean()

    conteos = [c for c in d.columns if c.startswith(("presiones", "ppda_", "acciones"))]
    d[conteos] = d[conteos].fillna(0).astype("Int64")
    d["pct_presiones_altas"] = razon(d["presiones_altas"], d["presiones"])
    d["pct_presiones_altas_40m"] = razon(d["presiones_altas_40m"], d["presiones"])
    d["ppda"] = razon(d["ppda_pases_rival"], d["ppda_acciones"])
    d["ppda_juego_abierto"] = razon(d["ppda_pases_rival_ja"], d["ppda_acciones"])
    d["defensive_line_height_100"] = d["defensive_line_height"] / 120 * 100
    return d


def razon(a, c):
    return (a.astype("float64") / c.astype("float64").replace(0, np.nan)).astype("float64")


def variantes_ppda(ev, sb):
    """D2, validación: prueba las variantes de la ficha contra team_match_ppda."""
    eq, rv = ev["es_eq"], ~ev["es_eq"]
    pase = rv & (ev["type_name"] == "Pass") & (ev["x"] <= 120 - X_PPDA)
    base = ev["es_entrada"] | ev["es_intercepcion"]
    extra = (ev["type_name"] == "Dribbled Past") | (ev["type_name"] == "50/50")
    filas = []
    for nombre_p, mp in [("todos", pase), ("juego abierto", pase & ev["juego_abierto"])]:
        for nombre_a, ma in [("entrada+intercepción+falta (ficha)", base | ev["es_falta"]),
                             ("sin faltas", base),
                             ("ficha + regateado + 50/50", base | ev["es_falta"] | extra)]:
            v = (ev[mp].groupby("match_id").size()
                 / ev[eq & ma & (ev["x"] >= X_PPDA)].groupby("match_id").size()).reindex(sb.index)
            filas.append((nombre_p, nombre_a, v.corr(sb), (v / sb).median(), (v - sb).abs().mean()))
    return pd.DataFrame(filas, columns=["pases", "acciones", "corr", "razon_mediana", "mae"])


# ---------------------------------------------------------------- B5: fases de presión

def b5_fases(ev, pos, ctx):
    partes = []
    for variante, intento in [("intentos", ev["es_presion"] | ev["es_recuperacion"] | ev["es_entrada"] | ev["es_intercepcion"]),
                              ("solo_pressure", ev["es_presion"])]:
        it = ev.loc[ev["es_eq"] & intento, ["match_id", "index", "period", "t", "x"]].sort_values(["match_id", "period", "t", "index"])
        nueva = ((it["match_id"] != it["match_id"].shift()) | (it["period"] != it["period"].shift())
                 | ((it["t"] - it["t"].shift()) >= FASE_GAP))
        it["grupo"] = nueva.cumsum()
        f = it.groupby("grupo").agg(
            match_id=("match_id", "first"), period=("period", "first"),
            index=("index", "first"), index_fin=("index", "last"),
            t_ini=("t", "first"), t_fin=("t", "last"),
            n_intentos=("index", "size"), x_media=("x", "mean"),
            gap_max=("t", lambda s: s.diff().max()))
        f = f[f["n_intentos"] >= FASE_MIN].copy()
        # Recupera si el EQ abre posesión desde el primer intento (incluido) hasta 5 s después del último
        f = recupera(f, pos, t_ref="t_fin", estricto=False)
        f = f.rename(columns={"regain_5s": "recupera"}).drop(columns=["t_inicio", "index_inicio"])
        f = f.rename(columns={"t_ini": "t_inicio"})
        f["variante"] = variante
        partes.append(f)
    out = pd.concat(partes, ignore_index=True)
    out = out.sort_values(["variante", "match_id", "index"])
    out["fase_id"] = out.groupby(["variante", "match_id"]).cumcount().astype("Int64")
    out["duracion"] = out["t_fin"] - out["t_inicio"]
    out = con_contexto(out, ctx)
    cols = ["match_id", "variante", "fase_id", "period", "index", "index_fin", "t_inicio", "t_fin",
            "duracion", "n_intentos", "x_media", "recupera", "gap_max"] + CONTEXTO
    out = out[cols].reset_index(drop=True)
    out["variante"] = out["variante"].astype("category")
    out["n_intentos"] = out["n_intentos"].astype("Int64")
    out["recupera"] = out["recupera"].astype("boolean")
    return out


# ---------------------------------------------------------------- D3: pérdidas, contrapresión y regain_5s

def d3_perdidas(ev, pos, ctx):
    eq_pos = ev["possession_team_id"] == EQ
    cand = ev.loc[ev["es_eq"] & eq_pos & ev["es_perdida_tipo"] & ev["juego_abierto"],
                  ["match_id", "index", "possession", "period", "t", "x", "type_name"]]
    # La pérdida es el último evento de pérdida de la posesión y la siguiente posesión es del rival
    cand = cand.sort_values(["match_id", "index"]).groupby(["match_id", "possession"]).tail(1)
    m = siguiente_inicio(cand, pos)
    m = m[(m["team_sig"] != EQ) & (m["period_sig"] == m["period"])][cand.columns]
    p = recupera(m, pos)
    p["segundos_a_recuperar"] = (p["t_inicio"] - p["t"]).where(p["period_sig"] == p["period"])

    # Contrapresión: algún evento del EQ con counterpress en los 5 s siguientes, mismo periodo
    cp = ev.loc[ev["es_eq"] & ev["es_cp"], ["match_id", "index", "period", "t"]].rename(
        columns={"index": "index_cp", "period": "period_cp", "t": "t_cp"}).sort_values("index_cp")
    p = pd.merge_asof(p.drop(columns=["index_inicio", "t_inicio", "period_sig", "team_sig"]).sort_values("index"),
                      cp, left_on="index", right_on="index_cp", by="match_id",
                      direction="forward", allow_exact_matches=False)
    p["con_contrapresion"] = ((p["period_cp"] == p["period"]) & ((p["t_cp"] - p["t"]) <= VENTANA)).fillna(False).astype(bool)

    p = con_contexto(p.sort_values(["match_id", "index"]), ctx)
    p = p.rename(columns={"type_name": "tipo_perdida"})
    out = p[["match_id", "index", "possession", "period", "t", "x", "tipo_perdida", "con_contrapresion",
             "regain_5s", "segundos_a_recuperar"] + CONTEXTO].reset_index(drop=True)
    out["tipo_perdida"] = out["tipo_perdida"].astype("string").astype("category")
    out[["con_contrapresion", "regain_5s"]] = out[["con_contrapresion", "regain_5s"]].astype("boolean")
    return out


def regains_de_presion(ev, pos):
    """Presiones del EQ seguidas de una posesión del EQ en <= 5 s (para comparar con StatsBomb)."""
    pr = ev.loc[ev["es_eq"] & ev["es_presion"], ["match_id", "index", "period", "t", "es_cp"]]
    r = recupera(pr, pos)
    return pd.DataFrame({
        "presiones_regain": r.groupby("match_id")["regain_5s"].sum(),
        "contrapresiones_regain": r[r["es_cp"]].groupby("match_id")["regain_5s"].sum(),
    })


# ---------------------------------------------------------------- D5: transiciones

def d5_transiciones(ev, pos, ctx):
    # Cambio de posesión: posesión no administrativa cuyo equipo difiere de la anterior,
    # mismo periodo, y que empieza en juego abierto
    p = pos.copy()
    previo = p.groupby("match_id")[["pos_team", "period"]].shift()
    cambio = (p["pos_team"] != previo["pos_team"]) & (p["period"] == previo["period"]) & p["play_pattern_id"].isin(JUEGO_ABIERTO)
    tr = p[cambio.fillna(False)].reset_index(drop=True)
    tr["tipo"] = np.where(tr["pos_team"] == EQ, "ofensiva", "defensiva")

    # Ventana: eventos no administrativos desde el inicio de la posesión nueva hasta 5 s, mismo periodo
    na = ev[~ev["es_adm"]].reset_index(drop=True)
    na["t_acum"] = na.groupby(["match_id", "period"])["t"].cummax()
    filas, trans = [], []
    for (mid, per), seg in na.groupby(["match_id", "period"], sort=False):
        tseg = tr[(tr["match_id"] == mid) & (tr["period"] == per)]
        if tseg.empty:
            continue
        ini = np.searchsorted(seg["index"].to_numpy(), tseg["index_inicio"].to_numpy())
        fin = np.searchsorted(seg["t_acum"].to_numpy(), tseg["t_inicio"].to_numpy() + VENTANA, side="right")
        fin = np.maximum(fin, ini + 1)
        largo = fin - ini
        pos_ev = np.concatenate([np.arange(a, z) for a, z in zip(ini, fin)])
        filas.append(seg.index.to_numpy()[pos_ev])
        trans.append(np.repeat(tseg.index.to_numpy(), largo))
    w = na.loc[np.concatenate(filas)].assign(tr_id=np.concatenate(trans))
    w["gana"] = w["team_id"] == tr.loc[w["tr_id"], "pos_team"].to_numpy()

    eq, rv = w["es_eq"], ~w["es_eq"]
    gw = w.groupby("tr_id")
    tr["n_eventos"] = gw.size()
    tr["n_eventos_eq"] = w[eq].groupby("tr_id").size()
    tr["tiros_eq"] = w[eq & w["es_tiro_np"]].groupby("tr_id").size()
    tr["xg_eq"] = w[eq & w["es_tiro_np"]].groupby("tr_id")["shot_statsbomb_xg"].sum()
    tr["tiros_rival"] = w[rv & w["es_tiro_np"]].groupby("tr_id").size()
    tr["xg_rival"] = w[rv & w["es_tiro_np"]].groupby("tr_id")["shot_statsbomb_xg"].sum()
    tr["obv_eq"] = w[eq].groupby("tr_id")["obv_total_net"].sum()
    gx = w[w["gana"] & w["x"].notna()].groupby("tr_id")["x"]
    tr["avance"] = gx.max() - gx.first()   # del equipo que gana el balón, en su perspectiva
    tr["con_contrapresion"] = w[eq & w["es_cp"]].groupby("tr_id").size().reindex(tr.index).fillna(0).gt(0)
    tr["pct_is_transition"] = gw["is_transition"].apply(lambda s: s.astype("float64").mean())
    tr["duracion_ventana"] = gw["t"].max() - tr["t_inicio"]

    conteos = ["n_eventos", "n_eventos_eq", "tiros_eq", "tiros_rival"]
    tr[conteos] = tr[conteos].fillna(0).astype("Int64")
    tr[["xg_eq", "xg_rival", "obv_eq"]] = tr[["xg_eq", "xg_rival", "obv_eq"]].fillna(0.0)

    # Ubicación del cambio en la perspectiva del EQ
    x_eq = ev[["match_id", "index", "x_eq"]].rename(columns={"index": "index_inicio", "x_eq": "x_eq_inicio"})
    tr = tr.merge(x_eq, on=["match_id", "index_inicio"], how="left")
    tr = con_contexto(tr.rename(columns={"index_inicio": "index", "t_inicio": "t"}), ctx)
    out = tr[["match_id", "index", "possession", "period", "t", "tipo", "x_eq_inicio", "n_eventos", "n_eventos_eq",
              "tiros_eq", "xg_eq", "tiros_rival", "xg_rival", "obv_eq", "avance", "con_contrapresion",
              "pct_is_transition", "duracion_ventana"] + CONTEXTO].sort_values(["match_id", "index"]).reset_index(drop=True)
    out["tipo"] = out["tipo"].astype("category")
    out["con_contrapresion"] = out["con_contrapresion"].astype("boolean")
    # Para validar: proporción de is_transition dentro y fuera de las ventanas
    dentro = na.index.isin(np.concatenate(filas))
    it = na["is_transition"].astype("float64")
    return out, (it[dentro].mean(), it[~dentro].mean())


# ---------------------------------------------------------------- P1 y P2: balón parado

def marcar_balon_parado(ev):
    st = ev["shot_type_name"].astype("string")
    pt = ev["pass_type_name"].astype("string")
    ev["es_fk_directo"] = ((ev["type_name"] == "Shot") & st.eq("Free Kick")).fillna(False).astype(bool)
    # Regla que reproduce a StatsBomb: el tiro trae set_piece_phase o es tiro libre directo
    ev["es_tiro_bp"] = ev["es_tiro_np"] & (ev["set_piece_phase"].notna() | ev["es_fk_directo"])
    saque_pase = (ev["type_name"] == "Pass") & pt.isin(list(SAQUES)).fillna(False)
    ev["es_saque"] = saque_pase | ev["es_fk_directo"]
    ev["tipo_saque"] = pt.map(SAQUES).where(saque_pase).mask(ev["es_fk_directo"], "Free Kick")
    return ev


def p1_posesiones(ev, pos, ctx):
    bp = pos[pos["play_pattern_id"].isin(list(TIPOS_BP))].copy()
    bp["set_piece_type"] = bp["play_pattern_id"].map(TIPOS_BP)
    na = ev[~ev["es_adm"]].merge(bp[["match_id", "possession", "pos_team"]], on=["match_id", "possession"])
    propio = na[na["team_id"] == na["pos_team"]]
    g = propio.groupby(["match_id", "possession"])
    saques = propio[propio["es_saque"]].groupby(["match_id", "possession"])
    agg = pd.DataFrame({
        "n_saques": saques.size(),
        "x_saque": saques["x"].first(),
        "y_saque": saques["y"].first(),
        "es_directo": g["es_fk_directo"].any(),
        "tiros": propio[propio["es_tiro_bp"]].groupby(["match_id", "possession"]).size(),
        "xg": propio[propio["es_tiro_bp"]].groupby(["match_id", "possession"])["shot_statsbomb_xg"].sum(),
        "goles": propio[propio["es_tiro_bp"] & (propio["shot_outcome_name"].astype("string") == "Goal")]
                 .groupby(["match_id", "possession"]).size(),
        "tiros_posesion": propio[propio["es_tiro_np"]].groupby(["match_id", "possession"]).size(),
        "set_piece_phase_max": g["set_piece_phase"].max(),
    })
    out = bp.join(agg, on=["match_id", "possession"])
    conteos = ["n_saques", "tiros", "goles", "tiros_posesion"]
    out[conteos] = out[conteos].fillna(0).astype("Int64")
    out["xg"] = out["xg"].fillna(0.0)
    out["es_directo"] = out["es_directo"].fillna(False).astype("boolean")
    out["termina_en_tiro"] = (out["tiros"] > 0).astype("boolean")
    # Sin saque propio la posesión solo hereda el play_pattern (p. ej. el rival recupera tras un corner)
    out["con_saque"] = (out["n_saques"] > 0).astype("boolean")
    out["lado"] = np.where(out["pos_team"] == EQ, "a_favor", "en_contra")
    out = con_contexto(out.rename(columns={"index_inicio": "index", "pos_team": "team_id", "t_inicio": "t"}), ctx)
    cols = ["match_id", "possession", "index", "period", "t", "team_id", "lado", "set_piece_type", "n_saques",
            "con_saque", "es_directo", "x_saque", "y_saque", "tiros", "xg", "goles", "termina_en_tiro", "tiros_posesion",
            "set_piece_phase_max"] + CONTEXTO
    out = out[cols].sort_values(["match_id", "possession"]).reset_index(drop=True)
    out[["lado", "set_piece_type"]] = out[["lado", "set_piece_type"]].astype("category")
    return out


def zona_remate(x, y):
    chica = (x >= 114) & y.between(30, 50)
    grande = (x >= AREA_X) & y.between(AREA_Y0, AREA_Y1)
    return pd.Series(np.select([chica, grande], ["area_chica", "area_grande"], "fuera_del_area"), index=x.index)


def p2_tiros(ev, ctx):
    s = ev[ev["es_tiro_np"] & ev["x"].notna()].copy()
    s["origen"] = np.where(s["es_tiro_bp"], "balon_parado", "juego_abierto")
    s["set_piece_type"] = s["play_pattern_id"].map(TIPOS_BP).where(s["es_tiro_bp"])
    s["lado"] = np.where(s["es_eq"], "a_favor", "en_contra")
    s["zona_remate"] = zona_remate(s["x"], s["y"])
    s["gol"] = (s["shot_outcome_name"].astype("string") == "Goal").fillna(False).astype("boolean")
    s = s.merge(ctx[["match_id", "index", "cell_6x5"]], on=["match_id", "index"], how="left")
    s = con_contexto(s, ctx)
    s = s.rename(columns={"shot_statsbomb_xg": "xg", "shot_body_part_name": "parte_cuerpo",
                          "shot_first_time": "primer_toque"})
    cols = ["match_id", "index", "period", "t", "team_id", "lado", "origen", "set_piece_type", "set_piece_phase",
            "es_fk_directo", "x", "y", "zona_remate", "cell_6x5", "xg", "gol", "parte_cuerpo", "primer_toque"] + CONTEXTO
    out = s[cols].sort_values(["match_id", "index"]).reset_index(drop=True)
    for c in ["lado", "origen", "set_piece_type", "zona_remate"]:
        out[c] = out[c].astype("category")
    out["es_fk_directo"] = out["es_fk_directo"].astype("boolean")
    out["primer_toque"] = b(out["primer_toque"]).astype("boolean")
    return out


def bp_partidos(ev, posbp, tiros, partidos, tms):
    """Una fila por partido, lado y tipo (Corner, Free Kick, Throw In y Juego abierto)."""
    rival = partidos.set_index("match_id")["rival_id"]
    filas = []
    for mid in partidos["match_id"]:
        for lado, tid in [("a_favor", EQ), ("en_contra", int(rival[mid]))]:
            for tipo in list(TIPOS_BP.values()) + ["Juego abierto"]:
                filas.append((mid, lado, tipo, tid))
    d = pd.DataFrame(filas, columns=["match_id", "lado", "set_piece_type", "team_id"])
    llave = ["match_id", "team_id", "set_piece_type"]

    sq = ev[ev["es_saque"]].groupby(["match_id", "team_id", "tipo_saque"]).size().rename("saques")
    sq.index = sq.index.set_names(llave)
    pb = posbp[posbp["con_saque"]].groupby(["match_id", "team_id", "set_piece_type"], observed=True).agg(
        posesiones=("possession", "size"), posesiones_con_tiro=("termina_en_tiro", "sum"))
    tipo_tiro = tiros["set_piece_type"].astype("string").fillna("Juego abierto")
    tt = tiros.assign(set_piece_type=tipo_tiro).groupby(llave).agg(
        tiros=("xg", "size"), xg=("xg", "sum"), goles=("gol", "sum"))
    d = d.join(sq, on=llave).join(pb, on=llave).join(tt, on=llave)

    # Referencia de StatsBomb (fila del equipo que ejecuta la jugada)
    ref = {"Corner": ("team_match_corners", "team_match_shots_from_corners", "team_match_corner_xg"),
           "Free Kick": ("team_match_free_kicks", "team_match_shots_from_free_kicks", "team_match_free_kick_xg"),
           "Throw In": ("team_match_throw_ins", "team_match_shots_from_throw_ins", "team_match_throw_in_xg")}
    t = tms.set_index(["match_id", "team_id"])
    for c, i in [("saques_sb", 0), ("tiros_sb", 1), ("xg_sb", 2)]:
        d[c] = [t.at[(m, tid), ref[tp][i]] if tp in ref else np.nan
                for m, tid, tp in zip(d["match_id"], d["team_id"], d["set_piece_type"])]
    d.loc[d["set_piece_type"] == "Juego abierto", "xg_sb"] = [
        t.at[(m, tid), "team_match_op_xg"] for m, tid in
        zip(d.loc[d["set_piece_type"] == "Juego abierto", "match_id"], d.loc[d["set_piece_type"] == "Juego abierto", "team_id"])]

    conteos = ["saques", "posesiones", "posesiones_con_tiro", "tiros", "goles", "saques_sb", "tiros_sb"]
    d[conteos] = d[conteos].astype("Float64").fillna(0).astype("Int64")
    es_ja = d["set_piece_type"] == "Juego abierto"
    d.loc[es_ja, ["saques", "posesiones", "posesiones_con_tiro", "saques_sb", "tiros_sb"]] = pd.NA
    d["xg"] = d["xg"].fillna(0.0)
    d["xg_sb"] = d["xg_sb"].astype("float64")
    d["xg_por_tiro"] = razon(d["xg"], d["tiros"])
    d["pct_posesiones_con_tiro"] = razon(d["posesiones_con_tiro"], d["posesiones"])
    info = partidos.set_index("match_id")[["torneo", "fase", "es_final"]]
    d = d.join(info, on="match_id")
    d[["lado", "set_piece_type"]] = d[["lado", "set_piece_type"]].astype("category")
    return d


# ---------------------------------------------------------------- tablas de apoyo

def por_zonas(ev, ctx):
    acciones = {"presion": "es_presion", "entrada": "es_entrada", "intercepcion": "es_intercepcion",
                "recuperacion": "es_recuperacion", "bloqueo": "es_bloqueo", "despeje": "es_despeje",
                "falta": "es_falta"}
    base = ev[ev["es_eq"]].merge(ctx[["match_id", "index", "cell_6x5"]], on=["match_id", "index"])
    base = base[base["cell_6x5"].notna()]
    partes = [base.loc[base[col], ["match_id", "cell_6x5"]].assign(accion=nombre) for nombre, col in acciones.items()]
    z = pd.concat(partes).groupby(["match_id", "accion", "cell_6x5"]).size().rename("n").reset_index()
    z["n"] = z["n"].astype("Int64")
    z["accion"] = z["accion"].astype("category")
    return z


def por_liga(liga, torneos_jardine):
    # Solo fase regular: todos los equipos juegan 17 partidos y el ranking es comparable
    liga = liga[liga["fase"].astype("string") == "regular"]
    cols = {  # columna de StatsBomb: (nombre, menor es mejor)
        "team_match_ppda": ("ppda", True),
        "team_match_defensive_distance": ("defensive_distance", False),
        "team_match_pressures": ("presiones", False),
        "team_match_fhalf_pressures_ratio": ("pct_presiones_mitad_rival", False),
        "team_match_counterpressures": ("contrapresiones", False),
        "team_match_pressure_regains": ("presiones_regain", False),
        "team_match_counterpressure_regains": ("contrapresiones_regain", False),
        "team_match_np_xg_conceded": ("xg_contra_np", True),
        "team_match_transition_xg_conceded": ("xg_contra_transicion", True),
        "team_match_counter_attacking_shots_conceded": ("tiros_contragolpe_contra", True),
    }
    out = (liga.groupby(["team_id", "torneo"], observed=True)
           .agg(team_name=("team_name", "first"), partidos=("match_id", "nunique"),
                **{v[0]: (k, "mean") for k, v in cols.items()})
           .reset_index())
    for nombre, menor in cols.values():
        out[f"rank_{nombre}"] = (out.groupby("torneo", observed=True)[nombre]
                                 .rank(ascending=menor, method="min").astype("Int64"))
    out["es_america"] = (out["team_id"] == EQ).astype("boolean")
    # La liga cubre 8 torneos; los anteriores a Jardine son la época del grupo de contraste
    out["es_jardine"] = (out["es_america"] & out["torneo"].astype("string").isin(torneos_jardine)).astype("boolean")
    out["team_name"] = out["team_name"].astype("string")
    out["partidos"] = out["partidos"].astype("Int64")
    return out


def validar_posesiones(pos, ctx_pos):
    """Las posesiones no administrativas deben ser las mismas de contexto_posesiones (las que usa ataque)."""
    y = ctx_pos[~b(ctx_pos["es_administrativa"])]
    m = pos.merge(y, on=["match_id", "possession"], how="outer", indicator=True)
    fallas = []
    if (m["_merge"] != "both").any():
        fallas.append(f"posesiones: {int((m['_merge'] != 'both').sum())} posesiones no coinciden con contexto_posesiones")
    a = m[m["_merge"] == "both"]
    distintas = ((a["pos_team"] != a["possession_team_id"]) | (a["period_x"] != a["period_y"])
                 | (a["play_pattern_id"].map(PATRONES) != a["play_pattern_name"].astype("string"))).fillna(True)
    if distintas.any():
        fallas.append(f"posesiones: {int(distintas.sum())} difieren de contexto_posesiones en equipo, periodo o patrón")
    if not fallas:
        print(f"[OK] posesiones: las {len(pos):,} no administrativas coinciden con contexto_posesiones "
              f"(equipo, periodo y play_pattern)")
    return fallas


def por_partido(ev, partidos, ctx_part, tms, fases, perdidas, trans, regains):
    d = d1_d2_d4(ev, ["match_id"])
    d = d.join(regains)
    d["contrapresiones"] = ev[ev["es_eq"] & ev["es_presion"] & ev["es_cp"]].groupby("match_id").size()

    pe = perdidas.groupby("match_id")
    d["perdidas"] = pe.size()
    d["perdidas_regain_5s"] = pe["regain_5s"].sum()
    d["perdidas_con_contrapresion"] = pe["con_contrapresion"].sum()
    d["perdidas_cp_regain_5s"] = perdidas[perdidas["con_contrapresion"]].groupby("match_id")["regain_5s"].sum()

    fa = fases[fases["variante"] == "intentos"].groupby("match_id")
    d["fases_presion"] = fa.size()
    d["fases_presion_recupera"] = fa["recupera"].sum()
    d["fases_presion_duracion_media"] = fa["duracion"].mean()
    d["fases_presion_x_media"] = fa["x_media"].mean()
    d["fases_solo_pressure"] = fases[fases["variante"] == "solo_pressure"].groupby("match_id").size()

    td = trans[trans["tipo"] == "defensiva"].groupby("match_id")
    to = trans[trans["tipo"] == "ofensiva"].groupby("match_id")
    d["transiciones_def"] = td.size()
    d["transiciones_def_con_cp"] = td["con_contrapresion"].sum()
    d["tiros_rival_trans_def"] = td["tiros_rival"].sum()
    d["xg_rival_trans_def"] = td["xg_rival"].sum()
    d["transiciones_of"] = to.size()
    d["tiros_eq_trans_of"] = to["tiros_eq"].sum()
    d["xg_eq_trans_of"] = to["xg_eq"].sum()
    d["obv_eq_trans_of"] = to["obv_eq"].sum()

    conteos = ["presiones_regain", "contrapresiones_regain", "contrapresiones", "perdidas", "perdidas_regain_5s",
               "perdidas_con_contrapresion", "perdidas_cp_regain_5s", "fases_presion", "fases_presion_recupera",
               "fases_solo_pressure", "transiciones_def", "transiciones_def_con_cp", "tiros_rival_trans_def",
               "transiciones_of", "tiros_eq_trans_of"]
    d[conteos] = d[conteos].fillna(0).astype("Int64")
    d["tasa_regain_5s"] = razon(d["perdidas_regain_5s"], d["perdidas"])
    d["tasa_regain_5s_cp"] = razon(d["perdidas_cp_regain_5s"], d["perdidas_con_contrapresion"])

    sb = tms[tms["team_id"] == EQ].set_index("match_id")
    ref = {"team_match_pressures": "presiones_sb", "team_match_fhalf_pressures": "presiones_mitad_rival_sb",
           "team_match_counterpressures": "contrapresiones_sb", "team_match_pressure_regains": "presiones_regain_sb",
           "team_match_counterpressure_regains": "contrapresiones_regain_sb", "team_match_ppda": "ppda_sb",
           "team_match_defensive_distance": "defensive_distance_sb",
           "team_match_transition_xg_conceded": "xg_rival_transicion_sb",
           "team_match_time_in_transition": "time_in_transition_sb"}
    d = d.join(sb[list(ref)].rename(columns=ref))

    info = partidos.set_index("match_id")[["match_date", "torneo", "fase", "es_final", "rival_id", "rival_nombre",
                                           "es_local", "resultado"]]
    pc = ctx_part.set_index("match_id")[["is_home", "stage", "rival_strength_tercil"]]
    return info.join(pc).join(d).reset_index()


# ---------------------------------------------------------------- validaciones

def validar(t, ev, partidos, ctx, dentro_fuera, var_ppda):
    errores, avisos = [], []
    dp = t["defensa_partidos"]
    ids = set(partidos["match_id"])

    llaves = {"defensa_partidos": ["match_id"], "defensa_periodos": ["match_id", "period"],
              "defensa_fases_presion": ["match_id", "variante", "fase_id"],
              "defensa_perdidas": ["match_id", "index"], "defensa_transiciones": ["match_id", "index"],
              "defensa_zonas": ["match_id", "accion", "cell_6x5"], "defensa_liga": ["team_id", "torneo"],
              "balon_parado_posesiones": ["match_id", "possession"], "balon_parado_tiros": ["match_id", "index"],
              "balon_parado_partidos": ["match_id", "lado", "set_piece_type"]}
    for nombre, ll in llaves.items():
        dup = int(t[nombre].duplicated(ll).sum())
        if dup:
            errores.append(f"{nombre}: {dup} llaves duplicadas en {ll}")
    if len(dp) != N_PARTIDOS or set(dp["match_id"]) != ids:
        errores.append(f"defensa_partidos no trae exactamente los {N_PARTIDOS} partidos de partidos")
    for nombre in ["defensa_periodos", "defensa_fases_presion", "defensa_perdidas", "defensa_transiciones", "defensa_zonas",
                   "balon_parado_posesiones", "balon_parado_tiros", "balon_parado_partidos"]:
        extra = set(t[nombre]["match_id"]) - ids
        if extra:
            errores.append(f"{nombre}: match_id fuera de partidos {sorted(extra)[:5]}")
    if set(t["defensa_periodos"].query("period <= 2")["match_id"]) != ids:
        errores.append("defensa_periodos: falta algún partido en los periodos 1 y 2")

    llaves_ev = set(zip(ctx["match_id"], ctx["index"]))
    for nombre in ["defensa_fases_presion", "defensa_perdidas", "defensa_transiciones",
                   "balon_parado_posesiones", "balon_parado_tiros"]:
        sin = sum((m, i) not in llaves_ev for m, i in zip(t[nombre]["match_id"], t[nombre]["index"]))
        if sin:
            errores.append(f"{nombre}: {sin} filas con un index que no existe en contexto_eventos")
        if t[nombre]["score_state"].isna().any():
            errores.append(f"{nombre}: score_state nulo en {int(t[nombre]['score_state'].isna().sum())} filas")

    # D1 y B5: conteo exacto de Pressure contra StatsBomb
    dif = dp[dp["presiones"] != dp["presiones_sb"]]
    if len(dif):
        errores.append(f"presiones no cuadra con team_match_pressures en {len(dif)} partidos (ej. {dif['match_id'].iloc[0]})")
    # D3: StatsBomb no documenta su conteo de contrapresiones y no se reproduce exacto; se informa
    dif = dp["contrapresiones"].astype("float64") - dp["contrapresiones_sb"].astype("float64")
    avisos.append(f"D3 contrapresiones (Pressure con counterpress) vs team_match_counterpressures: iguales en "
                  f"{int((dif == 0).sum())} de {N_PARTIDOS} partidos, diferencia media {dif.mean():+.2f}, "
                  f"rango {int(dif.min())} a {int(dif.max())}")
    dif = (dp["presiones_mitad_rival"] - dp["presiones_mitad_rival_sb"]).abs()
    avisos.append(f"D1 presiones en x >= 60 vs team_match_fhalf_pressures: iguales en {int((dif == 0).sum())} de "
                  f"{N_PARTIDOS} partidos, diferencia máxima {int(dif.max())}")

    # Rangos
    for nombre, cols in [("defensa_partidos", ["press_height", "defensive_line_height", "defensive_line_height_defensas"]),
                         ("defensa_periodos", ["press_height", "defensive_line_height"]),
                         ("defensa_fases_presion", ["x_media"])]:
        for c in cols:
            s = t[nombre][c].dropna()
            if ((s < 0) | (s > 120)).any():
                errores.append(f"{nombre}.{c} fuera de [0, 120]")
    for c in ["pct_presiones_altas", "tasa_regain_5s", "tasa_regain_5s_cp"]:
        s = dp[c].dropna()
        if ((s < 0) | (s > 1)).any():
            errores.append(f"defensa_partidos.{c} fuera de [0, 1]")
    for c in ["ppda", "press_height", "defensive_line_height"]:
        if dp[c].isna().any():
            errores.append(f"defensa_partidos.{c} nulo en {int(dp[c].isna().sum())} partidos")

    # B5: reglas de la fase
    f = t["defensa_fases_presion"]
    if (f["n_intentos"] < FASE_MIN).any() or (f["gap_max"] >= FASE_GAP).any():
        errores.append("defensa_fases_presion: hay fases con menos de 3 intentos o con huecos de 10 s o más")
    if (f["duracion"] < 0).any():
        errores.append("defensa_fases_presion: duración negativa")

    # D3: pérdidas y contrapresión
    p = t["defensa_perdidas"]
    if (p["segundos_a_recuperar"].dropna() < 0).any():
        errores.append("defensa_perdidas: segundos_a_recuperar negativo")

    # D5: la ventana no pasa de 5 s
    tr = t["defensa_transiciones"]
    if (tr["duracion_ventana"] > VENTANA + 1e-9).any():
        errores.append("defensa_transiciones: alguna ventana pasa de 5 s")
    if not tr["tipo"].astype("string").isin(["ofensiva", "defensiva"]).all():
        errores.append("defensa_transiciones: tipo fuera de {ofensiva, defensiva}")

    # P1 y P2: saques y tiros de balón parado, exactos contra StatsBomb, de los dos lados
    bp = t["balon_parado_partidos"]
    sp = bp[bp["set_piece_type"].astype("string") != "Juego abierto"]
    if len(bp) != N_PARTIDOS * 2 * 4:
        errores.append(f"balon_parado_partidos tiene {len(bp)} filas, se esperaban {N_PARTIDOS * 2 * 4}")
    for propia, ref in [("saques", "saques_sb"), ("tiros", "tiros_sb")]:
        dif = sp[sp[propia] != sp[ref]]
        if len(dif):
            r = dif.iloc[0]
            errores.append(f"P1/P2 {propia} de balón parado no cuadra con StatsBomb en {len(dif)} filas "
                           f"(ej. {r.match_id}, {r.lado}, {r.set_piece_type}: {r[propia]} contra {r[ref]})")
    tir = t["balon_parado_tiros"]
    if tir["xg"].isna().any():
        errores.append("balon_parado_tiros: hay tiros sin xG")
    if not set(tir["zona_remate"].astype("string")) <= {"area_chica", "area_grande", "fuera_del_area"}:
        errores.append("balon_parado_tiros: zona_remate fuera de catálogo")
    pbp = t["balon_parado_posesiones"]
    sin = pbp[~pbp["con_saque"]]
    avisos.append(f"P1: {len(sin)} de {len(pbp)} posesiones con play_pattern de balón parado no tienen saque propio "
                  f"(heredan el patrón); quedan con con_saque = False y no cuentan como jugada. Traen "
                  f"{int(sin['tiros'].sum())} tiros de segunda jugada, que sí cuentan en los tiros por evento")
    con = pbp[pbp["con_saque"]].groupby(["match_id", "team_id", "set_piece_type"], observed=True)["n_saques"].sum()
    sq = sp.set_index(["match_id", "team_id", "set_piece_type"])["saques"]
    if (con.reindex(sq.index).fillna(0).astype("int64") != sq.astype("int64")).any():
        errores.append("P1: los saques de las posesiones con saque no suman los saques del partido")
    for tipo in ["Corner", "Free Kick", "Throw In", "Juego abierto"]:
        s = bp[bp["set_piece_type"].astype("string") == tipo]
        dif = (s["xg"] - s["xg_sb"]).abs()
        avisos.append(f"P2 xG {tipo} vs StatsBomb: iguales (±0.011) en {int((dif <= 0.011).sum())} de {len(s)}, "
                      f"diferencia máxima {dif.max():.3f}")

    # Liga
    if int(t["defensa_liga"]["es_jardine"].sum()) != dp["torneo"].nunique():
        errores.append("defensa_liga no trae un renglón del América por cada torneo de Jardine")

    # Informativas (sección 12 de las fichas)
    mejor = var_ppda.sort_values("mae").iloc[0]
    for _, r in var_ppda.iterrows():
        avisos.append(f"D2 PPDA [{r.pases} | {r.acciones}] vs team_match_ppda: corr {r['corr']:.3f}, "
                      f"razón mediana {r.razon_mediana:.2f}, error medio {r.mae:.2f}")
    avisos.append(f"D2 variante más cercana: pases {mejor.pases}, acciones {mejor.acciones}")
    for propia, sb in [("presiones_regain", "presiones_regain_sb"), ("contrapresiones_regain", "contrapresiones_regain_sb")]:
        r = dp[propia].astype("float64").sum() / dp[sb].astype("float64").sum()
        c = dp[propia].astype("float64").corr(dp[sb].astype("float64"))
        avisos.append(f"D3 {propia} vs {sb}: total propio / StatsBomb {r:.2f}, corr por partido {c:.3f}")
    avisos.append(f"D5 is_transition: {dentro_fuera[0]:.1%} dentro de las ventanas y {dentro_fuera[1]:.1%} fuera")
    sp = dp["xg_rival_trans_def"].corr(dp["xg_rival_transicion_sb"], method="spearman")
    avisos.append(f"D5 xG del rival en transición vs team_match_transition_xg_conceded: Spearman {sp:.3f}")
    c = dp["press_height"].corr(dp["defensive_line_height"])
    avisos.append(f"D4 vs D1: correlación entre defensive_line_height y press_height por partido {c:.3f}")
    return errores, avisos


# ---------------------------------------------------------------- escritura

def _bloqueados(salida, archivos):
    # Destinos que ya existen y no se pueden abrir para escribir (en Windows, abiertos en Excel o en otro proceso).
    # Es heurístico, como en 02_limpieza.py y 03_contexto.py: no detecta procesos que solo impiden borrar.
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


def _borrar(ruta):
    if ruta.is_dir():
        shutil.rmtree(ruta, ignore_errors=True)
    else:
        ruta.unlink(missing_ok=True)
    if ruta.exists():
        print(f"AVISO: no se pudo borrar el temporal {ruta}", file=sys.stderr)


def escribir(tablas, salida):
    # Mismo esquema que 03_contexto.py: todo va a una carpeta temporal dentro de `salida` y después se reemplaza
    # archivo por archivo. La temporal solo se borra si no se reemplazó nada o si se reemplazó todo.
    archivos = [f"{n}.parquet" for n in tablas]
    try:
        salida.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=".tmp_defensa_", dir=salida))
    except OSError as e:
        raise ErrorDefensa(f"no se pudo preparar {salida}: {e}") from e
    reemplazados = []
    try:
        try:
            for nombre, df in tablas.items():
                df.to_parquet(tmp / f"{nombre}.parquet", compression="zstd", index=False)
        except ERRORES_ESCRITURA as e:
            raise ErrorDefensa(f"no se pudo escribir en la carpeta temporal {tmp}; no se reemplazó nada: "
                               f"{type(e).__name__}: {e}") from e
        bloqueados = _bloqueados(salida, archivos)
        if bloqueados:
            raise ErrorDefensa(f"no se reemplazó nada en {salida}: estos destinos están bloqueados o no se pueden "
                               f"escribir: {bloqueados}. Ciérralos (por ejemplo en Excel) y vuelve a correr.")
        for archivo in archivos:
            try:
                os.replace(tmp / archivo, salida / archivo)
            except OSError as e:
                if not reemplazados:
                    raise ErrorDefensa(f"no se reemplazó nada en {salida}: falló {archivo} ({e})") from e
                raise ErrorDefensa(
                    f"el reemplazo quedó a medias en {salida}: ya se reemplazaron {reemplazados}; faltan "
                    f"{archivos[len(reemplazados):]} ({e}). Los que faltan siguen en la carpeta temporal {tmp}, que no "
                    "se borró: cópialos a mano o vuelve a correr.") from e
            except KeyboardInterrupt:
                if reemplazados:
                    print(f"AVISO: interrumpido a medias; ya se reemplazaron {reemplazados} y el resto sigue en la "
                          f"carpeta temporal {tmp}, que no se borró.", file=sys.stderr)
                raise
            reemplazados.append(archivo)
    finally:
        if not 0 < len(reemplazados) < len(archivos):
            _borrar(tmp)
    for viejo in salida.glob(".tmp_defensa_*"):
        if viejo != tmp:
            _borrar(viejo)


# ---------------------------------------------------------------- main

def calcular(interim, processed):
    partidos = leer(interim, "partidos")
    ev = leer(interim, "eventos")
    tms = leer(interim, "team_match_stats")
    liga = leer(interim, "team_match_stats_liga")
    ctx = leer(processed, "contexto_eventos")
    ctx_pos = leer(processed, "contexto_posesiones")
    ctx_part = leer(processed, "contexto_partidos")

    # Siempre por manager_id y team_id, nunca por nombre
    partidos = partidos[(partidos["entrenador_id"] == MANAGER_ID) & (partidos["equipo_id"] == EQ)]
    ev = preparar(ev, partidos)
    print(f"lee {len(ev):,} eventos de {ev['match_id'].nunique()} partidos (periodos 1 a 4)")
    pos = posesiones(ev)
    fallas = validar_posesiones(pos, ctx_pos)

    fases = b5_fases(ev, pos, ctx)
    perdidas = d3_perdidas(ev, pos, ctx)
    trans, dentro_fuera = d5_transiciones(ev, pos, ctx)
    regains = regains_de_presion(ev, pos)
    periodos = d1_d2_d4(ev, ["match_id", "period"]).reset_index()
    periodos["period"] = periodos["period"].astype("Int64")
    posbp = p1_posesiones(ev, pos, ctx)
    tiros = p2_tiros(ev, ctx)

    tablas = fijar_categorias({
        "defensa_partidos": por_partido(ev, partidos, ctx_part, tms, fases, perdidas, trans, regains),
        "defensa_periodos": periodos,
        "defensa_fases_presion": fases,
        "defensa_perdidas": perdidas,
        "defensa_transiciones": trans,
        "defensa_zonas": por_zonas(ev, ctx),
        "defensa_liga": por_liga(liga, partidos["torneo"].astype("string").unique()),
        "balon_parado_posesiones": posbp,
        "balon_parado_tiros": tiros,
        "balon_parado_partidos": bp_partidos(ev, posbp, tiros, partidos, tms),
    })
    sb = tms[tms["team_id"] == EQ].set_index("match_id")["team_match_ppda"]
    return tablas, ev, partidos, ctx, dentro_fuera, variantes_ppda(ev, sb), fallas


def resumen(t):
    dp = t["defensa_partidos"]
    s = lambda c: dp[c].astype("float64").sum()
    print(f"Resumen de los {len(dp)} partidos:")
    print(f"  D1 presiones {int(s('presiones')):,}; altas (x >= 80) {s('presiones_altas') / s('presiones'):.1%}; "
          f"press_height medio {dp['press_height'].mean():.1f} yd")
    print(f"  D2 PPDA {s('ppda_pases_rival') / s('ppda_acciones'):.1f} (todos los pases), "
          f"{s('ppda_pases_rival_ja') / s('ppda_acciones'):.1f} (juego abierto)")
    print(f"  D3 pérdidas {int(s('perdidas')):,}; regain_5s {s('perdidas_regain_5s') / s('perdidas'):.1%}; "
          f"con contrapresión {s('perdidas_con_contrapresion') / s('perdidas'):.1%}, "
          f"y de ellas regain_5s {s('perdidas_cp_regain_5s') / s('perdidas_con_contrapresion'):.1%}")
    print(f"  D4 defensive_line_height medio {dp['defensive_line_height'].mean():.1f} yd "
          f"({dp['defensive_line_height_defensas'].mean():.1f} solo defensas)")
    print(f"  B5 fases de presión {int(s('fases_presion')):,} ({s('fases_presion_recupera') / s('fases_presion'):.1%} recuperan); "
          f"solo Pressure {int(s('fases_solo_pressure')):,}")
    print(f"  D5 transiciones defensivas {int(s('transiciones_def')):,} (xG rival {s('xg_rival_trans_def'):.1f}), "
          f"ofensivas {int(s('transiciones_of')):,} (xG EQ {s('xg_eq_trans_of'):.1f})")
    print(f"  D1 con 40 m (x >= {X_PRESION_ALTA_M:.2f}): altas {s('presiones_altas_40m') / s('presiones'):.1%}")
    bp = t["balon_parado_partidos"]
    r = bp.groupby(["lado", "set_piece_type"], observed=True)[["saques", "tiros", "xg", "goles"]].sum()
    for (lado, tipo), f in r.iterrows():
        print(f"  P1/P2 {lado:9s} {tipo:13s} saques {int(f.saques) if tipo != 'Juego abierto' else '-':>5} "
              f"tiros {int(f.tiros):4d}  xG {f.xg:5.1f}  goles {int(f.goles)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-escribir", action="store_true", help="calcula y valida sin escribir en data/processed/")
    ap.add_argument("--interim", type=Path, default=INTERIM, help=argparse.SUPPRESS)
    ap.add_argument("--processed", type=Path, default=PROCESSED, help=argparse.SUPPRESS)
    args = ap.parse_args()
    inicio = time.perf_counter()

    try:
        tablas, ev, partidos, ctx, dentro_fuera, var_ppda, fallas = calcular(args.interim, args.processed)
    except ErrorDefensa as e:
        print(f"ERROR: {e}\nNo se escribió nada.", file=sys.stderr)
        return 1

    errores, avisos = validar(tablas, ev, partidos, ctx, dentro_fuera, var_ppda)
    errores = fallas + errores
    for a in avisos:
        print(f"AVISO: {a}")
    if errores:
        print(f"ERROR: {len(errores)} validaciones duras fallaron:", file=sys.stderr)
        for e in errores:
            print(f"   {e}", file=sys.stderr)
        print("No se escribió nada.", file=sys.stderr)
        return 1
    for nombre, df in tablas.items():
        print(f"[OK] {nombre}: {len(df):,} filas, {df.shape[1]} columnas")
    resumen(tablas)

    if args.sin_escribir:
        print(f"Sin escribir (--sin-escribir). {time.perf_counter() - inicio:.1f} s")
        return 0
    try:
        escribir(tablas, args.processed)
    except ErrorDefensa as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"Escrito en {args.processed}/: {', '.join(tablas)}. {time.perf_counter() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
