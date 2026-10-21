"""Tabla analitica (fase 3, ensamblado final): junta el contexto y las metricas de Lee, Pablo y Pato.

Uso:
    python scripts/03_tabla_analitica.py                 # junta, valida y escribe en data/processed/
    python scripts/03_tabla_analitica.py --sin-escribir  # junta y valida, sin escribir

Va despues de 03_contexto.py, 03_ataque.py, 03_defensa.py y 03_jugadores.py, y antes de 04_contexto.py. No
recalcula ninguna metrica: cuenta, suma, pivota y pega. Escribe dos tablas (ver SALIDA_*):
- analitica_posesiones.parquet: una fila por posesion de contexto_posesiones, llave (match_id, possession), con
  ataque_posesiones, ataque_eventos sumados por posesion (eventos del equipo con el balon) y balon_parado_posesiones.
- analitica_partidos.parquet: una fila por partido de contexto_partidos, llave match_id, con defensa_partidos,
  balon_parado_partidos pivotado, totales de Lee por equipo (todo lo que hizo cada equipo) y formacion, cambios y
  once de Pato.

El contexto sale siempre de la fase 3: el que repiten Pablo y Pato se valida y no se copia. Lo que Lee solo calcula
para el America queda nulo en el rival. Las reglas, los insumos y los criterios de aceptacion estan en
docs/spec_03_tabla_analitica.md.

Codigos de salida: 0 si todo paso y se escribio (o no se pidio escribir); 1 si falta un insumo, fallo una
validacion dura o fallo la escritura. Si falla una validacion no se escribe nada.
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
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
# nombres de las salidas: aprobados por el usuario el 20-oct; ver docs/spec_03_tabla_analitica.md
SALIDA_POSESIONES = "analitica_posesiones.parquet"
SALIDA_PARTIDOS = "analitica_partidos.parquet"
PREFIJO_TMP = ".tmp_tabla_analitica_"

EQ = 1229  # America con Jardine
LLAVE_POSESION = ["match_id", "possession"]
LLAVE_EVENTO = ["match_id", "index"]
PERIODOS_JUEGO = {1, 2, 3, 4}  # el 5 es la tanda de penales

# Pablo, por partido: contexto repetido (se valida y no se copia) y lo que se conserva (match_date, resultado, 48)
CONTEXTO_DEFENSA = ["torneo", "es_final", "rival_id", "rival_nombre", "is_home", "stage", "rival_strength_tercil"]
QUITAR_DEFENSA = CONTEXTO_DEFENSA + ["fase", "es_local"]
METRICAS_DEFENSA = [
    "presiones", "presiones_altas", "presiones_altas_40m", "presiones_mitad_rival", "press_height", "ppda_pases_rival",
    "ppda_pases_rival_ja", "ppda_acciones", "acciones_linea", "defensive_line_height", "acciones_linea_defensas",
    "defensive_line_height_defensas", "pct_presiones_altas", "pct_presiones_altas_40m", "ppda", "ppda_juego_abierto",
    "defensive_line_height_100", "presiones_regain", "contrapresiones_regain", "contrapresiones", "perdidas",
    "perdidas_regain_5s", "perdidas_con_contrapresion", "perdidas_cp_regain_5s", "fases_presion",
    "fases_presion_recupera", "fases_presion_duracion_media", "fases_presion_x_media", "fases_solo_pressure",
    "transiciones_def", "transiciones_def_con_cp", "tiros_rival_trans_def", "xg_rival_trans_def", "transiciones_of",
    "tiros_eq_trans_of", "xg_eq_trans_of", "obv_eq_trans_of", "tasa_regain_5s", "tasa_regain_5s_cp", "presiones_sb",
    "presiones_mitad_rival_sb", "contrapresiones_sb", "presiones_regain_sb", "contrapresiones_regain_sb", "ppda_sb",
    "defensive_distance_sb", "xg_rival_transicion_sb", "time_in_transition_sb"]
COLS_DEFENSA = ["match_date", "resultado"] + METRICAS_DEFENSA

# insumo: (ruta, columnas que se usan, script que lo produce, autor); None = todas
INSUMOS = {
    "contexto_posesiones": ("data/processed/contexto_posesiones.parquet", None, "03_contexto.py", "Yordi"),
    "contexto_partidos": ("data/processed/contexto_partidos.parquet", None, "03_contexto.py", "Yordi"),
    "eventos": ("data/interim/eventos.parquet", ["match_id", "index", "team_id", "possession", "period", "type_name"],
                "02_limpieza.py", "Yordi"),
    "ataque_posesiones": ("data/processed/ataque_posesiones.parquet",
                          ["match_id", "possession", "possession_start_type", "build_up_chain", "xg_chain",
                           "xg_buildup"], "03_ataque.py", "Lee"),
    "ataque_eventos": ("data/processed/ataque_eventos.parquet",
                       ["match_id", "index", "progressive_pass", "carry_progress", "deep_progression",
                        "deep_completion", "line_breaking_pass", "ball_receipt_in_space", "xa", "obv_net"],
                       "03_ataque.py", "Lee"),
    "balon_parado_posesiones": ("data/processed/balon_parado_posesiones.parquet",
                                ["match_id", "possession", "period", "team_id", "lado", "set_piece_type",
                                 "con_saque", "es_directo", "x_saque", "y_saque", "tiros", "xg", "goles",
                                 "set_piece_phase_max", "score_state", "numerical_state_cat", "minute_bin",
                                 "rival_strength_tercil", "stage"], "03_defensa.py", "Pablo"),
    "defensa_partidos": ("data/processed/defensa_partidos.parquet", ["match_id"] + QUITAR_DEFENSA + COLS_DEFENSA,
                         "03_defensa.py", "Pablo"),
    "balon_parado_partidos": ("data/processed/balon_parado_partidos.parquet",
                              ["match_id", "lado", "set_piece_type", "team_id", "saques", "tiros", "xg", "goles",
                               "torneo", "fase", "es_final"], "03_defensa.py", "Pablo"),
    "formacion_por_periodo": ("data/processed/jugadores/formacion_por_periodo.parquet",
                              ["match_id", "period", "formacion"], "03_jugadores.py", "Pato"),
    "momentos_de_cambio": ("data/processed/jugadores/momentos_de_cambio.parquet",
                           ["match_id", "idx_evento", "minute", "n_cambios", "es_local", "fase", "torneo"],
                           "03_jugadores.py", "Pato"),
    "onces_iniciales": ("data/processed/jugadores/onces_iniciales.parquet",
                        ["match_id", "match_date", "fase", "torneo", "cambios_vs_previo"], "03_jugadores.py", "Pato"),
}
LLAVES = {
    "contexto_posesiones": LLAVE_POSESION, "contexto_partidos": ["match_id"], "eventos": LLAVE_EVENTO,
    "ataque_posesiones": LLAVE_POSESION, "ataque_eventos": LLAVE_EVENTO, "balon_parado_posesiones": LLAVE_POSESION,
    "defensa_partidos": ["match_id"], "balon_parado_partidos": ["match_id", "lado", "set_piece_type"],
    "formacion_por_periodo": ["match_id", "period"], "momentos_de_cambio": ["match_id", "idx_evento"],
    "onces_iniciales": ["match_id"],
}
# insumos por partido que deben traer exactamente los partidos del contexto (momentos_de_cambio puede traer menos)
POR_PARTIDO_COMPLETOS = ["defensa_partidos", "balon_parado_partidos", "formacion_por_periodo", "onces_iniciales"]

# Lee, por evento: bandera -> conteo por posesion
CONTEOS_POSESION = {"progressive_pass": "n_pases_progresivos", "carry_progress": "n_conducciones_progresivas",
                    "deep_progression": "n_deep_progressions", "deep_completion": "n_deep_completions",
                    "line_breaking_pass": "n_pases_rompe_lineas", "ball_receipt_in_space": "n_recepciones_espacio"}
SOLO_EQ_EVENTO = ["progressive_pass", "carry_progress", "deep_progression", "deep_completion"]
# banderas del 360: nulas si el evento no tiene frame; True solo en su tipo de evento
APLICA_360 = {"line_breaking_pass": "Pass", "ball_receipt_in_space": "Ball Receipt*"}
SUMAS_POSESION = {"xa": "xa", "obv_net": "obv_neto"}
# Lee, por posesion: solo existen para el America
SOLO_EQ_POSESION = ["build_up_chain", "xg_chain", "xg_buildup"]
CADENAS = ["xg_chain", "xg_buildup"]
# posesiones del rival con xg_chain > 0 ya conocidas: se anulan y se avisan a Lee en vez de fallar
EXCEPCIONES_CADENA_RIVAL = {(3889699, 25)}  # 0.007 en una posesion del rival sin xG (20-oct)
# Lee, por partido
CONTEOS_PARTIDO_EQ = {"progressive_pass": "pases_progresivos_eq", "carry_progress": "conducciones_progresivas_eq",
                      "deep_progression": "deep_progressions_eq", "deep_completion": "deep_completions_eq"}
CONTEOS_PARTIDO_AMBOS = {"line_breaking_pass": "pases_rompe_lineas", "ball_receipt_in_space": "recepciones_espacio"}
SUMAS_PARTIDO_AMBOS = {"xa": "xa", "obv_net": "obv_neto"}
COLS_LEE_PARTIDO = list(CONTEOS_PARTIDO_EQ.values()) + ["cadenas_construccion_eq"] + [
    f"{n}_{s}" for n in list(CONTEOS_PARTIDO_AMBOS.values()) + list(SUMAS_PARTIDO_AMBOS.values())
    for s in ("eq", "rival")] + ["xg_chain_eq"]

# Pablo, balon parado por posesion
COLS_BP_POSESION = ["set_piece_type", "con_saque", "es_directo", "x_saque", "y_saque", "set_piece_phase_max"]
RENOMBRE_BP = {"tiros": "tiros_bp", "xg": "xg_bp", "goles": "goles_bp"}
CONTEXTO_BP_POSESION = ["period", "score_state", "minute_bin", "rival_strength_tercil", "stage"]
LADO_EQ = {"a_favor": True, "en_contra": False}

# Pablo, balon parado por partido
FASE_A_STAGE = {"regular": "regular", "liguilla": "fase final"}
MEDIDAS_BP = ["saques", "tiros", "xg", "goles"]
TIPOS_BP = {"Corner": "corner", "Free Kick": "tiro_libre", "Throw In": "banda", "Juego abierto": "juego_abierto"}
LADOS_BP = {"a_favor": "favor", "en_contra": "contra"}
SIN_SAQUE = ["saques_juego_abierto_favor", "saques_juego_abierto_contra"]  # en juego abierto no hay saque
COLS_PIVOTE = [f"{m}_{t}_{lado}" for m in MEDIDAS_BP for t in TIPOS_BP.values() for lado in LADOS_BP.values()
               if f"{m}_{t}_{lado}" not in SIN_SAQUE]

# Pato
COLS_PATO = ["formacion_1t", "formacion_2t", "cambia_formacion", "n_cambios", "n_momentos_cambio",
             "minuto_primer_cambio", "cambios_vs_previo"]
ENTEROS_PATO = {"formacion_por_periodo": "formacion", "momentos_de_cambio": "minute"}

TIPOS_SALIDA = {"Int64", "float64", "boolean", "string", "category"}  # mas datetime64[...]
TOL = 1e-9
ERRORES_ESCRITURA = (OSError, ValueError, TypeError, pa.lib.ArrowException)


class ErrorAnalitica(Exception):
    pass


def _ok(msg):
    print(f"[OK] {msg}")


def _aviso(msg):
    print(f"AVISO: {msg}")


def _origen(nombre):
    ruta, _, script, autor = INSUMOS[nombre]
    return f"{ruta} (lo produce {script}, de {autor})"


def _mascara(serie):
    # Serie boolean con nulos a arreglo numpy, con los nulos en False.
    return serie.astype("boolean").fillna(False).to_numpy(dtype=bool)


def leer(nombre):
    # Lee un insumo con solo sus columnas; si falta el archivo o una columna, dice que script lo produce.
    ruta, columnas, _, _ = INSUMOS[nombre]
    archivo = ROOT / ruta
    if not archivo.exists():
        raise ErrorAnalitica(f"no existe {_origen(nombre)}; corre ese script antes")
    try:
        disponibles = set(pq.read_schema(archivo).names)
        faltan = [c for c in columnas or [] if c not in disponibles]
        if faltan:
            raise ErrorAnalitica(f"a {_origen(nombre)} le faltan las columnas {faltan}")
        return pd.read_parquet(archivo, columns=columnas)
    except (OSError, ValueError, KeyError, pa.lib.ArrowException) as e:
        raise ErrorAnalitica(f"no se pudo leer {_origen(nombre)}: {type(e).__name__}: {e}") from e


# ---------------------------------------------------------------- validaciones de insumos

def validar_llaves(tablas):
    fallas = []
    for nombre, llave in LLAVES.items():
        df = tablas[nombre]
        repetidas = int(df.duplicated(llave).sum())
        nulas = int(df[llave].isna().any(axis=1).sum())
        if repetidas or nulas:
            fallas.append(f"{nombre}: {repetidas} filas con la llave {llave} repetida y {nulas} con la llave nula")
    if not fallas:
        _ok(f"llave unica y sin nulos en los {len(LLAVES)} insumos")
    return fallas


def _huerfanos(nombre, df, base, llave, nombre_base):
    # Filas de df cuya llave completa no esta en base.
    m = df[llave].drop_duplicates().merge(base[llave].drop_duplicates(), on=llave, how="left", indicator=True)
    sueltas = m[m["_merge"] == "left_only"]
    if sueltas.empty:
        return []
    return [f"{nombre}: {len(sueltas)} llaves {llave} que no estan en {nombre_base}, por ejemplo "
            f"{sueltas[llave].head(3).to_dict('records')}"]


def validar_partidos(tablas):
    # Los insumos por partido traen los partidos del contexto; balon_parado_partidos, la reticula completa.
    fallas = []
    base = tablas["contexto_partidos"]
    esperados = set(base["match_id"].astype("int64"))
    for nombre in POR_PARTIDO_COMPLETOS + ["momentos_de_cambio"]:
        vistos = set(tablas[nombre]["match_id"].astype("int64"))
        fallas += _huerfanos(nombre, tablas[nombre].astype({"match_id": "Int64"}), base, ["match_id"],
                             "contexto_partidos")
        if nombre in POR_PARTIDO_COMPLETOS and vistos != esperados:
            fallas.append(f"{nombre}: trae {len(vistos)} partidos y faltan {sorted(esperados - vistos)[:5]}")
    bpp = tablas["balon_parado_partidos"]
    desconocidos = sorted(set(bpp["lado"].astype("string")) - set(LADOS_BP)) + \
        sorted(set(bpp["set_piece_type"].astype("string")) - set(TIPOS_BP))
    if desconocidos:
        fallas.append(f"balon_parado_partidos: lado o set_piece_type desconocidos {desconocidos}")
    incompletos = bpp.groupby("match_id").size()
    incompletos = incompletos[incompletos != len(LADOS_BP) * len(TIPOS_BP)]
    if not incompletos.empty:
        fallas.append(f"balon_parado_partidos: {len(incompletos)} partidos sin las {len(LADOS_BP) * len(TIPOS_BP)} "
                      "combinaciones de lado y tipo")
    fallas += validar_pato(tablas, esperados)
    if not fallas:
        _ok(f"insumos por partido: los {len(esperados)} partidos del contexto en {', '.join(POR_PARTIDO_COMPLETOS)}; "
            f"momentos_de_cambio en {tablas['momentos_de_cambio']['match_id'].nunique()}; balon_parado_partidos con "
            "la reticula completa; formacion con los periodos 1 y 2 en cada partido")
    return fallas


def validar_pato(tablas, esperados):
    # formacion y minute son enteros; cada partido tiene la formacion de los periodos 1 y 2.
    fallas = []
    for nombre, col in ENTEROS_PATO.items():
        if not pd.api.types.is_integer_dtype(tablas[nombre][col]):
            fallas.append(f"{col} de {_origen(nombre)} no es entero ({tablas[nombre][col].dtype})")
    f = tablas["formacion_por_periodo"]
    for periodo in (1, 2):
        con = set(f.loc[(f["period"] == periodo).to_numpy(dtype=bool), "match_id"].astype("int64"))
        if esperados - con:
            fallas.append(f"formacion_por_periodo: a {len(esperados - con)} partidos les falta el periodo {periodo}, "
                          f"por ejemplo {sorted(esperados - con)[:3]}")
    otros = int((~f["period"].isin([1, 2])).sum())
    if otros:
        _aviso(f"formacion_por_periodo: {otros} filas de periodos distintos de 1 y 2 no se usan")
    return fallas


def _distintos(a, b):
    # Posiciones donde dos columnas de contexto no coinciden, comparadas como texto (nulo con nulo coincide).
    ta, tb = a.astype("string").fillna("<nulo>").to_numpy(), b.astype("string").fillna("<nulo>").to_numpy()
    return int((ta != tb).sum())


def _comparar(nombre, pares):
    malos = [f"{c} ({n})" for c, a, b in pares if (n := _distintos(a.reset_index(drop=True), b.reset_index(drop=True)))]
    if malos:
        return [f"{nombre}: el contexto repetido no coincide con la fase 3 en {malos}"]
    _ok(f"{nombre}: contexto repetido igual al de la fase 3 ({', '.join(c for c, _, _ in pares)})")
    return []


def validar_contexto(tablas):
    # El contexto que repiten Pablo y Pato debe ser igual al de la fase 3; no se copia.
    fallas = []
    cp, cpar = tablas["contexto_posesiones"], tablas["contexto_partidos"]

    bp = tablas["balon_parado_posesiones"].merge(cp, on=LLAVE_POSESION, how="left", suffixes=("_bp", ""))
    signo = np.sign(bp["numerical_state"].astype("Float64").to_numpy(dtype="float64", na_value=np.nan))
    num = pd.Series(np.select([signo < 0, signo == 0, signo > 0], ["inferioridad", "igualdad", "superioridad"],
                              default=None), dtype="string")
    pares = [("team_id", bp["team_id"], bp["possession_team_id"]),
             ("lado", bp["lado"].astype("string").map(LADO_EQ).astype("boolean"), bp["es_eq"]),
             ("numerical_state_cat", bp["numerical_state_cat"], num)]
    pares += [(c, bp[f"{c}_bp"], bp[c]) for c in CONTEXTO_BP_POSESION]
    fallas += _comparar("balon_parado_posesiones", pares)

    d = tablas["defensa_partidos"].merge(cpar, on="match_id", how="left", suffixes=("_d", ""))
    pares = [(c, d[f"{c}_d"], d[c]) for c in CONTEXTO_DEFENSA]
    pares += [("es_local", d["es_local"], d["is_home"]),
              ("fase", d["fase"].astype("string").map(FASE_A_STAGE), d["stage"])]
    fallas += _comparar("defensa_partidos", pares)

    b = tablas["balon_parado_partidos"].merge(cpar, on="match_id", how="left", suffixes=("_b", ""))
    equipo = np.where(b["lado"].astype("string") == "a_favor", EQ, b["rival_id"].astype("float64"))
    pares = [("team_id", b["team_id"].astype("float64"), pd.Series(equipo, dtype="float64")),
             ("torneo", b["torneo_b"], b["torneo"]), ("es_final", b["es_final_b"], b["es_final"]),
             ("fase", b["fase"].astype("string").map(FASE_A_STAGE), b["stage"])]
    fallas += _comparar("balon_parado_partidos", pares)

    mo = tablas["momentos_de_cambio"].merge(cpar, on="match_id", how="left", suffixes=("_m", ""))
    pares = [("es_local", mo["es_local"], mo["is_home"]), ("torneo", mo["torneo_m"], mo["torneo"]),
             ("fase", mo["fase"].astype("string").map(FASE_A_STAGE), mo["stage"])]
    fallas += _comparar("momentos_de_cambio", pares)

    o = tablas["onces_iniciales"].merge(cpar, on="match_id", how="left", suffixes=("_o", "")).merge(
        tablas["defensa_partidos"][["match_id", "match_date"]], on="match_id", how="left", suffixes=("", "_d"))
    pares = [("torneo", o["torneo_o"], o["torneo"]), ("fase", o["fase"].astype("string").map(FASE_A_STAGE), o["stage"]),
             ("match_date", o["match_date"], o["match_date_d"])]
    fallas += _comparar("onces_iniciales", pares)
    return fallas


# ---------------------------------------------------------------- eventos de Lee

def eventos_lee(tablas):
    # ataque_eventos con equipo, posesion, periodo y tipo de cada evento, solo periodos 1 a 4; marca del_eq (evento
    # del America) y con_balon (evento del equipo que tiene la posesion) y prepara columnas 0/1 para sumar.
    fallas = []
    ae, ev, cp = tablas["ataque_eventos"], tablas["eventos"], tablas["contexto_posesiones"]
    fallas += _huerfanos("ataque_eventos", ae, ev, LLAVE_EVENTO, "eventos")
    fallas += _huerfanos("eventos", ev, ae, LLAVE_EVENTO, "ataque_eventos")
    e = ae.merge(ev, on=LLAVE_EVENTO, how="inner", validate="one_to_one")
    juego = e["period"].isin(PERIODOS_JUEGO).to_numpy(dtype=bool)
    tanda = int((~juego).sum())
    e = e[juego]
    fallas += _huerfanos("eventos de los periodos 1 a 4", e, cp, LLAVE_POSESION, "contexto_posesiones")
    e = e.merge(cp[LLAVE_POSESION + ["possession_team_id"]], on=LLAVE_POSESION, how="left", validate="many_to_one")
    e["del_eq"] = _mascara(e["team_id"] == EQ)
    e["con_balon"] = _mascara(e["team_id"] == e["possession_team_id"])
    for col in CONTEOS_POSESION:
        e[f"v_{col}"] = _mascara(e[col]).astype("int64")
    for col, tipo in APLICA_360.items():
        aplica = (e["type_name"] == tipo).to_numpy(dtype=bool)
        e[f"a_{col}"] = aplica.astype("int64")
        e[f"c_{col}"] = (aplica & e[col].notna().to_numpy(dtype=bool)).astype("int64")
    sin_360 = {c: int((e[f"a_{c}"] - e[f"c_{c}"]).sum()) for c in APLICA_360}
    print(f"eventos de Lee: {len(e):,} de los periodos 1 a 4; {tanda} del periodo 5 descartados; "
          f"{int((~e['con_balon']).sum()):,} del equipo sin el balon no cuentan para la posesion; sin 360 (nulos) "
          f"en su tipo de evento: {sin_360}")
    return e, fallas


def validar_solo_america(tablas, e):
    # Lo que Lee solo calcula para el America no debe traer valores del rival; si los trae, falla en vez de borrarlos.
    fallas = []
    rival_ev = {c: int((e[f"v_{c}"].to_numpy() == 1)[~e["del_eq"].to_numpy()].sum()) for c in SOLO_EQ_EVENTO}
    if any(rival_ev.values()):
        fallas.append(f"ataque_eventos: True del rival en metricas que Lee solo calcula para el America {rival_ev}")
    ap = tablas["ataque_posesiones"].merge(tablas["contexto_posesiones"][LLAVE_POSESION + ["es_eq"]],
                                           on=LLAVE_POSESION, how="left")
    rival = ap[~_mascara(ap["es_eq"])]
    cadena_rival = int(_mascara(rival["build_up_chain"]).sum())
    if cadena_rival:
        fallas.append(f"ataque_posesiones: {cadena_rival} posesiones del rival con build_up_chain True")
    con_valor = rival[(rival[CADENAS].fillna(0) > 0).any(axis=1).to_numpy(dtype=bool)]
    llaves = set(zip(con_valor["match_id"].astype("int64"), con_valor["possession"].astype("int64")))
    nuevas = llaves - EXCEPCIONES_CADENA_RIVAL
    if nuevas:
        fallas.append(f"ataque_posesiones: {len(nuevas)} posesiones del rival con xg_chain o xg_buildup > 0, por "
                      f"ejemplo {sorted(nuevas)[:3]}")
    for m, p in sorted(llaves & EXCEPCIONES_CADENA_RIVAL):
        fila = con_valor[(con_valor["match_id"] == m) & (con_valor["possession"] == p)].iloc[0]
        _aviso(f"ataque_posesiones: la posesion del rival ({m}, {p}) trae xg_chain {fila['xg_chain']:.6f}; se anula "
               "como el resto del rival (avisar a Lee)")
    if not fallas:
        _ok(f"solo del America: 0 True del rival en {', '.join(SOLO_EQ_EVENTO)} y build_up_chain; xg_chain y "
            f"xg_buildup del rival en 0 salvo {len(llaves & EXCEPCIONES_CADENA_RIVAL)} excepcion conocida")
    return fallas


def _sumas_lee(eventos, grupo):
    # Conteos de True, sumas y banderas 360 de un conjunto de eventos agrupado por `grupo`.
    g = eventos.groupby(grupo)
    v = g[[f"v_{c}" for c in CONTEOS_POSESION]].sum()
    v.columns = list(CONTEOS_POSESION)
    for col, tipo in APLICA_360.items():
        aplica, con_valor = g[f"a_{col}"].sum(), g[f"c_{col}"].sum()
        # el conteo queda nulo si el equipo tuvo eventos de ese tipo y ninguno trae 360
        v[col] = v[col].astype("Int64").mask((aplica > 0) & (con_valor == 0))
    v["xa"] = g["xa"].sum()
    v["obv_net"] = g["obv_net"].sum(min_count=1)
    v["_hay"] = g.size()
    return v


# ---------------------------------------------------------------- posesiones

def armar_posesiones(tablas, e):
    cp, cpar = tablas["contexto_posesiones"], tablas["contexto_partidos"]
    out = cp.merge(cpar[["match_id", "is_home"]], on="match_id", how="left", validate="many_to_one")
    out = out.merge(tablas["ataque_posesiones"], on=LLAVE_POSESION, how="left", validate="one_to_one")
    rival = ~_mascara(out["es_eq"])
    out.loc[rival, "build_up_chain"] = pd.NA
    out.loc[rival, CADENAS] = np.nan

    sumas = _sumas_lee(e[e["con_balon"].to_numpy()], LLAVE_POSESION).reset_index()
    out = out.merge(sumas, on=LLAVE_POSESION, how="left", validate="one_to_one")
    hay = out.pop("_hay").notna().to_numpy()
    for col, nuevo in CONTEOS_POSESION.items():
        # sin eventos propios vale 0; un nulo de 360 (ningun evento de su tipo con frame) se conserva
        out[nuevo] = out.pop(col).astype("Int64").mask(~hay, 0)
        if col in SOLO_EQ_EVENTO:
            out.loc[rival, nuevo] = pd.NA
    out["xa"] = out.pop("xa").fillna(0.0).astype("float64")
    out["obv_neto"] = out.pop("obv_net").astype("float64")
    print("posesiones con nulo: " + ", ".join(
        f"{CONTEOS_POSESION[c]} {int(out[CONTEOS_POSESION[c]].isna().sum()):,} (sin 360)" for c in APLICA_360) +
        f", obv_neto {int(out['obv_neto'].isna().sum()):,} (ningun evento propio con obv_net)")

    bp = tablas["balon_parado_posesiones"][LLAVE_POSESION + COLS_BP_POSESION + list(RENOMBRE_BP)].rename(
        columns=RENOMBRE_BP).astype({"tiros_bp": "Int64", "goles_bp": "Int64", "xg_bp": "float64"})
    return out.merge(bp, on=LLAVE_POSESION, how="left", validate="one_to_one")


# ---------------------------------------------------------------- partidos

def pivote_balon_parado(bpp, match_ids):
    # {medida}_{tipo}_{lado} con los tipos de origen; saques_juego_abierto_* se omiten y deben venir nulas.
    bpp = bpp.assign(_tipo=bpp["set_piece_type"].astype("string").map(TIPOS_BP),
                     _lado=bpp["lado"].astype("string").map(LADOS_BP)).set_index(["match_id", "_tipo", "_lado"])
    out = pd.DataFrame({"match_id": match_ids.astype("int64")})
    fallas = []
    for medida in MEDIDAS_BP:
        for tipo in TIPOS_BP.values():
            for lado in LADOS_BP.values():
                nombre = f"{medida}_{tipo}_{lado}"
                serie = bpp.xs((tipo, lado), level=["_tipo", "_lado"])[medida]
                if nombre in SIN_SAQUE:
                    if serie.notna().any():
                        fallas.append(f"balon_parado_partidos: {nombre} trae {int(serie.notna().sum())} valores; en "
                                      "juego abierto no hay saque")
                    continue
                out[nombre] = out["match_id"].map(serie).astype(serie.dtype)
    nulas = [c for c in COLS_PIVOTE if out[c].isna().any()]
    if nulas:
        _aviso(f"balon_parado_partidos: columnas pivotadas con nulos {nulas}")
    return out.astype({"match_id": "Int64"}), fallas


def _por_partido(match_ids, sumas, col, entero):
    # Columna de `sumas` (indexada por match_id) en el orden de los partidos; sin eventos vale 0 (o nulo en obv).
    hay = match_ids.isin(sumas.index).to_numpy()
    serie = match_ids.map(sumas[col])
    if entero:
        return serie.astype("Int64").mask(~hay, 0)
    return serie.astype("float64") if col == "obv_net" else serie.astype("float64").fillna(0.0)


def totales_lee(tablas, e, match_ids):
    # Por partido, todo lo que hizo cada equipo: eventos por team_id (periodos 1 a 4, administrativas incluidas).
    # cadenas_construccion_eq y xg_chain_eq van por possession_team_id, sin posesiones administrativas.
    out = pd.DataFrame({"match_id": match_ids})
    del_eq = e["del_eq"].to_numpy()
    s_eq, s_rival = _sumas_lee(e[del_eq], "match_id"), _sumas_lee(e[~del_eq], "match_id")
    for col, nombre in CONTEOS_PARTIDO_EQ.items():
        out[nombre] = _por_partido(match_ids, s_eq, col, True)
    ap = tablas["ataque_posesiones"].merge(tablas["contexto_posesiones"][LLAVE_POSESION + [
        "possession_team_id", "es_administrativa"]], on=LLAVE_POSESION, how="left", validate="one_to_one")
    ap = ap[~_mascara(ap["es_administrativa"]) & _mascara(ap["possession_team_id"] == EQ)]
    cadenas = ap[_mascara(ap["build_up_chain"])].groupby("match_id").size()
    out["cadenas_construccion_eq"] = match_ids.map(cadenas).fillna(0).astype("Int64")
    for sufijo, sumas in (("eq", s_eq), ("rival", s_rival)):
        for col, nombre in CONTEOS_PARTIDO_AMBOS.items():
            out[f"{nombre}_{sufijo}"] = _por_partido(match_ids, sumas, col, True)
        for col, nombre in SUMAS_PARTIDO_AMBOS.items():
            out[f"{nombre}_{sufijo}"] = _por_partido(match_ids, sumas, col, False)
    out["xg_chain_eq"] = match_ids.map(ap.groupby("match_id")["xg_chain"].sum()).fillna(0.0).astype("float64")
    return out[["match_id"] + COLS_LEE_PARTIDO]


def columnas_pato(tablas, match_ids):
    # formacion: la tactica predominante (mas minutos) de cada mitad segun Pato; el tiempo extra no tiene columna.
    out = pd.DataFrame({"match_id": match_ids.astype("int64")})
    f = tablas["formacion_por_periodo"]
    for periodo, nombre in ((1, "formacion_1t"), (2, "formacion_2t")):
        serie = f[(f["period"] == periodo).to_numpy(dtype=bool)].set_index("match_id")["formacion"]
        out[nombre] = out["match_id"].map(serie).astype("Int64")
    out["cambia_formacion"] = (out["formacion_1t"] != out["formacion_2t"]).astype("boolean")
    # momentos_de_cambio es solo del America (supuesto escrito en la spec)
    g = tablas["momentos_de_cambio"].groupby("match_id")
    out["n_cambios"] = out["match_id"].map(g["n_cambios"].sum()).fillna(0).astype("Int64")
    out["n_momentos_cambio"] = out["match_id"].map(g.size()).fillna(0).astype("Int64")
    out["minuto_primer_cambio"] = out["match_id"].map(g["minute"].min()).astype("Int64")
    out["cambios_vs_previo"] = out["match_id"].map(
        tablas["onces_iniciales"].set_index("match_id")["cambios_vs_previo"]).astype("float64")
    return out.astype({"match_id": "Int64"})[["match_id"] + COLS_PATO]


def armar_partidos(tablas, e):
    cpar = tablas["contexto_partidos"]
    ids = cpar["match_id"]
    defensa = tablas["defensa_partidos"][["match_id"] + COLS_DEFENSA].astype({"match_id": "Int64"})
    pivote, fallas = pivote_balon_parado(tablas["balon_parado_partidos"], ids)
    out = cpar
    for parte in (defensa, pivote, totales_lee(tablas, e, ids), columnas_pato(tablas, ids)):
        out = out.merge(parte, on="match_id", how="left", validate="one_to_one")
    lee = out[[c for c in COLS_LEE_PARTIDO if c.startswith(("pases_rompe", "recepciones", "obv_neto"))]]
    nulas = {c: int(n) for c, n in lee.isna().sum().items() if n}
    print(f"partidos con nulo en columnas de Lee: {nulas or 'ninguno'}")
    return out, fallas


# ---------------------------------------------------------------- validaciones de salida y cuadres

def columnas_esperadas(tablas):
    pos = list(tablas["contexto_posesiones"].columns) + ["is_home"] + INSUMOS["ataque_posesiones"][1][2:] + \
        list(CONTEOS_POSESION.values()) + list(SUMAS_POSESION.values()) + COLS_BP_POSESION + list(RENOMBRE_BP.values())
    par = list(tablas["contexto_partidos"].columns) + COLS_DEFENSA + COLS_PIVOTE + COLS_LEE_PARTIDO + COLS_PATO
    return pos, par


def validar_salida(nombre, df, base, llave, esperadas):
    fallas = []
    repetidos = sorted({c for c in esperadas if esperadas.count(c) > 1})
    if repetidos:
        fallas.append(f"{nombre}: nombres de columna repetidos entre insumos {repetidos}")
    if list(df.columns) != esperadas:
        fallas.append(f"{nombre}: columnas distintas de las acordadas; sobran {sorted(set(df.columns) - set(esperadas))}"
                      f", faltan {sorted(set(esperadas) - set(df.columns))} o cambio el orden")
    if len(df) != len(base) or not df[llave].reset_index(drop=True).equals(base[llave].reset_index(drop=True)):
        fallas.append(f"{nombre}: {len(df)} filas para {len(base)} de la base o en otro orden")
    if df.duplicated(llave).any():
        fallas.append(f"{nombre}: llave {llave} repetida")
    malos = {c: str(t) for c, t in df.dtypes.items() if str(t) not in TIPOS_SALIDA and not str(t).startswith("datetime64")}
    if malos:
        fallas.append(f"{nombre}: tipos fuera de Int64/float64/boolean/string/category/datetime {malos}")
    if not fallas:
        _ok(f"{nombre}: {len(df):,} filas (las de la base, mismo orden), las {len(df.columns)} columnas acordadas en "
            "orden, llave unica, tipos permitidos")
    return fallas


def cuadres(tablas, e, pos, par):
    fallas = []
    # pases progresivos contra el insumo sin tocar: todos los True del America, menos tanda y posesiones del rival
    crudo = tablas["ataque_eventos"].merge(tablas["eventos"][LLAVE_EVENTO + ["team_id", "period"]], on=LLAVE_EVENTO)
    pp = _mascara(crudo["progressive_pass"]) & _mascara(crudo["team_id"] == EQ)
    total = int(pp.sum())
    tanda = int((pp & ~crudo["period"].isin(PERIODOS_JUEGO).to_numpy(dtype=bool)).sum())
    en_rival = int(((e["v_progressive_pass"] == 1) & e["del_eq"] & ~e["con_balon"]).sum())
    en_pos, en_par = int(pos["n_pases_progresivos"].sum()), int(par["pases_progresivos_eq"].sum())
    if en_pos == total - tanda - en_rival and en_par == total - tanda:
        _ok(f"pases progresivos: {total:,} True del America en ataque_eventos - {tanda} en la tanda - {en_rival} en "
            f"posesiones del rival = {en_pos:,} en posesiones; pases_progresivos_eq suma {en_par:,}")
    else:
        fallas.append(f"cuadre de pases progresivos: {total} en ataque_eventos, {tanda} en la tanda, {en_rival} en "
                      f"posesiones del rival, {en_pos} en posesiones, {en_par} por partido")
    # columnas de los dos equipos: posesiones del equipo + eventos del equipo sin el balon = total por partido
    pares = [("line_breaking_pass", "n_pases_rompe_lineas", "pases_rompe_lineas", "v_line_breaking_pass"),
             ("ball_receipt_in_space", "n_recepciones_espacio", "recepciones_espacio", "v_ball_receipt_in_space"),
             ("xa", "xa", "xa", "xa"), ("obv_net", "obv_neto", "obv_neto", "obv_net")]
    es_eq = _mascara(pos["es_eq"])
    for _, col_pos, col_par, col_ev in pares:
        partes = []
        for sufijo, del_equipo in (("eq", True), ("rival", False)):
            filas = es_eq if del_equipo else ~es_eq
            eventos = e[(e["del_eq"] == del_equipo).to_numpy() & ~e["con_balon"].to_numpy()]
            en_posesiones = float(pos.loc[filas, col_pos].astype("float64").sum())
            sin_balon = float(eventos[col_ev].astype("float64").sum())
            por_partido = float(par[f"{col_par}_{sufijo}"].astype("float64").sum())
            if abs(en_posesiones + sin_balon - por_partido) > TOL * max(1.0, abs(por_partido)):
                fallas.append(f"cuadre de {col_par}_{sufijo}: {en_posesiones:.4f} en posesiones + {sin_balon:.4f} sin "
                              f"el balon != {por_partido:.4f} por partido")
            partes.append(f"{sufijo} {en_posesiones:,.2f} + {sin_balon:,.2f} sin balon = {por_partido:,.2f}")
        if not any(f.startswith(f"cuadre de {col_par}_") for f in fallas):
            _ok(f"{col_par}: posesiones del equipo + eventos del equipo sin el balon = total por partido "
                f"({'; '.join(partes)})")
    # xg_chain_eq contra ataque_posesiones del America
    ap = tablas["ataque_posesiones"].merge(tablas["contexto_posesiones"][LLAVE_POSESION + ["possession_team_id"]],
                                           on=LLAVE_POSESION)
    esperado = float(ap.loc[_mascara(ap["possession_team_id"] == EQ), "xg_chain"].sum())
    por_partido, en_posesiones = float(par["xg_chain_eq"].sum()), float(pos.loc[es_eq, "xg_chain"].sum())
    if abs(esperado - por_partido) > TOL or abs(esperado - en_posesiones) > TOL:
        fallas.append(f"cuadre de xg_chain_eq: {por_partido:.6f} por partido y {en_posesiones:.6f} en posesiones contra "
                      f"{esperado:.6f} en ataque_posesiones")
    else:
        _ok(f"xg_chain_eq por partido = xg_chain de las posesiones del America = ataque_posesiones ({esperado:.3f})")
    # informativos: balon parado de Pablo contra es_balon_parado y resultado contra goles
    bp = pos["set_piece_type"].notna()
    if int(bp.sum()) == int(pos["es_balon_parado"].sum()) and bool((bp == pos["es_balon_parado"]).all()):
        _ok(f"balon parado (informativo): las {int(bp.sum()):,} posesiones de Pablo son las de es_balon_parado")
    else:
        _aviso(f"balon parado: {int(bp.sum())} posesiones de Pablo y {int(pos['es_balon_parado'].sum())} con "
               "es_balon_parado")
    signo = np.sign((par["goles_eq"] - par["goles_rival"]).to_numpy(dtype="float64"))
    esperado_res = pd.Series(np.select([signo > 0, signo == 0], ["G", "E"], "P"))
    distintos = _distintos(par["resultado"].reset_index(drop=True), esperado_res)
    if distintos:
        _aviso(f"resultado de Pablo distinto de goles_eq contra goles_rival en {distintos} de {len(par)} partidos")
    else:
        _ok(f"resultado (informativo): cuadra con goles_eq y goles_rival en los {len(par)} partidos")
    return fallas


# ---------------------------------------------------------------- escritura

def _bloqueados(archivos):
    # Destinos que ya existen y no se pueden abrir para escribir (en Windows, abiertos en otro proceso).
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
    if ruta.is_dir():
        shutil.rmtree(ruta, ignore_errors=True)
    else:
        ruta.unlink(missing_ok=True)
    if ruta.exists():
        print(f"AVISO: no se pudo borrar el temporal {ruta}", file=sys.stderr)


def escribir(tablas):
    # Mismo esquema que 03_contexto.py: carpeta temporal, revision de bloqueos y reemplazo archivo por archivo.
    archivos = list(tablas)
    try:
        PROCESSED.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=PREFIJO_TMP, dir=PROCESSED))
    except OSError as e:
        raise ErrorAnalitica(f"no se pudo preparar {PROCESSED}: {e}") from e
    reemplazados = []
    try:
        try:
            for nombre, df in tablas.items():
                df.to_parquet(tmp / nombre, compression="zstd", index=False)
        except ERRORES_ESCRITURA as e:
            raise ErrorAnalitica(f"no se pudo escribir en la carpeta temporal {tmp}; no se reemplazo nada: "
                                 f"{type(e).__name__}: {e}") from e
        bloqueados = _bloqueados(archivos)
        if bloqueados:
            raise ErrorAnalitica(f"no se reemplazo nada en {PROCESSED}: estos destinos estan bloqueados o no se pueden "
                                 f"escribir: {bloqueados}. Cierralos y vuelve a correr.")
        for archivo in archivos:
            try:
                os.replace(tmp / archivo, PROCESSED / archivo)
                reemplazados.append(archivo)
            except OSError as e:
                if not reemplazados:
                    raise ErrorAnalitica(f"no se reemplazo nada en {PROCESSED}: fallo {archivo} ({e})") from e
                raise ErrorAnalitica(
                    f"el reemplazo quedo a medias en {PROCESSED}: ya se reemplazaron {reemplazados}; faltan "
                    f"{archivos[len(reemplazados):]} ({e}). Los que faltan siguen en la carpeta temporal {tmp}, que no "
                    "se borro: copialos a mano o vuelve a correr.") from e
            except KeyboardInterrupt:
                if reemplazados:
                    print(f"AVISO: interrumpido a medias; ya se reemplazaron {reemplazados} y el resto sigue en la "
                          f"carpeta temporal {tmp}, que no se borro.", file=sys.stderr)
                raise
    finally:
        if not 0 < len(reemplazados) < len(archivos):
            _borrar(tmp)
    for viejo in PROCESSED.glob(f"{PREFIJO_TMP}*"):
        if viejo != tmp:
            _borrar(viejo)


# ---------------------------------------------------------------- principal

def ensamblar(tablas):
    # Devuelve (analitica_posesiones, analitica_partidos, fallas).
    fallas = validar_llaves(tablas)
    if fallas:
        return None, None, fallas
    cp = tablas["contexto_posesiones"]
    fallas += _huerfanos("ataque_posesiones", tablas["ataque_posesiones"], cp, LLAVE_POSESION, "contexto_posesiones")
    fallas += _huerfanos("balon_parado_posesiones", tablas["balon_parado_posesiones"], cp, LLAVE_POSESION,
                         "contexto_posesiones")
    fallas += validar_partidos(tablas)
    if fallas:
        return None, None, fallas
    fallas += validar_contexto(tablas)
    e, f = eventos_lee(tablas)
    fallas += f
    if fallas:
        return None, None, fallas
    fallas += validar_solo_america(tablas, e)
    if fallas:
        return None, None, fallas

    pos = armar_posesiones(tablas, e)
    par, f = armar_partidos(tablas, e)
    fallas += f
    print(f"balon_parado_partidos: pivote a {len(COLS_PIVOTE)} columnas; {SIN_SAQUE} se omiten (vienen nulas). "
          f"defensa_partidos: match_date, resultado y {len(METRICAS_DEFENSA)} metricas; contexto repetido no copiado")
    esperadas_pos, esperadas_par = columnas_esperadas(tablas)
    fallas += validar_salida(SALIDA_POSESIONES, pos, cp, LLAVE_POSESION, esperadas_pos)
    fallas += validar_salida(SALIDA_PARTIDOS, par, tablas["contexto_partidos"], ["match_id"], esperadas_par)
    if fallas:
        return None, None, fallas
    fallas += cuadres(tablas, e, pos, par)
    return pos, par, fallas


def resumen(pos, par, n_ctx_pos, n_ctx_par):
    print(f"{SALIDA_POSESIONES}: {len(pos):,} filas, {len(pos.columns)} columnas ({len(pos.columns) - n_ctx_pos} nuevas "
          f"sobre contexto_posesiones)")
    print(f"{SALIDA_PARTIDOS}: {len(par):,} filas, {len(par.columns)} columnas ({len(par.columns) - n_ctx_par} nuevas "
          f"sobre contexto_partidos)")
    eq = _mascara(pos["es_eq"])
    print("totales del America en posesiones: " + ", ".join(
        f"{c} {pos.loc[eq, c].sum():,.0f}" for c in list(CONTEOS_POSESION.values())) +
        f", xa {pos.loc[eq, 'xa'].sum():.2f}, obv_neto {pos.loc[eq, 'obv_neto'].sum():.2f}, "
        f"xg_chain {pos.loc[eq, 'xg_chain'].sum():.2f}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-escribir", action="store_true", help="junta y valida sin escribir en data/processed/")
    args = p.parse_args()
    inicio = time.perf_counter()

    try:
        tablas = {nombre: leer(nombre) for nombre in INSUMOS}
    except ErrorAnalitica as e:
        print(f"ERROR: {e}\nNo se escribio nada.", file=sys.stderr)
        return 1
    print("lee " + ", ".join(f"{n} {len(t):,}" for n, t in tablas.items()))
    pos, par, fallas = ensamblar(tablas)
    if fallas:
        print(f"ERROR: {len(fallas)} validaciones duras fallaron:", file=sys.stderr)
        for x in fallas:
            print(f"   {x}", file=sys.stderr)
        print("No se escribio nada.", file=sys.stderr)
        return 1
    resumen(pos, par, len(tablas["contexto_posesiones"].columns), len(tablas["contexto_partidos"].columns))
    if args.sin_escribir:
        print(f"Sin escribir (--sin-escribir). {time.perf_counter() - inicio:.1f} s")
        return 0
    try:
        escribir({SALIDA_POSESIONES: pos, SALIDA_PARTIDOS: par})
    except ErrorAnalitica as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"Escrito en {PROCESSED.relative_to(ROOT).as_posix()}/: {SALIDA_POSESIONES}, {SALIDA_PARTIDOS}. "
          f"{time.perf_counter() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
