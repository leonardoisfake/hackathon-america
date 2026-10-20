"""Contexto y espacio por evento (fase 3): fichas B1, C1 a C5 y E1 a E2 de la especificacion de metricas de Lee.

Uso:
    python scripts/03_contexto.py                 # calcula, valida y escribe en data/processed/
    python scripts/03_contexto.py --sin-escribir  # calcula y valida, sin escribir

Lee data/interim/ (salida de 02_limpieza.py) y escribe cuatro tablas y un CSV de control (ver SALIDA_*):
- contexto_eventos.parquet: una fila por evento, llave (match_id, index), solo la llave y las columnas nuevas
  (C1 match_clock, minute_bin; C2 goal_diff, goal_diff_clip, score_state; C3 is_home, rival_id, stage,
  match_week; C4 rival_strength, rival_strength_tercil, rival_ppg; C5 numerical_state, numerical_state_cat;
  E1 third, cell_6x5, zona14; E2 dist_goal, angle_goal).
- rival_strength.parquet: una fila por (team_id, torneo) de toda la liga, sin el equipo analizado.
- contexto_posesiones.parquet: una fila por posesion de StatsBomb de los periodos 1 a 4, llave (match_id,
  possession), con contexto al inicio, conteos y la posesion valida de B1 (posesion_fundida_id sin fundir filas).
- contexto_partidos.parquet: una fila por partido (91), con contexto, goles, expulsiones en cancha y minutos
  ganando, empatando y perdiendo ponderados por tiempo.
- control_posesiones_fundidas.csv: para revisar a mano, columna tipo: muestra fija de hasta 10 posesiones
  fundidas (solo el encabezado si no hay) y de hasta 10 pares descartados porque q empieza con reanudacion.

Cada ficha es una funcion que devuelve su frame (para reutilizarla en tablas por posesion y por partido) y
tiene una funcion validar_* que imprime [OK] o AVISO y devuelve las fallas duras. Las reglas, las desviaciones
de las fichas y la regla de expulsiones en cancha estan en docs/spec_03_contexto.md.

Codigos de salida: 0 si todo paso y se escribio (o no se pidio escribir); 1 si fallo una validacion dura, falta
un dato o fallo la escritura. Si falla una validacion no se escribe nada. Las salidas por evento, posesion y
partido deben traer exactamente los match_id de partidos. La escritura va a una carpeta temporal dentro de
data/processed/ y despues reemplaza archivo por archivo, tras comprobar que ningun destino esta bloqueado; si el
reemplazo queda a medias, el mensaje dice que archivos se reemplazaron y donde quedo la carpeta temporal.
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

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
# nombres de las salidas, aprobados por el equipo el 19-oct
SALIDA_EVENTOS = "contexto_eventos.parquet"
SALIDA_RIVALES = "rival_strength.parquet"
SALIDA_POSESIONES = "contexto_posesiones.parquet"
SALIDA_PARTIDOS = "contexto_partidos.parquet"
CONTROL_FUSION = "control_posesiones_fundidas.csv"  # muestra para revisar a mano las posesiones fundidas (B1)

EQ = 1229  # equipo analizado: America con Jardine (ya filtrado en partidos)
LLAVE = ["match_id", "index"]
STAGES_REGULAR = {1, 42, 44}  # competition_stage_id de fase regular (C3)
ESPERADO = {"partidos": 91, "regular": 66, "fase final": 25}
# jornadas de fase regular que faltan a proposito: las dirigio Diego Cervantes (excluidas como otro manager)
HUECOS_PERMITIDOS = {"Clausura 2025": {1, 2}}
PERIODO_PENALES = 5  # tanda de penales: C1, C2 y C5 quedan nulos

# categorias fijas para que no cambien entre corridas
BINS_MINUTO = ["0-15", "15-30", "30-45", "45+", "45-60", "60-75", "75-90", "90+", "ET"]
ESTADOS_MARCADOR = ["perdiendo", "empatando", "ganando"]
STAGES = ["regular", "fase final"]
TERCILES = ["débil", "medio", "fuerte"]
ESTADOS_NUMERICOS = ["inferioridad", "igualdad", "superioridad"]
TERCIOS = ["defensive_third", "midfield_third", "final_third"]  # mismas etiquetas que location_bucket

TARJETAS_EXPULSION = {"Red Card", "Second Yellow"}
END_REASON_EXPULSION = {"Red Card", "Second Yellow Card"}
ANCHO, ALTO = 120.0, 80.0
POSTES = (36.0, 44.0)  # y de los postes; la porteria rival esta en x = 120
DIST_PENAL = 12.0
BINS_DISTANCIA = [0, 6, 12, 18, 24, 30, np.inf]
# zona 14: 80 <= x < 102 y 26.7 <= y <= 53.3 (propuesta de la ficha E1)
ZONA14_X, ZONA14_Y = (80.0, 102.0), (26.7, 53.3)
JUEGO_ABIERTO = {1, 6}  # play_pattern Regular Play y From Counter, para comparar third con location_bucket
MIN_ACUERDO_TERCIO = 0.995

# B1: toques del rival sin direccion que no cortan la posesion (supuesto de la ficha), mas Ball Recovery con
# recovery_failure; balon parado = play_pattern 2, 3 y 4; umbrales de la posesion valida
TOQUES_SIN_DIRECCION = {"Block", "Clearance", "Miscontrol"}
PATRONES_BALON_PARADO = {2, 3, 4}
# una posesion que empieza con una reanudacion no se funde con la anterior (paso 1 de B1)
REANUDACIONES = {"From Corner", "From Free Kick", "From Throw In", "From Goal Kick", "From Kick Off"}
MIN_PASES_VALIDA, MIN_TIROS_VALIDA = 3, 1
N_MUESTRA_FUSION = 10
SEMILLA_MUESTRA = 0
LLAVE_POSESION = ["match_id", "possession"]

ERRORES_ESCRITURA = (OSError, ValueError, TypeError, pa.lib.ArrowException)

COLS_EVENTOS = ["match_id", "index", "period", "minute", "match_second", "timestamp", "type_name", "team_id",
                "player_id", "shot_outcome_name", "shot_type_name", "shot_statsbomb_xg", "foul_committed_card_name",
                "bad_behaviour_card_name", "x", "y", "location_bucket", "possession", "possession_team_id",
                "play_pattern_id", "play_pattern_name", "ball_recovery_recovery_failure", "es_administrativo"]
COLS_LIGA = ["match_id", "team_id", "team_name", "opposition_id", "torneo", "fase", "es_play_in",
             "team_match_np_xgd", "team_match_goals", "team_match_goals_conceded", "match_week"]


class ErrorContexto(Exception):
    pass


def leer(nombre, columnas=None):
    ruta = INTERIM / f"{nombre}.parquet"
    if not ruta.exists():
        raise ErrorContexto(f"no existe {ruta.relative_to(ROOT).as_posix()}; corre antes 02_limpieza.py")
    try:
        return pd.read_parquet(ruta, columns=columnas)
    except (OSError, ValueError, KeyError) as e:
        raise ErrorContexto(f"no se pudo leer {nombre}: {type(e).__name__}: {e}") from e


def _texto(s):
    # Categorias y texto a string, para comparar y unir sin depender de las categorias de cada corrida.
    return s.astype("string")


def _cat(valores, categorias, indice, nulos=None):
    # Arreglo de texto a category con categorias fijas; `nulos` es una mascara de filas que quedan en NA.
    s = pd.Series(pd.Categorical(valores, categories=categorias, ordered=True), index=indice)
    return s.mask(nulos) if nulos is not None else s


def _penales(ev):
    return (ev["period"] == PERIODO_PENALES).fillna(False).to_numpy(dtype=bool)


def _ok(msg):
    print(f"[OK] {msg}")


def _aviso(msg):
    print(f"AVISO: {msg}")


# ---------------------------------------------------------------- C1 reloj

def c1_reloj(ev):
    # match_clock en minutos (reusa match_second) y minute_bin en ventanas de 15 minutos por periodo.
    m, per = ev["minute"].to_numpy(dtype="float64", na_value=np.nan), ev["period"].to_numpy(dtype="float64", na_value=np.nan)
    bins = np.select(
        [(per == 1) & (m < 15), (per == 1) & (m < 30), (per == 1) & (m < 45), per == 1,
         (per == 2) & (m < 60), (per == 2) & (m < 75), (per == 2) & (m < 90), per == 2,
         (per == 3) | (per == 4)],
        BINS_MINUTO, default=None)
    return pd.DataFrame({
        "match_clock": ev["match_second"].astype("float64") / 60,
        "minute_bin": _cat(bins, BINS_MINUTO, ev.index),
    }, index=ev.index)


def validar_c1(ev, c1):
    fallas = []
    ts_min = pd.to_timedelta(ev["timestamp"]).groupby([ev["match_id"], ev["period"]]).min()
    no_cero = ts_min[ts_min != pd.Timedelta(0)]
    if no_cero.empty:
        _ok(f"C1 timestamp minimo = 0 en los {len(ts_min)} pares (match_id, period)")
    else:
        fallas.append("C1: timestamp minimo distinto de cero en (match_id, period): "
                      + ", ".join(f"({int(m)}, {int(p)}) {t}" for (m, p), t in no_cero.items()))
    conteo = c1["minute_bin"].value_counts().reindex(BINS_MINUTO)
    vacios = conteo[conteo == 0].index.tolist()
    if vacios:
        fallas.append(f"C1: bins vacios en el agregado: {vacios}")
    else:
        _ok("C1 ningun bin vacio: " + ", ".join(f"{b} {n:,}" for b, n in conteo.items()))
    nulos = int(c1["minute_bin"].isna().sum())
    if nulos != int(_penales(ev).sum()):
        fallas.append(f"C1: {nulos} minute_bin nulos y {int(_penales(ev).sum())} eventos del periodo 5")
    # duracion: un periodo regular no deberia pasar 15 minutos de su final nominal
    tope = ev[ev["period"] <= 2].groupby(["match_id", "period"])["minute"].max().unstack()
    largos = tope[(tope[1] >= 60) | (tope[2] >= 105)]
    if not largos.empty:
        _aviso("C1 periodos con minuto maximo muy alto (el reloj incluye pausas; no se corrige): "
               + "; ".join(f"{mid}: 1T {r[1]}', 2T {r[2]}'" for mid, r in largos.iterrows()))
    return fallas


# ---------------------------------------------------------------- C2 marcador

def _goles(ev, autogol):
    # Mascaras de gol del EQ y del rival por evento. directo: Own Goal For cuenta para su team_id;
    # invertido: Own Goal Against cuenta para su team_id. La tanda de penales no cuenta.
    tipo = _texto(ev["type_name"])
    gol_tiro = (tipo == "Shot") & (_texto(ev["shot_outcome_name"]) == "Goal")
    gol_propio = tipo == ("Own Goal For" if autogol == "directo" else "Own Goal Against")
    gol = ((gol_tiro | gol_propio) & (ev["period"] < PERIODO_PENALES)).fillna(False).to_numpy(dtype=bool)
    eq = (ev["team_id"] == EQ).fillna(False).to_numpy(dtype=bool)
    return gol & eq, gol & ~eq


def c2_marcador(ev, autogol="directo"):
    # goal_diff = goles EQ - goles rival antes del evento, en orden (match_id, index); periodo 5 nulo.
    g_eq, g_r = _goles(ev, autogol)
    diff = pd.Series(g_eq.astype("int64") - g_r.astype("int64"), index=ev.index)
    antes = (diff.groupby(ev["match_id"]).cumsum() - diff).astype("Int64").mask(_penales(ev))
    estado = np.select([antes.fillna(0) < 0, antes.fillna(0) == 0], ESTADOS_MARCADOR[:2], default=ESTADOS_MARCADOR[2])
    return pd.DataFrame({
        "goal_diff": antes,
        "goal_diff_clip": antes.clip(-2, 2),
        "score_state": _cat(estado, ESTADOS_MARCADOR, ev.index, nulos=antes.isna()),
    }, index=ev.index)


def _marcadores_no_cuadran(ev, partidos, autogol):
    # Partidos cuyos goles acumulados no dan home_score y away_score con el criterio de autogol dado.
    g_eq, g_r = _goles(ev, autogol)
    tot = pd.DataFrame({"eq": g_eq, "r": g_r, "match_id": ev["match_id"]}).groupby("match_id").sum()
    p = partidos.set_index("match_id").join(tot).fillna({"eq": 0, "r": 0})
    local = p["home_team_id"] == EQ
    goles_local = np.where(local, p["eq"], p["r"])
    goles_visita = np.where(local, p["r"], p["eq"])
    malos = (goles_local != p["home_score"]) | (goles_visita != p["away_score"])
    return p.loc[malos.to_numpy(dtype=bool), ["home_score", "away_score"]].assign(
        local_calc=goles_local[malos.to_numpy(dtype=bool)], visita_calc=goles_visita[malos.to_numpy(dtype=bool)])


def elegir_autogol(ev, partidos):
    # Devuelve el criterio de autogol que cuadra los marcadores de todos los partidos, y las fallas si ninguno.
    malos = {}
    for criterio in ("directo", "invertido"):
        malos[criterio] = _marcadores_no_cuadran(ev, partidos, criterio)
        if malos[criterio].empty:
            _ok(f"C2 goles finales = home_score y away_score en los {len(partidos)} partidos "
                f"(criterio de autogol {criterio}: Own Goal {'For' if criterio == 'directo' else 'Against'} "
                "cuenta para su team_id)")
            return criterio, []
        _aviso(f"C2 criterio de autogol {criterio}: {len(malos[criterio])} partidos no cuadran: "
               f"{malos[criterio].to_dict('index')}")
    return None, [f"C2: ningun criterio de autogol cuadra los marcadores (directo {len(malos['directo'])} "
                  f"partidos, invertido {len(malos['invertido'])})"]


# ---------------------------------------------------------------- C3 partido

def c3_partido(partidos):
    # Una fila por partido: is_home, rival_id, stage, match_week y torneo (como string).
    stage = np.where(partidos["competition_stage_id"].isin(STAGES_REGULAR).to_numpy(dtype=bool), STAGES[0], STAGES[1])
    return pd.DataFrame({
        "match_id": partidos["match_id"],
        "is_home": (partidos["home_team_id"] == EQ).astype("boolean"),
        "rival_id": partidos["rival_id"].astype("Int64"),
        "stage": _cat(stage, STAGES, partidos.index),
        "match_week": partidos["match_week"].astype("Int64"),
        "torneo": _texto(partidos["torneo"]),
    }).reset_index(drop=True)


def validar_c3(partidos, c3, liga):
    fallas = []
    n = len(c3)
    por_stage = c3["stage"].value_counts()
    obtenido = {"partidos": n, "regular": int(por_stage.get("regular", 0)), "fase final": int(por_stage.get("fase final", 0))}
    if obtenido == ESPERADO:
        _ok(f"C3 {n} partidos: {obtenido['regular']} regulares y {obtenido['fase final']} de fase final")
    else:
        fallas.append(f"C3: se esperaba {ESPERADO} y salio {obtenido}")
    if not (partidos["equipo_id"] == EQ).all():
        fallas.append(f"C3: hay partidos con equipo_id distinto de {EQ}")
    local, visita = partidos["home_team_id"], partidos["away_team_id"]
    otro = local.where(visita == EQ, visita.where(local == EQ))
    malos = partidos.loc[(otro != partidos["rival_id"]).fillna(True).to_numpy(dtype=bool), "match_id"].tolist()
    if malos:
        fallas.append(f"C3: rival_id no es el otro equipo (o {EQ} no juega) en {malos}")
    else:
        _ok(f"C3 rival_id es el otro equipo en los {n} partidos; {int(c3['is_home'].sum())} de local")
    distintos = (_texto(partidos["fase"]) == "regular") != (c3["stage"].astype("string") == "regular")
    if distintos.any():
        _aviso(f"C3 stage no coincide con partidos.fase en {partidos.loc[distintos, 'match_id'].tolist()}")
    # huecos de jornada en fase regular, contra 1..jornada maxima de la liga en ese torneo
    reg = liga[_texto(liga["fase"]) == "regular"]
    tope = reg.groupby(_texto(reg["torneo"]))["match_week"].max()
    lineas = []
    por_torneo = dict(tuple(c3[c3["stage"] == "regular"].groupby("torneo")["match_week"]))
    for torneo in sorted(set(por_torneo) | set(HUECOS_PERMITIDOS)):
        semanas = por_torneo.get(torneo, pd.Series(dtype="Int64"))
        if torneo not in tope:
            fallas.append(f"C3: {torneo} no tiene fase regular en team_match_stats_liga")
            continue
        faltan = set(range(1, int(tope[torneo]) + 1)) - set(semanas.dropna().astype(int))
        repetidas = sorted(semanas[semanas.duplicated()].dropna().astype(int).unique().tolist())
        permitidos = HUECOS_PERMITIDOS.get(torneo, set())
        if faltan != permitidos:
            fallas.append(f"C3: {torneo} le faltan las jornadas {sorted(faltan)} y se permiten {sorted(permitidos)}")
        if repetidas:
            fallas.append(f"C3: {torneo} tiene jornadas repetidas en fase regular: {repetidas}")
        lineas.append(f"{torneo}: {len(semanas)} partidos, faltan jornadas {sorted(faltan) or 'ninguna'}"
                      + (" (permitidas: partidos de otro manager)" if faltan and faltan == permitidos else ""))
    print("C3 jornadas de fase regular por torneo:\n   " + "\n   ".join(lineas))
    return fallas


# ---------------------------------------------------------------- C4 fuerza del rival

def c4_rival_strength(liga):
    # Una fila por (team_id, torneo) de la liga sin el EQ: promedio de np_xgd y puntos por partido en fase regular,
    # sin el partido contra el EQ; tercil de np_xgd dentro del torneo.
    reg = liga[(_texto(liga["fase"]) == "regular").to_numpy(dtype=bool)]
    reg = reg[(reg["opposition_id"] != EQ).to_numpy(dtype=bool) & (reg["team_id"] != EQ).to_numpy(dtype=bool)]
    gf, gc = reg["team_match_goals"], reg["team_match_goals_conceded"]
    puntos = pd.Series(np.select([gf > gc, gf == gc], [3, 1], default=0), index=reg.index)
    df = pd.DataFrame({"team_id": reg["team_id"].astype("Int64"), "team_name": _texto(reg["team_name"]),
                       "torneo": _texto(reg["torneo"]), "np_xgd": reg["team_match_np_xgd"].astype("float64"),
                       "puntos": puntos.astype("float64")})
    out = df.groupby(["team_id", "torneo"]).agg(
        team_name=("team_name", "first"), partidos_regular=("np_xgd", "size"),
        rival_strength=("np_xgd", "mean"), rival_ppg=("puntos", "mean")).reset_index()
    out["partidos_regular"] = out["partidos_regular"].astype("Int64")
    # rank(method="first") evita bordes repetidos en qcut si dos equipos empatan
    tercil = out.groupby("torneo")["rival_strength"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
    out["rival_strength_tercil"] = _cat(np.asarray(TERCILES, dtype=object)[tercil.to_numpy(dtype="int64")],
                                        TERCILES, out.index)
    return out[["team_id", "team_name", "torneo", "partidos_regular", "rival_strength", "rival_strength_tercil",
                "rival_ppg"]].sort_values(["torneo", "rival_strength"], ascending=[True, False]).reset_index(drop=True)


def _spearman(a, b):
    # Spearman = Pearson sobre rangos promedio (sin scipy, que no esta en requirements.txt).
    return a.rank().corr(b.rank())


def validar_c4(liga, c3, c4):
    fallas = []
    play_in = liga[liga["es_play_in"].fillna(False).to_numpy(dtype=bool)]
    donde = play_in.groupby([_texto(play_in["torneo"]), _texto(play_in["fase"])]).size()
    en_regular = int((_texto(play_in["fase"]) == "regular").fillna(False).sum())
    if en_regular:
        fallas.append(f"C4: {en_regular} filas es_play_in tienen fase regular: {donde.to_dict()}")
    print(f"C4 filas es_play_in en team_match_stats_liga: {len(play_in)}, por (torneo, fase): {donde.to_dict()}"
          + ("; ninguna entra en fase regular" if len(play_in) and not en_regular else ""))
    reparto = c4.groupby("torneo")["rival_strength_tercil"].value_counts().unstack().reindex(columns=TERCILES)
    print("C4 terciles por torneo (" + "/".join(TERCILES) + "): "
          + ", ".join(f"{'/'.join(map(str, r))} en {n}" for r, n in
                      reparto.apply(tuple, axis=1).value_counts().items()))
    llaves = c3[["rival_id", "torneo"]].drop_duplicates().rename(columns={"rival_id": "team_id"})
    cruce = llaves.merge(c4, how="left", on=["team_id", "torneo"])
    sin = cruce[cruce["rival_strength"].isna()]
    if sin.empty:
        _ok(f"C4 los {len(llaves)} pares (rival, torneo) de los {len(c3)} partidos tienen rival_strength")
    else:
        fallas.append(f"C4: rivales sin rival_strength en su torneo: {sin[['team_id', 'torneo']].values.tolist()}")
    print(f"C4 partidos de fase regular por equipo y torneo (sin el partido contra {EQ}): "
          f"{c4['partidos_regular'].min()} a {c4['partidos_regular'].max()}")
    for torneo in sorted(c3["torneo"].unique()):
        t = c4[c4["torneo"] == torneo]
        fmt = lambda d: ", ".join(f"{r.team_name} {r.rival_strength:+.2f} ({r.rival_ppg:.2f} ppp)" for r in d.itertuples())
        print(f"C4 {torneo}: arriba {fmt(t.head(3))} | abajo {fmt(t.tail(3))}")
    rho = _spearman(c4["rival_strength"], c4["rival_ppg"])
    print(f"C4 Spearman entre rival_strength (np_xgd) y rival_ppg, {len(c4)} pares (equipo, torneo): {rho:.3f}")
    return fallas


# ---------------------------------------------------------------- C5 estado numerico

def _a_segundos(texto):
    return pd.to_timedelta(texto).dt.total_seconds()


def expulsiones(ev, posiciones):
    # Una fila por evento de expulsion (Red Card o Second Yellow en foul_committed o bad_behaviour), con en_cancha:
    # True si el jugador tiene un tramo en posiciones que cubre el momento de la tarjeta. Un to nulo llega al final.
    tarjeta = _texto(ev["foul_committed_card_name"]).fillna(_texto(ev["bad_behaviour_card_name"]))
    es = tarjeta.isin(TARJETAS_EXPULSION).fillna(False).to_numpy(dtype=bool)
    ex = ev.loc[es, LLAVE + ["period", "match_second", "team_id", "player_id"]].assign(tarjeta=tarjeta[es])
    tramos = posiciones[["match_id", "team_id", "player_id", "from", "to", "from_period", "to_period"]].copy()
    # momento como periodo * 1e5 + segundo de reloj, comparable entre periodos (match_second se repite entre periodos)
    tramos["desde"] = tramos["from_period"] * 100_000 + np.floor(_a_segundos(tramos["from"]))
    tramos["hasta"] = tramos["to_period"] * 100_000 + np.floor(_a_segundos(tramos["to"]))
    cruce = ex.merge(tramos, how="left", on=["match_id", "team_id", "player_id"])
    momento = cruce["period"] * 100_000 + cruce["match_second"]
    cubre = (momento >= cruce["desde"]) & ((momento <= cruce["hasta"]) | cruce["hasta"].isna())
    en_cancha = cubre.fillna(False).groupby([cruce["match_id"], cruce["index"]]).any()
    ex["en_cancha"] = ex.set_index(LLAVE).index.map(en_cancha).astype("boolean").fillna(False)
    return ex.reset_index(drop=True)


def c5_numerico(ev, exp):
    # numerical_state = expulsiones del rival - del EQ acumuladas, incluido el evento de la tarjeta; periodo 5 nulo.
    validas = exp[exp["en_cancha"].to_numpy(dtype=bool)]
    signo = pd.Series(np.where(validas["team_id"] == EQ, -1, 1), index=pd.MultiIndex.from_frame(validas[LLAVE]))
    delta = pd.Series(pd.MultiIndex.from_frame(ev[LLAVE]).map(signo), index=ev.index).fillna(0).astype("int64")
    estado = delta.groupby(ev["match_id"]).cumsum().astype("Int64").mask(_penales(ev))
    cat = np.select([estado.fillna(0) < 0, estado.fillna(0) == 0], ESTADOS_NUMERICOS[:2], default=ESTADOS_NUMERICOS[2])
    return pd.DataFrame({
        "numerical_state": estado,
        "numerical_state_cat": _cat(cat, ESTADOS_NUMERICOS, ev.index, nulos=estado.isna()),
    }, index=ev.index)


def validar_c5(exp, c5, posiciones, tms, match_ids):
    # match_ids: match_id de cada evento, alineado con c5.
    fallas = []
    n, n_cancha = len(exp), int(exp["en_cancha"].sum())
    por_tarjeta = exp["tarjeta"].value_counts().to_dict()
    print(f"C5 eventos de expulsion: {n} ({por_tarjeta}); en cancha {n_cancha}; fuera de la cancha {n - n_cancha}")
    for r in exp[~exp["en_cancha"].to_numpy(dtype=bool)].itertuples(index=False):
        print(f"   fuera de la cancha: match_id {r.match_id}, index {r.index}, team_id {r.team_id}, "
              f"player_id {r.player_id}, periodo {r.period}, {r.match_second // 60}:{r.match_second % 60:02d}, {r.tarjeta}")
    # en cancha contra posiciones.end_reason (mismos jugadores, misma cantidad)
    llave_j = ["match_id", "team_id", "player_id"]
    er = posiciones[_texto(posiciones["end_reason"]).isin(END_REASON_EXPULSION).fillna(False).to_numpy(dtype=bool)]
    a = sorted(map(tuple, exp.loc[exp["en_cancha"].to_numpy(dtype=bool), llave_j].astype("int64").values.tolist()))
    b = sorted(map(tuple, er[llave_j].astype("int64").values.tolist()))
    if a == b:
        _ok(f"C5 las {n_cancha} expulsiones en cancha son los {len(b)} tramos de posiciones con end_reason "
            f"{sorted(END_REASON_EXPULSION)}")
    else:
        fallas.append(f"C5: expulsiones en cancha y posiciones.end_reason no coinciden: solo en eventos "
                      f"{sorted(set(a) - set(b))}, solo en posiciones {sorted(set(b) - set(a))}")
    # todas las expulsiones de eventos contra team_match_stats, por (partido, equipo)
    t = tms.set_index(["match_id", "team_id"])
    oficial = (t["team_match_red_cards"].fillna(0) + t["team_match_second_yellow_cards"].fillna(0)).astype("int64")
    con_tarjeta = exp.groupby(["match_id", "team_id"]).size()
    fuera = con_tarjeta.index.difference(oficial.index)
    if len(fuera):
        fallas.append(f"C5: pares (match_id, team_id) con expulsiones en eventos que no estan en team_match_stats: "
                      f"{[tuple(map(int, i)) for i in fuera]}")
    todas = con_tarjeta.reindex(oficial.index, fill_value=0)
    cancha = exp[exp["en_cancha"].to_numpy(dtype=bool)].groupby(["match_id", "team_id"]).size().reindex(
        oficial.index, fill_value=0)
    malos = oficial[oficial != todas]
    if malos.empty:
        _ok(f"C5 eventos de expulsion = team_match_red_cards + team_match_second_yellow_cards en las {len(oficial)} "
            f"filas (partido, equipo); total {int(oficial.sum())}")
    else:
        fallas.append(f"C5: eventos de expulsion distintos de team_match_stats en {malos.index.tolist()}")
    for (mid, tid), v in oficial[oficial != cancha].items():
        _aviso(f"C5 match_id {mid}, team_id {tid}: team_match_stats {v}, en cancha {cancha[(mid, tid)]} "
               "(la diferencia es una expulsion fuera de la cancha)")
    est = c5["numerical_state"]
    lo, hi = int(est.min()), int(est.max())
    if -2 <= lo and hi <= 2:
        _ok(f"C5 numerical_state entre {lo} y {hi}")
    else:
        fuera = sorted(match_ids[(est.abs() > 2).fillna(False).to_numpy(dtype=bool)].unique().tolist())
        _aviso(f"C5 numerical_state llega a [{lo}, {hi}], fuera de [-2, 2] en los partidos {fuera}; no se recorta")
    return fallas


# ---------------------------------------------------------------- E1 zonas

def e1_zonas(ev):
    # third, cell_6x5 (id = fila * 6 + columna) y zona14; nulos si no hay x.
    x, y = ev["x"].to_numpy(dtype="float64"), ev["y"].to_numpy(dtype="float64")
    sin = np.isnan(x) | np.isnan(y)
    tercio = np.select([x < 40, x < 80], TERCIOS[:2], default=TERCIOS[2])
    col = np.minimum(np.floor(np.nan_to_num(x) / 20), 5)
    fila = np.minimum(np.floor(np.nan_to_num(y) / 16), 4)
    celda = pd.array((fila * 6 + col).astype("int64"), dtype="Int64")
    celda[sin] = pd.NA
    z14 = pd.array((x >= ZONA14_X[0]) & (x < ZONA14_X[1]) & (y >= ZONA14_Y[0]) & (y <= ZONA14_Y[1]), dtype="boolean")
    z14[sin] = pd.NA
    return pd.DataFrame({
        "third": _cat(tercio, TERCIOS, ev.index, nulos=sin),
        "cell_6x5": celda,
        "zona14": z14,
    }, index=ev.index)


def validar_e1(ev, e1):
    fallas = []
    x, y = ev["x"], ev["y"]
    fuera_x, fuera_y = int(((x < 0) | (x > ANCHO)).sum()), int(((y < 0) | (y > ALTO)).sum())
    if fuera_x or fuera_y:
        fallas.append(f"E1: {fuera_x} x fuera de [0, {ANCHO:g}] y {fuera_y} y fuera de [0, {ALTO:g}]")
    else:
        _ok(f"E1 x en [{x.min():g}, {x.max():g}] y y en [{y.min():g}, {y.max():g}]; "
            f"{100 * x.isna().mean():.2f}% sin x (third, cell_6x5 y zona14 nulos)")
    ambos = (e1["third"].notna() & ev["location_bucket"].notna()).to_numpy(dtype=bool)
    igual = (e1["third"].astype("string") == _texto(ev["location_bucket"])).fillna(False).to_numpy(dtype=bool)
    abierto = ambos & ev["play_pattern_id"].isin(JUEGO_ABIERTO).fillna(False).to_numpy(dtype=bool)
    acuerdo = igual[abierto].mean()
    x_malos = ev.loc[abierto & ~igual, "x"]
    en_borde = x_malos.isin([40.0, 80.0]).mean() if len(x_malos) else 1.0
    detalle = (f"{100 * acuerdo:.2f}% de {int(abierto.sum()):,} eventos de juego abierto (play_pattern "
               f"{sorted(JUEGO_ABIERTO)}); {len(x_malos)} distintos, {100 * en_borde:.0f}% con x exactamente 40 u 80; "
               f"en todos los eventos {100 * igual[ambos].mean():.2f}%")
    if acuerdo < MIN_ACUERDO_TERCIO:
        fallas.append(f"E1: acuerdo de third con location_bucket por debajo de {100 * MIN_ACUERDO_TERCIO:g}%: {detalle}")
    else:
        _ok(f"E1 acuerdo de third con location_bucket: {detalle}")
    celdas = e1["cell_6x5"].dropna()
    print(f"E1 cell_6x5 de {int(celdas.min())} a {int(celdas.max())}, {celdas.nunique()} celdas usadas; "
          f"zona14 en {int(e1['zona14'].sum()):,} eventos")
    return fallas


# ---------------------------------------------------------------- E2 porteria

def e2_porteria(ev):
    # Distancia al centro de la porteria [120, 40] y angulo entre los postes, en grados; x/y sin espejar.
    dx, y = ANCHO - ev["x"].to_numpy(dtype="float64"), ev["y"].to_numpy(dtype="float64")
    return pd.DataFrame({
        "dist_goal": np.hypot(dx, ALTO / 2 - y),
        "angle_goal": np.degrees(np.abs(np.arctan2(POSTES[1] - y, dx) - np.arctan2(POSTES[0] - y, dx))),
    }, index=ev.index)


def validar_e2(ev, e2):
    fallas = []
    pen = (_texto(ev["shot_type_name"]) == "Penalty").fillna(False).to_numpy(dtype=bool)
    d = e2.loc[pen, "dist_goal"]
    eq = (ev.loc[pen, "team_id"] == EQ).to_numpy(dtype=bool)
    malos = (d - DIST_PENAL).abs().gt(1e-6) | d.isna()
    if pen.sum() == 0 or malos.any():
        fallas.append(f"E2: {int(malos.sum())} de {int(pen.sum())} penales no dan {DIST_PENAL:g} yardas")
    else:
        _ok(f"E2 los {int(pen.sum())} penales dan {DIST_PENAL:g} yardas ({int(eq.sum())} del EQ, "
            f"{int((~eq).sum())} del rival; incluye la tanda del periodo 5)")
    tiro = ((_texto(ev["type_name"]) == "Shot") & (ev["period"] < PERIODO_PENALES)).fillna(False).to_numpy(dtype=bool)
    tiro &= ~pen
    t = pd.DataFrame({"bin": pd.cut(e2.loc[tiro, "dist_goal"], BINS_DISTANCIA, right=False),
                      "xg": ev.loc[tiro, "shot_statsbomb_xg"]})
    xg = t.groupby("bin", observed=False)["xg"].agg(["size", "mean"])
    print("E2 xG medio por distancia (tiros sin penales, periodos 1 a 4): "
          + ", ".join(f"{iv.left:g}-{iv.right:g}: {r['mean']:.3f} (n={int(r['size'])})" for iv, r in xg.iterrows()))
    medias = xg["mean"].dropna()
    if medias.is_monotonic_decreasing:
        _ok("E2 el xG medio baja al aumentar la distancia")
    else:
        _aviso("E2 el xG medio no baja de forma monotona con la distancia")
    return fallas


# ---------------------------------------------------------------- B1 posesiones

def _sin_tanda(ev):
    return ev[(ev["period"] < PERIODO_PENALES).fillna(False).to_numpy(dtype=bool)]


def posesiones_base(ev):
    # Una fila por (match_id, possession) de los periodos 1 a 4: equipo, limites, duracion, play_pattern, inicio
    # en la cancha y conteos del equipo con la posesion. `ev` debe venir ordenado por (match_id, index).
    e = _sin_tanda(ev)
    admin = e["es_administrativo"].fillna(False).to_numpy(dtype=bool)
    propio = (e["team_id"] == e["possession_team_id"]).fillna(False).to_numpy(dtype=bool)
    tipo = _texto(e["type_name"])
    tiro = (tipo == "Shot").fillna(False).to_numpy(dtype=bool) & propio
    penal = (_texto(e["shot_type_name"]) == "Penalty").fillna(False).to_numpy(dtype=bool)
    aux = pd.DataFrame({
        "match_id": e["match_id"], "possession": e["possession"], "index": e["index"], "period": e["period"],
        "possession_team_id": e["possession_team_id"], "match_second": e["match_second"],
        "ts": pd.to_timedelta(e["timestamp"]).dt.total_seconds(),
        "pase": (tipo == "Pass").fillna(False).to_numpy(dtype=bool) & propio, "tiro": tiro, "admin": admin,
        "tiro_sin_penal": tiro & ~penal,
        "xg": np.where(tiro & ~penal, e["shot_statsbomb_xg"].fillna(0).to_numpy(dtype="float64"), 0.0),
    }, index=e.index)
    pos = aux.groupby(LLAVE_POSESION, sort=True).agg(
        possession_team_id=("possession_team_id", "first"), period=("period", "first"),
        period_fin=("period", "last"), index_inicio=("index", "first"), index_fin=("index", "last"),
        segundo_inicio=("match_second", "first"), ts0=("ts", "first"), ts1=("ts", "last"),
        n_eventos=("index", "size"), n_pases=("pase", "sum"), n_tiros=("tiro", "sum"), xg=("xg", "sum"),
        n_tiros_sin_penal=("tiro_sin_penal", "sum"),
        es_administrativa=("admin", "all"))
    pos["es_administrativa"] = pos["es_administrativa"].astype("boolean")
    # la duracion solo tiene sentido dentro de un periodo (las administrativas del medio tiempo cruzan)
    pos["duracion"] = (pos["ts1"] - pos["ts0"]).where(pos["period"] == pos["period_fin"])
    # play_pattern del primer evento no administrativo; si la posesion solo tiene administrativos, del primero
    patron = e[LLAVE_POSESION + ["play_pattern_id", "play_pattern_name"]].assign(
        play_pattern_name=_texto(e["play_pattern_name"]))
    patron = patron[~admin].groupby(LLAVE_POSESION).first().combine_first(patron.groupby(LLAVE_POSESION).first())
    pos = pos.join(patron)
    pos["es_balon_parado"] = pos["play_pattern_id"].isin(PATRONES_BALON_PARADO).astype("boolean")
    # inicio: primer evento propio con ubicacion, en la perspectiva del equipo con la posesion
    con_x = propio & e["x"].notna().to_numpy(dtype=bool)
    inicio = e.loc[con_x, LLAVE_POSESION + ["x", "y"]].groupby(LLAVE_POSESION).first()
    pos = pos.join(inicio.rename(columns={"x": "x_inicio", "y": "y_inicio"}))
    pos["third_inicio"] = e1_zonas(pos[["x_inicio", "y_inicio"]].set_axis(["x", "y"], axis=1))["third"]
    # limites de los eventos propios no administrativos, para la fusion
    activos = e.loc[propio & ~admin, LLAVE_POSESION + ["index"]].groupby(LLAVE_POSESION)["index"]
    pos = pos.join(activos.min().rename("primer_propio")).join(activos.max().rename("ultimo_propio"))
    return pos.reset_index()


def b1_fusion(ev, pos):
    # posesion_fundida_id: une p con la siguiente q del mismo equipo y periodo cuando los eventos no administrativos
    # del rival entre ellas (cola de p despues del ultimo evento propio y cabeza de q antes del primero) son al menos
    # uno y todos toques sin direccion, salvo que q empiece con una reanudacion (REANUDACIONES). Devuelve pos con
    # posesion_fundida_id, se_funde (q se une a la anterior), excluida_reanudacion (cumplia lo demas pero q es
    # reanudacion) y toques_rival (texto de esos eventos, para la muestra de control).
    e = _sin_tanda(ev)
    admin = e["es_administrativo"].fillna(False).to_numpy(dtype=bool)
    propio = (e["team_id"] == e["possession_team_id"]).fillna(False).to_numpy(dtype=bool)
    tipo = _texto(e["type_name"])
    toque = (tipo.isin(TOQUES_SIN_DIRECCION)
             | ((tipo == "Ball Recovery") & e["ball_recovery_recovery_failure"].fillna(False))).fillna(False)
    riv = pd.DataFrame({"match_id": e["match_id"], "possession": e["possession"], "index": e["index"],
                        "tipo": tipo, "toque": toque.to_numpy(dtype=bool)}, index=e.index)[~propio & ~admin]
    p = pos[LLAVE_POSESION + ["possession_team_id", "period", "primer_propio", "ultimo_propio",
                              "play_pattern_name"]].copy()
    p["siguiente"] = p.groupby("match_id")["possession"].shift(-1)
    riv = riv.merge(p[LLAVE_POSESION + ["primer_propio", "ultimo_propio", "siguiente"]], how="left", on=LLAVE_POSESION)
    cola = (riv["index"] > riv["ultimo_propio"]).fillna(False).to_numpy(dtype=bool)
    cabeza = (riv["index"] < riv["primer_propio"]).fillna(False).to_numpy(dtype=bool)
    # cada evento del hueco se asigna a la posesion posterior q del par (p, q)
    riv["q"] = np.where(cola, riv["siguiente"].astype("float64"), np.where(cabeza, riv["possession"].astype("float64"), np.nan))
    riv = riv[riv["q"].notna()]
    hueco = riv.groupby(["match_id", "q"]).agg(
        n_rival=("toque", "size"), todos_toque=("toque", "all"),
        toques_rival=("tipo", lambda s: "; ".join(f"{t} ({i})" for t, i in zip(s, riv.loc[s.index, "index"]))))
    hueco.index = hueco.index.set_levels(hueco.index.levels[1].astype("int64"), level=1)
    p = p.join(hueco, on=["match_id", "possession"])
    prev = p.groupby("match_id")[["possession_team_id", "period", "primer_propio"]].shift(1)
    candidata = ((p["possession_team_id"] == prev["possession_team_id"]) & (p["period"] == prev["period"])
                 & p["primer_propio"].notna() & prev["primer_propio"].notna()
                 & (p["n_rival"].fillna(0) >= 1) & p["todos_toque"].fillna(False).astype(bool)).fillna(False)
    reanuda = p["play_pattern_name"].isin(REANUDACIONES).fillna(False)
    se_funde = candidata & ~reanuda
    grupo = (~se_funde).cumsum()
    out = pos.copy()
    out["se_funde"] = se_funde.to_numpy(dtype=bool)
    out["excluida_reanudacion"] = (candidata & reanuda).to_numpy(dtype=bool)
    out["posesion_fundida_id"] = p["possession"].groupby(grupo).transform("first").astype("Int64").to_numpy()
    out["toques_rival"] = p["toques_rival"].where(candidata).to_numpy()
    return out


def b1_validez(pos):
    # is_valid_possession sobre la posesion fundida: pases y tiros sin penal sumando solo las filas que no son de
    # balon parado; las filas de balon parado quedan en False.
    parado = pos["es_balon_parado"].fillna(False).to_numpy(dtype=bool)
    abierto = pos[["match_id", "posesion_fundida_id"]].assign(
        pases=np.where(parado, 0, pos["n_pases"]), tiros=np.where(parado, 0, pos["n_tiros_sin_penal"]))
    g = abierto.groupby(["match_id", "posesion_fundida_id"])
    pases, tiros = g["pases"].transform("sum"), g["tiros"].transform("sum")
    return pd.Series(((pases >= MIN_PASES_VALIDA) | (tiros >= MIN_TIROS_VALIDA)).to_numpy(dtype=bool) & ~parado,
                     index=pos.index).astype("boolean")


def contexto_posesiones(ev, eventos_out):
    # Tabla por posesion: base + B1 + contexto de contexto_eventos en el primer evento de la posesion.
    pos = b1_fusion(ev, posesiones_base(ev))
    pos["is_valid_possession"] = b1_validez(pos)
    ctx = eventos_out[["match_id", "index", "score_state", "numerical_state", "minute_bin", "stage",
                       "rival_strength_tercil"]].rename(columns={"index": "index_inicio"})
    pos = pos.merge(ctx, how="left", on=["match_id", "index_inicio"], validate="one_to_one")
    pos["es_eq"] = (pos["possession_team_id"] == EQ).astype("boolean")
    return pos


COLS_POSESIONES = ["match_id", "possession", "possession_team_id", "es_eq", "period", "index_inicio", "index_fin",
                   "segundo_inicio", "duracion", "play_pattern_name", "x_inicio", "y_inicio", "third_inicio",
                   "n_eventos", "n_pases", "n_tiros", "xg", "score_state", "numerical_state", "minute_bin", "stage",
                   "rival_strength_tercil", "posesion_fundida_id", "is_valid_possession", "es_balon_parado",
                   "es_administrativa"]
COLS_MUESTRA = ["tipo", "match_id", "posesion_fundida_id", "posesiones", "possession_team_id", "es_eq", "period",
                "minuto_inicio", "index_inicio", "index_fin", "play_patterns", "toques_rival", "n_pases", "n_tiros",
                "is_valid_possession"]


def tabla_posesiones(pos):
    # Columnas aprobadas de contexto_posesiones, con sus tipos.
    out = pos[COLS_POSESIONES].copy()
    for c in ("match_id", "possession", "possession_team_id", "period", "index_inicio", "index_fin", "segundo_inicio",
              "n_eventos", "n_pases", "n_tiros", "posesion_fundida_id"):
        out[c] = out[c].astype("Int64")
    out["play_pattern_name"] = out["play_pattern_name"].astype("string")
    return out


def _fila_muestra(tipo, g):
    # Una fila del CSV de control a partir de las posesiones `g` (consecutivas) de un grupo o de un par.
    seg = int(g["segundo_inicio"].iloc[0])
    return {
            "tipo": tipo, "match_id": g["match_id"].iloc[0], "posesion_fundida_id": g["posesion_fundida_id"].iloc[0],
            "posesiones": ", ".join(map(str, g["possession"])),
            "possession_team_id": g["possession_team_id"].iloc[0], "es_eq": g["es_eq"].iloc[0],
            "period": g["period"].iloc[0], "minuto_inicio": f"{seg // 60}:{seg % 60:02d}",
            "index_inicio": g["index_inicio"].iloc[0], "index_fin": g["index_fin"].iloc[-1],
            "play_patterns": " | ".join(g["play_pattern_name"].astype(str)),
            "toques_rival": " | ".join(g["toques_rival"].dropna()),
            "n_pases": int(g["n_pases"].sum()), "n_tiros": int(g["n_tiros"].sum()),
            "is_valid_possession": " | ".join(g["is_valid_possession"].astype(str)),
    }


def muestra_fusion(pos):
    # CSV de control (semilla fija): hasta 10 posesiones fundidas (tipo fundida) y hasta 10 pares (p, q) que no se
    # fundieron porque q empieza con reanudacion (tipo descartada_reanudacion). Sin filas queda solo el encabezado.
    pos = pos.reset_index(drop=True)
    tam = pos.groupby(["match_id", "posesion_fundida_id"])["possession"].transform("size")
    fundidas = pos[tam > 1]
    llaves = fundidas[["match_id", "posesion_fundida_id"]].drop_duplicates()
    llaves = llaves.sample(min(N_MUESTRA_FUSION, len(llaves)), random_state=SEMILLA_MUESTRA)
    filas = [_fila_muestra("fundida", fundidas[(fundidas["match_id"] == mid) & (fundidas["posesion_fundida_id"] == fid)])
             for mid, fid in llaves.itertuples(index=False)]
    # q siempre tiene una posesion anterior en el mismo partido (si no, no seria candidata)
    qs = pos.index[pos["excluida_reanudacion"].to_numpy(dtype=bool)].to_series()
    qs = qs.sample(min(N_MUESTRA_FUSION, len(qs)), random_state=SEMILLA_MUESTRA)
    filas += [_fila_muestra("descartada_reanudacion", pos.loc[[q - 1, q]]) for q in qs]
    return pd.DataFrame(filas, columns=COLS_MUESTRA).sort_values(["tipo", "match_id", "posesion_fundida_id"]).reset_index(drop=True)


def validar_b1(ev, pos, tms):
    fallas = []
    g = pos.groupby(["match_id", "posesion_fundida_id"])
    n_grupos = g.ngroups
    mezcla = int(((g["possession_team_id"].nunique() > 1) | (g["period"].nunique() > 1)).sum())
    if mezcla:
        fallas.append(f"B1: {mezcla} posesiones fundidas mezclan equipos o periodos")
    adelante = int((pos["posesion_fundida_id"] > pos["possession"]).sum())
    if adelante:
        fallas.append(f"B1: {adelante} filas con posesion_fundida_id mayor que possession")
    unidas = int(pos["se_funde"].sum())
    if unidas != len(pos) - n_grupos:
        fallas.append(f"B1: {unidas} fusiones y {len(pos) - n_grupos} = filas - grupos; deben ser iguales")
    llaves_ev = pd.MultiIndex.from_frame(ev[LLAVE].astype("int64"))
    sin_evento = int((~pd.MultiIndex.from_frame(
        pos[["match_id", "index_inicio"]].astype("int64")).isin(llaves_ev)).sum())
    if sin_evento:
        fallas.append(f"B1: {sin_evento} index_inicio no existen en eventos")
    if not (mezcla or adelante or sin_evento or unidas != len(pos) - n_grupos):
        _ok(f"B1 {n_grupos:,} posesiones fundidas con un solo equipo y periodo, posesion_fundida_id <= possession, "
            f"fusiones = filas - grupos ({unidas}), todos los index_inicio existen en eventos")
    tanda = int(_penales(ev).sum())
    admin = int(pos["es_administrativa"].sum())
    print(f"B1 fuera de la tabla: {tanda} eventos del periodo 5; {admin} posesiones con es_administrativa (todos sus "
          f"eventos administrativos) se conservan; {int(pos['primer_propio'].isna().sum())} sin eventos propios no "
          "administrativos")
    # posesiones de StatsBomb con eventos propios, antes de fundir, contra team_match_possessions
    reales = pos[pos["primer_propio"].notna()].groupby(["match_id", "possession_team_id"]).size()
    oficial = tms.set_index(["match_id", "team_id"])["team_match_possessions"].astype("float64")
    razon = (reales.rename_axis(["match_id", "team_id"]).reindex(oficial.index) / oficial).dropna()
    extremo = lambda i: f"(match_id {int(i[0])}, team_id {int(i[1])})"
    print(f"B1 posesiones antes de fundir / team_match_possessions por (partido, equipo), n={len(razon)}: media "
          f"{razon.mean():.3f}, min {razon.min():.3f} {extremo(razon.idxmin())}, max {razon.max():.3f} "
          f"{extremo(razon.idxmax())}")
    # team_match_possessions casi no cambia entre los dos equipos del partido: se compara tambien con el total
    por_partido = oficial.groupby(level=0).agg(["min", "max"])
    total = pos[pos["primer_propio"].notna()].groupby("match_id").size().reindex(por_partido.index)
    fundidas = (pos[pos["primer_propio"].notna()].groupby("match_id")["posesion_fundida_id"].nunique()
                .reindex(por_partido.index))
    print(f"B1 team_match_possessions difiere entre los dos equipos en a lo sumo "
          f"{int((por_partido['max'] - por_partido['min']).max())}; posesiones del partido (los dos equipos) / "
          f"team_match_possessions del EQ: antes de fundir media {(total / oficial.xs(EQ, level=1)).mean():.3f}, "
          f"fundidas media {(fundidas / oficial.xs(EQ, level=1)).mean():.3f}")
    patron_q = pos.loc[pos["se_funde"], "play_pattern_name"].value_counts().to_dict()
    excluidas = pos.loc[pos["excluida_reanudacion"], "play_pattern_name"].value_counts().to_dict()
    print(f"B1 fusion: {unidas} posesiones se unen a la anterior; {len(pos):,} posesiones quedan en {n_grupos:,} "
          f"fundidas. play_pattern de la posesion que se une: {patron_q or 'ninguna'}. Pares con toque sin "
          f"direccion del rival que no se funden porque q empieza con reanudacion: "
          f"{int(pos['excluida_reanudacion'].sum())} {excluidas}")
    parado = pos["es_balon_parado"].fillna(False).to_numpy(dtype=bool)
    sin_fundir = ((pos["n_pases"] >= MIN_PASES_VALIDA)
                  | (pos["n_tiros_sin_penal"] >= MIN_TIROS_VALIDA)).to_numpy(dtype=bool) & ~parado
    con_penal = ((pos["n_pases"] >= MIN_PASES_VALIDA) | (pos["n_tiros"] >= MIN_TIROS_VALIDA)).to_numpy(dtype=bool) & ~parado
    validas = pos["is_valid_possession"].to_numpy(dtype=bool)
    eq = pos["es_eq"].to_numpy(dtype=bool)
    print(f"B1 validas: {int(validas.sum()):,} de {len(pos):,} ({int((validas & eq).sum()):,} del EQ); "
          f"{int(parado.sum()):,} de balon parado quedan en False; la fusion vuelve validas {int((validas & ~sin_fundir).sum())} "
          f"filas de juego abierto que solas no lo serian; {int((con_penal & ~sin_fundir).sum())} dejarian de serlo "
          "si el penal contara como tiro")
    return fallas


# ---------------------------------------------------------------- tabla por partido

def contexto_partidos(ev, partidos, c2, c3, c4, exp, autogol):
    # Una fila por partido: contexto (C3, C4), goles (C2), expulsiones en cancha (C5) y minutos por marcador.
    base = c3.merge(partidos[["match_id", "es_final", "rival_nombre"]].assign(
        rival_nombre=_texto(partidos["rival_nombre"]), es_final=partidos["es_final"].astype("boolean")),
        how="left", on="match_id", validate="one_to_one")
    base = base.merge(c4[["team_id", "torneo", "rival_strength", "rival_strength_tercil", "rival_ppg"]].rename(
        columns={"team_id": "rival_id"}), how="left", on=["rival_id", "torneo"], validate="many_to_one")
    g_eq, g_r = _goles(ev, autogol)
    goles = pd.DataFrame({"goles_eq": g_eq, "goles_rival": g_r}).groupby(ev["match_id"].to_numpy()).sum()
    validas = exp[exp["en_cancha"].to_numpy(dtype=bool)]
    lado = np.where(validas["team_id"] == EQ, "expulsiones_eq", "expulsiones_rival")
    expuls = validas.groupby([validas["match_id"].to_numpy(), lado]).size().unstack()
    # minutos: cada evento aporta el tiempo hasta el siguiente de su (match_id, period), con el marcador posterior
    e = pd.DataFrame({"match_id": ev["match_id"], "period": ev["period"], "s": ev["match_second"],
                      "estado": c2["score_state"]})[(ev["period"] < PERIODO_PENALES).fillna(False).to_numpy(dtype=bool)]
    sig = e.groupby(["match_id", "period"])[["s", "estado"]].shift(-1)
    tramo = pd.DataFrame({"match_id": e["match_id"], "estado": sig["estado"], "min": (sig["s"] - e["s"]) / 60}).dropna()
    minutos = tramo.groupby(["match_id", "estado"], observed=False)["min"].sum().unstack().reindex(
        columns=ESTADOS_MARCADOR).fillna(0.0)
    minutos.columns = [f"minutos_{c}" for c in minutos.columns]
    out = base.join(goles, on="match_id").join(expuls, on="match_id").join(minutos, on="match_id")
    for c in ("goles_eq", "goles_rival", "expulsiones_eq", "expulsiones_rival"):
        out[c] = out[c].fillna(0).astype("Int64") if c in out else pd.array([0] * len(out), dtype="Int64")
    for c in minutos.columns:
        out[c] = out[c].astype("float64")
    return out[["match_id", "torneo", "match_week", "stage", "es_final", "is_home", "rival_id", "rival_nombre",
                "rival_strength", "rival_strength_tercil", "rival_ppg", "goles_eq", "goles_rival", "expulsiones_eq",
                "expulsiones_rival", "minutos_ganando", "minutos_empatando", "minutos_perdiendo"]]


def validar_partidos(ev, partidos, cp, posiciones):
    fallas = []
    if len(cp) != ESPERADO["partidos"] or cp["match_id"].duplicated().any():
        fallas.append(f"partidos: {len(cp)} filas o match_id duplicado; se esperaban {ESPERADO['partidos']} unicas")
    p = partidos.set_index("match_id")
    c = cp.set_index("match_id")
    malos = c.index[(c["goles_eq"] != p["goles_favor"].reindex(c.index))
                    | (c["goles_rival"] != p["goles_contra"].reindex(c.index))].tolist()
    if malos:
        fallas.append(f"partidos: goles_eq/goles_rival no cuadran con goles_favor/goles_contra en {malos}")
    else:
        _ok(f"partidos: goles_eq y goles_rival = goles_favor y goles_contra en los {len(c)} partidos "
            f"({int(c['goles_eq'].sum())} a favor, {int(c['goles_rival'].sum())} en contra)")
    er = posiciones[_texto(posiciones["end_reason"]).isin(END_REASON_EXPULSION).fillna(False).to_numpy(dtype=bool)]
    er_eq = er[er["team_id"] == EQ].groupby("match_id").size().reindex(c.index, fill_value=0)
    er_r = er[er["team_id"] != EQ].groupby("match_id").size().reindex(c.index, fill_value=0)
    malos = c.index[(c["expulsiones_eq"] != er_eq) | (c["expulsiones_rival"] != er_r)].tolist()
    if malos:
        fallas.append(f"partidos: expulsiones no cuadran con posiciones.end_reason en {malos}")
    else:
        _ok(f"partidos: expulsiones_eq {int(c['expulsiones_eq'].sum())} y expulsiones_rival "
            f"{int(c['expulsiones_rival'].sum())} = tramos de posiciones con end_reason de tarjeta")
    # suma de minutos contra la duracion por timestamp (maximo por periodo, sumado)
    e = _sin_tanda(ev)
    dur = (pd.to_timedelta(e["timestamp"]).dt.total_seconds().groupby([e["match_id"], e["period"]]).max()
           .groupby(level=0).sum() / 60).reindex(c.index)
    suma = c[["minutos_ganando", "minutos_empatando", "minutos_perdiendo"]].sum(axis=1)
    dif = suma - dur
    print(f"partidos: minutos ganando/empatando/perdiendo del EQ {c['minutos_ganando'].sum():.0f} / "
          f"{c['minutos_empatando'].sum():.0f} / {c['minutos_perdiendo'].sum():.0f}; suma por partido de "
          f"{suma.min():.1f} a {suma.max():.1f} (media {suma.mean():.1f}); diferencia con la duracion por timestamp "
          f"de {dif.min():+.2f} a {dif.max():+.2f} min")
    lejos = dif[dif.abs() > 1]
    if lejos.empty:
        _ok("partidos: la suma de minutos queda a menos de 1 min de la duracion por timestamp en todos")
    else:
        _aviso(f"partidos: la suma de minutos se aleja mas de 1 min de la duracion en {lejos.round(2).to_dict()}")
    return fallas


def validar_match_ids(partidos, salidas):
    # Cada salida por partido o evento debe traer exactamente los match_id de partidos.
    fallas = []
    esperados = set(partidos["match_id"].astype("int64"))
    for nombre, df in salidas.items():
        vistos = set(df["match_id"].dropna().astype("int64"))
        sobran, faltan = sorted(vistos - esperados), sorted(esperados - vistos)
        if sobran or faltan or df["match_id"].isna().any():
            fallas.append(f"{nombre}: match_id fuera de partidos {sobran}, faltantes {faltan}")
        else:
            _ok(f"{nombre}: exactamente los {len(esperados)} match_id de partidos")
    return fallas


# ---------------------------------------------------------------- armado y escritura

def armar_eventos(ev, frames, c3, c4):
    # Llave + columnas de cada ficha por evento; C3 y C4 se copian del partido al evento.
    out = pd.concat([ev[LLAVE], *frames], axis=1)
    partido = c3.merge(c4[["team_id", "torneo", "rival_strength", "rival_strength_tercil", "rival_ppg"]].rename(
        columns={"team_id": "rival_id"}), how="left", on=["rival_id", "torneo"], validate="many_to_one")
    partido = partido.drop(columns="torneo")
    out = out.merge(partido, how="left", on="match_id", validate="many_to_one")
    orden = LLAVE + ["match_clock", "minute_bin", "goal_diff", "goal_diff_clip", "score_state", "is_home", "rival_id",
                     "stage", "match_week", "rival_strength", "rival_strength_tercil", "rival_ppg", "numerical_state",
                     "numerical_state_cat", "third", "cell_6x5", "zona14", "dist_goal", "angle_goal"]
    return out[orden]


def validar_salida(ev, eventos_out, posesiones_out, c4):
    fallas = []
    if len(eventos_out) != len(ev) or eventos_out.duplicated(LLAVE).any():
        fallas.append(f"salida: {len(eventos_out)} filas para {len(ev)} eventos o llaves duplicadas")
    if posesiones_out.duplicated(LLAVE_POSESION).any():
        fallas.append("salida: contexto_posesiones tiene llaves (match_id, possession) duplicadas")
    if not fallas:
        _ok(f"salida: {len(eventos_out):,} eventos con llave unica, {len(eventos_out.columns)} columnas; "
            f"{len(posesiones_out):,} posesiones con llave unica; rival_strength {len(c4)} filas (equipo, torneo)")
    return fallas


def _bloqueados(archivos):
    # Destinos que ya existen y no se pueden abrir para escribir (en Windows, abiertos en Excel o en otro proceso).
    # Es heuristico, como en 02_limpieza.py: no detecta procesos que solo impiden borrar.
    malos = []
    for archivo in archivos:
        destino = PROCESSED / archivo
        if destino.exists():
            try:
                with open(destino, "r+b"):
                    pass
            except OSError as e:
                malos.append(f"{archivo} ({e.strerror or e})")
    return malos


def _borrar(ruta):
    # Borra una carpeta o archivo temporal; avisa si no se pudo.
    if ruta.is_dir():
        shutil.rmtree(ruta, ignore_errors=True)
    else:
        ruta.unlink(missing_ok=True)
    if ruta.exists():
        print(f"AVISO: no se pudo borrar el temporal {ruta}", file=sys.stderr)


def escribir(tablas):
    # Escribe todo en una carpeta temporal dentro de data/processed/ y despues reemplaza archivo por archivo (mismo
    # esquema que 02_limpieza.py). La temporal solo se borra si no se reemplazo nada o si se reemplazo todo.
    archivos = list(tablas)
    try:
        PROCESSED.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=".tmp_contexto_", dir=PROCESSED))
    except OSError as e:
        raise ErrorContexto(f"no se pudo preparar {PROCESSED}: {e}") from e
    reemplazados = []
    try:
        try:
            for nombre, df in tablas.items():
                if nombre.endswith(".csv"):
                    df.to_csv(tmp / nombre, index=False)
                else:
                    df.to_parquet(tmp / nombre, compression="zstd", index=False)
        except ERRORES_ESCRITURA as e:
            raise ErrorContexto(f"no se pudo escribir en la carpeta temporal {tmp}; no se reemplazo nada: "
                                f"{type(e).__name__}: {e}") from e
        bloqueados = _bloqueados(archivos)
        if bloqueados:
            raise ErrorContexto(f"no se reemplazo nada en {PROCESSED}: estos destinos estan bloqueados o no se pueden "
                                f"escribir: {bloqueados}. Cierralos (por ejemplo en Excel) y vuelve a correr.")
        for archivo in archivos:
            try:
                os.replace(tmp / archivo, PROCESSED / archivo)
            except OSError as e:
                if not reemplazados:
                    raise ErrorContexto(f"no se reemplazo nada en {PROCESSED}: fallo {archivo} ({e})") from e
                raise ErrorContexto(
                    f"el reemplazo quedo a medias en {PROCESSED}: ya se reemplazaron {reemplazados}; faltan "
                    f"{archivos[len(reemplazados):]} ({e}). Los que faltan siguen en la carpeta temporal {tmp}, que no "
                    "se borro: copialos a mano o vuelve a correr.") from e
            except KeyboardInterrupt:
                if reemplazados:
                    print(f"AVISO: interrumpido a medias; ya se reemplazaron {reemplazados} y el resto sigue en la "
                          f"carpeta temporal {tmp}, que no se borro.", file=sys.stderr)
                raise
            reemplazados.append(archivo)
    finally:
        if not 0 < len(reemplazados) < len(archivos):
            _borrar(tmp)
    # restos de corridas anteriores: carpetas temporales y los .tmp sueltos del esquema viejo
    viejos = [v for v in PROCESSED.glob(".tmp_contexto_*") if v != tmp]
    viejos += [PROCESSED / f".{a}.tmp" for a in archivos if (PROCESSED / f".{a}.tmp").exists()]
    for viejo in viejos:
        _borrar(viejo)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-escribir", action="store_true", help="calcula y valida sin escribir en data/processed/")
    args = p.parse_args()
    inicio = time.perf_counter()

    try:
        ev = leer("eventos", COLS_EVENTOS).sort_values(LLAVE).reset_index(drop=True)
        partidos = leer("partidos").sort_values("match_id").reset_index(drop=True)
        posiciones = leer("posiciones")
        tms = leer("team_match_stats", ["match_id", "team_id", "team_match_red_cards", "team_match_second_yellow_cards",
                                        "team_match_possessions"])
        liga = leer("team_match_stats_liga", COLS_LIGA)
    except ErrorContexto as e:
        print(f"ERROR: {e}\nNo se escribio nada.", file=sys.stderr)
        return 1
    print(f"lee {len(ev):,} eventos de {ev['match_id'].nunique()} partidos")

    fallas = []
    c1 = c1_reloj(ev)
    fallas += validar_c1(ev, c1)
    autogol, f = elegir_autogol(ev, partidos)
    fallas += f
    c2 = c2_marcador(ev, autogol or "directo")
    c3 = c3_partido(partidos)
    fallas += validar_c3(partidos, c3, liga)
    c4 = c4_rival_strength(liga)
    fallas += validar_c4(liga, c3, c4)
    exp = expulsiones(ev, posiciones)
    c5 = c5_numerico(ev, exp)
    fallas += validar_c5(exp, c5, posiciones, tms, ev["match_id"])
    e1 = e1_zonas(ev)
    fallas += validar_e1(ev, e1)
    e2 = e2_porteria(ev)
    fallas += validar_e2(ev, e2)
    eventos_out = armar_eventos(ev, [c1, c2, c5, e1, e2], c3, c4)
    pos = contexto_posesiones(ev, eventos_out)
    fallas += validar_b1(ev, pos, tms)
    posesiones_out = tabla_posesiones(pos)
    fallas += validar_salida(ev, eventos_out, posesiones_out, c4)
    muestra = muestra_fusion(pos)
    partidos_out = contexto_partidos(ev, partidos, c2, c3, c4, exp, autogol or "directo")
    fallas += validar_partidos(ev, partidos, partidos_out, posiciones)
    fallas += validar_match_ids(partidos, {SALIDA_EVENTOS: eventos_out, SALIDA_POSESIONES: posesiones_out,
                                           SALIDA_PARTIDOS: partidos_out})

    if fallas:
        print(f"ERROR: {len(fallas)} validaciones duras fallaron:", file=sys.stderr)
        for x in fallas:
            print(f"   {x}", file=sys.stderr)
        print("No se escribio nada.", file=sys.stderr)
        return 1
    print(f"control: {len(muestra)} filas en la muestra de {CONTROL_FUSION} "
          f"({muestra['tipo'].value_counts().to_dict()})")
    if args.sin_escribir:
        print(f"Sin escribir (--sin-escribir). {time.perf_counter() - inicio:.1f} s")
        return 0
    try:
        escribir({SALIDA_EVENTOS: eventos_out, SALIDA_RIVALES: c4, SALIDA_POSESIONES: posesiones_out,
                  SALIDA_PARTIDOS: partidos_out, CONTROL_FUSION: muestra})
    except ErrorContexto as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"Escrito en {PROCESSED.relative_to(ROOT).as_posix()}/: {SALIDA_EVENTOS}, {SALIDA_RIVALES}, "
          f"{SALIDA_POSESIONES}, {SALIDA_PARTIDOS}, {CONTROL_FUSION}. "
          f"{time.perf_counter() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
