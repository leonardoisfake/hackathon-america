"""Patrones de juego (fase 4, Lee): tipos de posesion, consistencia entre partidos y evolucion por jornada.

Responde "el equipo mantiene una identidad?" sobre el America de Jardine (91 partidos) con tres analisis:
1. Tipos de posesion: k-means sobre las posesiones validas del America (pases, duracion, directness,
   zona de inicio y zona maxima alcanzada).
2. Consistencia: cuanto varia cada metrica de un partido a otro, comparada con la variacion que habria solo
   por azar entre posesiones (permutacion). parte_real = 1 - (sd_azar / sd)^2 es la fraccion de esa variacion
   que el azar no explica (incluye rival, marcador, localia y torneo, no solo decisiones del entrenador).
3. Evolucion por jornada: tendencia de cada metrica a lo largo del torneo (fase regular, efectos fijos de torneo).

Uso:
    python scripts/04_patrones.py                  # calcula, valida y escribe en data/processed/
    python scripts/04_patrones.py --sin-escribir   # calcula y valida, sin escribir
    python scripts/04_patrones.py --k 5            # fuerza el numero de clusters
    python scripts/04_patrones.py --replicas 200 --permutaciones 100 --replicas-estabilidad 5   # prueba rapida

Entradas (todas ya existen; este script no recalcula nada de otros):
    data/processed/analitica_posesiones.parquet   03_tabla_analitica.py (Yordi), llave (match_id, possession)
    data/processed/analitica_partidos.parquet     03_tabla_analitica.py (Yordi), llave match_id
    data/interim/eventos.parquet                  02_limpieza.py (Yordi); solo possession_directness, x y team_id

Salidas (data/processed/, escritura atomica; si falla una validacion no se escribe nada):
    patrones_posesiones_cluster.parquet   una fila por posesion clusterizada, con su cluster y las 5 variables crudas
    patrones_clusters_perfil.parquet      una fila por cluster: tamano, variables, resultados y etiqueta sugerida
    patrones_clusters_torneo.parquet      peso de cada cluster en cada torneo
    patrones_k_seleccion.parquet          silueta e inercia por k, el k elegido y la estabilidad (bootstrap por partidos)
    patrones_partidos.parquet             una fila por partido: contexto, valor de cada metrica y peso de cada cluster
    patrones_consistencia.parquet         una fila por metrica: media, sd, CV, variacion contra el azar y lectura
    patrones_tendencia.parquet            una fila por metrica: pendiente por jornada, IC bootstrap, efecto y lectura

Supuestos explicitos (todos son constantes de abajo, para declararlos en el framework):
    - Universo del clustering: posesiones del America (es_eq), no administrativas, periodos 1 a 4, validas (B1: al
      menos 3 pases o 1 tiro sin penal, y no balon parado) y con directness (solo existe en juego abierto).
    - directness es possession_directness de StatsBomb (0 a 1, igual en todos los eventos de la posesion).
    - x_max es la x maxima alcanzada (como B6 y D5 de METRICAS_LEE.md): la x mas alta (yardas, perspectiva del
      America) de los eventos con ubicacion del America en la posesion. A diferencia de B2 no usa el destino de
      pases y conducciones. "Llega al tercio final" es x_max >= TERCIO_FINAL (METRICAS_LEE.md, seccion 2).
    - n_pases y duracion se pasan por log1p (distribuciones muy sesgadas) y todo se escala con mediana y MAD.
    - n_pases y duracion estan muy correlacionadas: el "tempo" pesa el doble. Se puede ajustar en FEATURES.
    - k se elige por silueta entre K_MIN y K_MAX, con un cluster minimo de MIN_PCT_CLUSTER.
    - Lectura de consistencia: alta si parte_real >= PARTE_REAL_ALTA, moderada si >= PARTE_REAL_MODERADA y estable
      si es menor o si la permutacion no encuentra diferencia (p > ALFA).
    - Un partido con menos de MIN_POSESIONES_PARTIDO posesiones en una metrica queda nulo en esa metrica.
    - La tendencia usa solo la fase regular (la liguilla no tiene jornadas comparables).

Codigo de salida: 0 si todo cuadra, 1 si falla una validacion o falta un insumo.
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]

POSESIONES = "data/processed/analitica_posesiones.parquet"
PARTIDOS = "data/processed/analitica_partidos.parquet"
EVENTOS = "data/interim/eventos.parquet"
DIR_SALIDA = ROOT / "data" / "processed"

SAL_POSESIONES = "patrones_posesiones_cluster.parquet"
SAL_PERFIL = "patrones_clusters_perfil.parquet"
SAL_TORNEO = "patrones_clusters_torneo.parquet"
SAL_K = "patrones_k_seleccion.parquet"
SAL_PARTIDOS = "patrones_partidos.parquet"
SAL_CONSISTENCIA = "patrones_consistencia.parquet"
SAL_TENDENCIA = "patrones_tendencia.parquet"

EQUIPO_ID = 1229
N_PARTIDOS = 91
N_REGULAR = 66

COLS_POS = ["match_id", "possession", "es_eq", "is_valid_possession", "es_administrativa", "es_balon_parado",
            "n_pases", "duracion", "x_inicio", "n_tiros", "xg", "n_pases_progresivos", "n_pases_rompe_lineas",
            "n_recepciones_espacio", "obv_neto", "build_up_chain"]
COLS_PAR = ["match_id", "torneo", "match_week", "stage", "ppda_juego_abierto", "press_height"]
COLS_EV = ["match_id", "possession", "period", "team_id", "x", "possession_directness"]

# (nombre, columna en la tabla de clustering, transformacion, peso)
FEATURES = [
    ("pases", "n_pases", "log1p", 1.0),
    ("duracion", "duracion", "log1p", 1.0),
    ("directness", "directness", None, 1.0),
    ("x_inicio", "x_inicio", None, 1.0),
    ("x_max", "x_max", None, 1.0),
]

SEMILLA = 20261021
K_MIN, K_MAX = 3, 7
MIN_PCT_CLUSTER = 0.05
N_INIT = 10
N_INIT_ESTAB = 3
MAX_ITER = 100
REPLICAS_ESTABILIDAD = 30
SILUETA_MUESTRA = 3000
SILUETA_DEBIL = 0.25
ARI_BUENO, ARI_MODERADO = 0.75, 0.5
ESCALA_MAD = 1.4826

MIN_POSESIONES_PARTIDO = 10
PERMUTACIONES = 1000
REPLICAS = 2000
ALFA = 0.05
PARTE_REAL_ALTA = 0.50  # parte real de la variacion entre partidos desde la cual se lee "alta"
PARTE_REAL_MODERADA = 0.25
EFECTO_MIN = 0.2  # mismo corte que 04_contexto.py, pero aqui el efecto va en sd entre partidos, no en g o h
TERCIO_FINAL = 80  # METRICAS_LEE.md, seccion 2: tercio final x >= 80 yardas

LECTURAS_CONSISTENCIA = ["alta", "moderada", "estable", "sin referencia de azar", "sin dato"]
LECTURAS_TENDENCIA = ["tendencia", "tendencia pequena", "indicio", "sin tendencia clara", "sin dato"]

ERRORES_ESCRITURA = (OSError, ValueError, TypeError, pa.lib.ArrowException)


class ErrorPatrones(Exception):
    pass


def _ok(msg):
    print(f"[OK] {msg}")


def _aviso(msg):
    print(f"AVISO: {msg}")


@dataclass(frozen=True)
class MetricaPartido:
    # Una metrica por partido: media de una columna de posesion, o una columna de analitica_partidos.
    metrica: str
    etiqueta: str
    unidad: str
    origen: str  # "posesiones" o "partidos"
    columna: str
    universo: str = "validas"  # posesiones: "todas" (America, no administrativas), "validas" o "clusterizadas"


METRICAS_BASE = [
    MetricaPartido("directness", "Directness medio de la posesion", "indice 0 a 1", "posesiones", "directness"),
    MetricaPartido("pases", "Pases por posesion", "pases", "posesiones", "n_pases"),
    MetricaPartido("duracion", "Duracion media de la posesion", "segundos", "posesiones", "duracion"),
    MetricaPartido("altura_inicio", "Altura de inicio de la posesion", "yardas", "posesiones", "x_inicio"),
    MetricaPartido("altura_max", "Altura maxima alcanzada en la posesion", "yardas", "posesiones", "x_max"),
    MetricaPartido("con_tiro", "Posesiones validas con tiro", "proporcion", "posesiones", "con_tiro"),
    MetricaPartido("xg", "xG por posesion", "xG", "posesiones", "xg"),
    MetricaPartido("pases_progresivos", "Pases progresivos por posesion", "pases", "posesiones",
                   "n_pases_progresivos"),
    MetricaPartido("pases_rompe_lineas", "Pases que rompen lineas por posesion", "pases", "posesiones",
                   "n_pases_rompe_lineas"),
    MetricaPartido("recepciones_espacio", "Recepciones en espacio por posesion", "recepciones", "posesiones",
                   "n_recepciones_espacio"),
    MetricaPartido("obv_neto", "OBV neto por posesion", "OBV", "posesiones", "obv_neto"),
    MetricaPartido("cadena_construccion", "Posesiones validas que son cadena de construccion", "proporcion",
                   "posesiones", "build_up_chain"),
    MetricaPartido("balon_parado", "Posesiones que nacen de balon parado", "proporcion", "posesiones",
                   "es_balon_parado", "todas"),
    MetricaPartido("ppda", "PPDA en juego abierto", "pases por accion", "partidos", "ppda_juego_abierto"),
    MetricaPartido("altura_presion", "Altura media de la presion", "yardas", "partidos", "press_height"),
]


# ---------------------------------------------------------------- carga

def a_float(serie):
    return serie.astype("Float64").to_numpy(dtype="float64", na_value=np.nan)


def leer(ruta, columnas, autor):
    archivo = ROOT / ruta
    if not archivo.exists():
        raise ErrorPatrones(f"no existe {ruta}; lo produce {autor}")
    try:
        nombres = pq.read_schema(archivo).names
    except (OSError, ValueError, pa.lib.ArrowException) as e:
        raise ErrorPatrones(f"no se pudo leer {ruta}: {type(e).__name__}: {e}") from e
    faltan = [c for c in columnas if c not in nombres]
    if faltan:
        raise ErrorPatrones(f"{ruta} no trae las columnas {faltan}; revisa {autor}")
    try:
        return pd.read_parquet(archivo, columns=columnas)
    except (OSError, ValueError, pa.lib.ArrowException) as e:
        raise ErrorPatrones(f"no se pudo leer {ruta}: {type(e).__name__}: {e}") from e


def _llave_entera(df, llave, ruta):
    nulas = int(df[llave].isna().any(axis=1).sum())
    if nulas:
        raise ErrorPatrones(f"{ruta}: {nulas} filas con la llave {llave} nula")
    df[llave] = df[llave].astype("int64")
    repetidas = int(df.duplicated(llave).sum())
    if repetidas:
        raise ErrorPatrones(f"{ruta}: {repetidas} filas con la llave {llave} repetida")


def cargar():
    pos = leer(POSESIONES, COLS_POS, "03_tabla_analitica.py (Yordi)")
    par = leer(PARTIDOS, COLS_PAR, "03_tabla_analitica.py (Yordi)")
    ev = leer(EVENTOS, COLS_EV, "02_limpieza.py (Yordi)")
    _llave_entera(pos, ["match_id", "possession"], POSESIONES)
    _llave_entera(par, ["match_id"], PARTIDOS)
    ev[["match_id", "possession"]] = ev[["match_id", "possession"]].astype("int64")
    if len(par) != N_PARTIDOS:
        raise ErrorPatrones(f"{PARTIDOS} tiene {len(par)} partidos y se esperaban {N_PARTIDOS}")
    if set(pos["match_id"]) != set(par["match_id"]):
        raise ErrorPatrones(f"los match_id de {POSESIONES} y de {PARTIDOS} no son los mismos")
    for col in ("es_eq", "es_administrativa", "is_valid_possession", "es_balon_parado"):
        if pos[col].isna().any():
            raise ErrorPatrones(f"{POSESIONES}: {int(pos[col].isna().sum())} filas con {col} nula")
        pos[col] = pos[col].astype(bool)
    for col in ("torneo", "stage"):
        if par[col].isna().any():
            raise ErrorPatrones(f"{PARTIDOS}: {int(par[col].isna().sum())} filas con {col} nula")
        par[col] = par[col].astype("string").str.strip()
    n_reg = int((par["stage"] == "regular").sum())
    if n_reg == 0:
        raise ErrorPatrones(f"{PARTIDOS}: ningun partido con stage = 'regular' (hay {sorted(par['stage'].unique())})")
    if n_reg != N_REGULAR:
        _aviso(f"{n_reg} partidos de fase regular y se esperaban {N_REGULAR}")
    par = par.sort_values("match_id").reset_index(drop=True)
    return pos, par, ev


def posesiones_america(pos, ev):
    # Posesiones del America no administrativas, con la directness y la x maxima sacadas de eventos.
    llave = ["match_id", "possession"]
    ev = ev[(ev["period"] <= 4).fillna(False).to_numpy(dtype=bool)]
    directness = ev.assign(d=a_float(ev["possession_directness"])).groupby(llave)["d"].agg(["mean", "min", "max"])
    propios = ev[(ev["team_id"] == EQUIPO_ID).fillna(False).to_numpy(dtype=bool)]
    x_max = propios.assign(x=a_float(propios["x"])).groupby(llave)["x"].max().rename("x_max")
    ag = pd.concat([directness["mean"].rename("directness"), (directness["max"] - directness["min"]).rename("_dif"),
                    directness["min"].rename("_min"), directness["max"].rename("_max"), x_max], axis=1).reset_index()
    eq = pos[pos["es_eq"] & ~pos["es_administrativa"]].copy()
    eq = eq.merge(ag, how="left", on=llave, validate="one_to_one")
    fuera = int(((eq["_min"] < -1e-9) | (eq["_max"] > 1 + 1e-9)).sum())
    if fuera:
        raise ErrorPatrones(f"{fuera} posesiones con possession_directness fuera de [0, 1]")
    variable = int((eq["_dif"] > 1e-6).sum())
    if variable:
        _aviso(f"possession_directness no es constante en {variable} posesiones; se usa su media")
    eq = eq.drop(columns=["_dif", "_min", "_max"])
    eq["con_tiro"] = eq["n_tiros"] > 0
    return eq


# ---------------------------------------------------------------- k-means en numpy (sin dependencias nuevas)

def _dist2(X, C):
    d = (X ** 2).sum(1)[:, None] - 2 * X @ C.T + (C ** 2).sum(1)[None, :]
    return np.maximum(d, 0.0)


def _etiquetar(X, centros):
    return _dist2(X, centros).argmin(1)


def _kmeanspp(X, k, rng):
    n = len(X)
    centros = np.empty((k, X.shape[1]))
    centros[0] = X[rng.integers(n)]
    d2 = ((X - centros[0]) ** 2).sum(1)
    for j in range(1, k):
        total = d2.sum()
        elegido = rng.choice(n, p=d2 / total) if total > 0 else rng.integers(n)
        centros[j] = X[elegido]
        d2 = np.minimum(d2, ((X - centros[j]) ** 2).sum(1))
    return centros


def _lloyd(X, centros):
    k, dim = centros.shape
    for _ in range(MAX_ITER):
        et = _etiquetar(X, centros)
        cuentas = np.bincount(et, minlength=k)
        nuevos = centros.copy()
        for d in range(dim):
            sumas = np.bincount(et, weights=X[:, d], minlength=k)
            nuevos[cuentas > 0, d] = sumas[cuentas > 0] / cuentas[cuentas > 0]
        quieto = np.allclose(nuevos, centros, atol=1e-8, rtol=0)
        centros = nuevos
        if quieto:
            break
    et = _etiquetar(X, centros)
    return centros, et, float(((X - centros[et]) ** 2).sum())


def kmeans(X, k, rng, n_init):
    mejor = None
    for _ in range(n_init):
        resultado = _lloyd(X, _kmeanspp(X, k, rng))
        if mejor is None or resultado[2] < mejor[2]:
            mejor = resultado
    return mejor


def silueta(X, etiquetas, k, rng):
    n = len(X)
    idx = rng.choice(n, size=SILUETA_MUESTRA, replace=False) if n > SILUETA_MUESTRA else np.arange(n)
    Xs, es = X[idx], etiquetas[idx]
    fila = np.arange(len(es))
    d = np.sqrt(_dist2(Xs, Xs))
    uno = np.eye(k)[es]
    sumas = d @ uno
    cuentas = uno.sum(0)
    if (cuentas > 0).sum() < 2:
        return float("nan")
    n_prop = cuentas[es]
    a = np.where(n_prop > 1, sumas[fila, es] / np.maximum(n_prop - 1, 1), 0.0)
    medias = sumas / np.maximum(cuentas, 1)
    medias[fila, es] = np.inf
    medias[:, cuentas == 0] = np.inf
    b = medias.min(1)
    s = np.where(n_prop > 1, (b - a) / np.maximum(np.maximum(a, b), 1e-12), 0.0)
    return float(s.mean())


def ari(a, b):
    # indice de Rand ajustado entre dos etiquetados (1 = identicos, 0 = como al azar)
    ka, kb = int(a.max()) + 1, int(b.max()) + 1
    tabla = np.bincount(a * kb + b, minlength=ka * kb).reshape(ka, kb).astype(float)

    def comb2(x):
        return x * (x - 1) / 2

    suma_ij, suma_a, suma_b = comb2(tabla).sum(), comb2(tabla.sum(1)).sum(), comb2(tabla.sum(0)).sum()
    total = comb2(tabla.sum())
    esperado = suma_a * suma_b / total
    maximo = (suma_a + suma_b) / 2
    return 1.0 if maximo == esperado else float((suma_ij - esperado) / (maximo - esperado))


def estabilidad(X, base, k, filas_por_partido, rng, replicas):
    # Remuestrea partidos completos, reajusta y compara con el etiquetado base (ARI sobre todas las posesiones).
    n_part = len(filas_por_partido)
    aris = []
    for _ in range(replicas):
        elegidos = rng.integers(0, n_part, n_part)
        filas = np.concatenate([filas_por_partido[i] for i in elegidos])
        centros, _, _ = kmeans(X[filas], k, rng, N_INIT_ESTAB)
        aris.append(ari(base, _etiquetar(X, centros)))
    return np.array(aris)


def matriz_features(df):
    columnas = []
    for nombre, col, trans, _ in FEATURES:
        v = a_float(df[col])
        if trans == "log1p":
            if (v < 0).any():
                raise ErrorPatrones(f"{col} trae valores negativos y no se puede aplicar log1p")
            v = np.log1p(v)
        columnas.append(v)
    return np.column_stack(columnas)


def escalar(M):
    mediana = np.median(M, axis=0)
    mad = np.median(np.abs(M - mediana), axis=0) * ESCALA_MAD
    escala = np.where(mad > 0, mad, M.std(axis=0))
    if (escala == 0).any():
        sin = [FEATURES[i][0] for i in np.flatnonzero(escala == 0)]
        raise ErrorPatrones(f"variables sin variacion en el clustering: {sin}")
    pesos = np.array([f[3] for f in FEATURES])
    return (M - mediana) / escala * pesos


def _nivel(valor, cortes, bajo, medio, alto):
    return bajo if valor <= cortes[0] else alto if valor >= cortes[1] else medio


def etiqueta_sugerida(cluster, directness, pases, cortes_dir, cortes_pases):
    # Solo una sugerencia para arrancar: terciles de toda la muestra. La etiqueta final la decide el equipo.
    d = _nivel(directness, cortes_dir, "directness baja", "directness media", "directness alta")
    p = _nivel(pases, cortes_pases, "posesion corta", "posesion media", "posesion larga")
    return f"{cluster}: {d}, {p}"


def agrupar(datos, args, rng_k, rng_est):
    X = escalar(matriz_features(datos))
    n = len(X)
    ks = sorted(set(range(K_MIN, K_MAX + 1)) | ({args.k} if args.k else set()))
    if max(ks) >= n:
        raise ErrorPatrones(f"solo hay {n} posesiones para el clustering y se piden hasta {max(ks)} clusters")
    ajustes = {}
    filas = []
    for k in ks:
        centros, et, inercia = kmeans(X, k, rng_k, N_INIT)
        pct_min = np.bincount(et, minlength=k).min() / n
        ajustes[k] = (centros, et)
        filas.append({"k": k, "inercia": inercia, "silueta": silueta(X, et, k, rng_k), "pct_cluster_min": pct_min})
    tabla = pd.DataFrame(filas)
    if args.k:
        elegido = args.k
    else:
        candidatos = tabla[tabla["pct_cluster_min"] >= MIN_PCT_CLUSTER]
        if candidatos.empty:
            _aviso(f"ningun k deja todos los clusters con al menos {MIN_PCT_CLUSTER:.0%}; se elige por silueta")
            candidatos = tabla
        elegido = int(candidatos.sort_values(["silueta", "k"], ascending=[False, True]).iloc[0]["k"])
    centros, et = ajustes[elegido]
    # orden estable de los clusters: 1 es el de posesiones mas cortas
    duracion = a_float(datos["duracion"])
    orden = np.argsort([np.median(duracion[et == j]) for j in range(elegido)], kind="stable")
    nuevo = np.empty(elegido, dtype=int)
    nuevo[orden] = np.arange(1, elegido + 1)
    cluster = nuevo[et]
    codigos = pd.factorize(datos["match_id"].to_numpy())[0]
    filas_por_partido = [np.flatnonzero(codigos == i) for i in range(codigos.max() + 1)]
    aris = estabilidad(X, et, elegido, filas_por_partido, rng_est, args.replicas_estabilidad)
    tabla["elegido"] = tabla["k"] == elegido
    for col, valor in (("ari_media", aris.mean()), ("ari_p05", np.quantile(aris, 0.05)),
                       ("ari_p95", np.quantile(aris, 0.95))):
        tabla[col] = np.where(tabla["elegido"], valor, np.nan)
    tabla["n_replicas_ari"] = np.where(tabla["elegido"], len(aris), 0)
    return cluster, elegido, tabla, aris


# ---------------------------------------------------------------- tablas de clusters

def perfil_clusters(datos, k):
    cortes_dir = np.quantile(a_float(datos["directness"]), [1 / 3, 2 / 3])
    cortes_pases = np.quantile(a_float(datos["n_pases"]), [1 / 3, 2 / 3])
    filas = []
    for c in range(1, k + 1):
        sub = datos[datos["cluster"] == c]
        fila = {"cluster": c, "n_posesiones": len(sub), "pct_posesiones": len(sub) / len(datos),
                "n_partidos": sub["match_id"].nunique()}
        for nombre, col, _, _ in FEATURES:
            v = a_float(sub[col])
            fila[f"{nombre}_mediana"] = float(np.nanmedian(v))
            fila[f"{nombre}_media"] = float(np.nanmean(v))
        fila["pct_tercio_final"] = float((a_float(sub["x_max"]) >= TERCIO_FINAL).mean())
        fila["con_tiro"] = float((sub["n_tiros"] > 0).mean())
        fila["xg_media"] = float(np.nanmean(a_float(sub["xg"])))
        for salida, col in (("pases_progresivos_media", "n_pases_progresivos"),
                            ("pases_rompe_lineas_media", "n_pases_rompe_lineas"),
                            ("obv_neto_media", "obv_neto")):
            v = a_float(sub[col])
            fila[salida] = float(np.nanmean(v)) if (~np.isnan(v)).any() else np.nan
        fila["etiqueta_sugerida"] = etiqueta_sugerida(c, fila["directness_mediana"], fila["pases_mediana"],
                                                      cortes_dir, cortes_pases)
        filas.append(fila)
    return pd.DataFrame(filas)


def clusters_por_torneo(datos, partidos, k):
    torneo = datos["match_id"].map(partidos.set_index("match_id")["torneo"])
    d = pd.DataFrame({"torneo": torneo.astype("string"), "cluster": datos["cluster"], "match_id": datos["match_id"]})
    torneos = sorted(d["torneo"].unique(), key=_orden_torneo)
    filas = []
    for t in torneos:
        sub = d[d["torneo"] == t]
        for c in range(1, k + 1):
            en = sub[sub["cluster"] == c]
            filas.append({"torneo": t, "cluster": c, "n_posesiones": len(en), "n_posesiones_torneo": len(sub),
                          "pct_torneo": len(en) / len(sub), "n_partidos": en["match_id"].nunique()})
    return pd.DataFrame(filas)


def _orden_torneo(nombre):
    m = re.match(r"^(Apertura|Clausura) (\d{4})$", str(nombre))
    if not m:
        return (9999, 9, str(nombre))
    anio, apertura = int(m.group(2)), m.group(1) == "Apertura"
    return (anio if apertura else anio - 1, 0 if apertura else 1, "")


# ---------------------------------------------------------------- consistencia y tendencia

def sd_permutado(x, g, n_grupos, rng, permutaciones):
    # sd entre partidos de la media de x si las posesiones se repartieran al azar entre partidos
    cuentas = np.bincount(g, minlength=n_grupos)
    ok = cuentas > 0
    sds = np.empty(permutaciones)
    for r in range(permutaciones):
        medias = np.bincount(g, weights=rng.permutation(x), minlength=n_grupos)[ok] / cuentas[ok]
        sds[r] = medias.std(ddof=1)
    return sds


def valores_por_partido(metricas, universos, partidos, rng, permutaciones):
    n_part = len(partidos)
    indice = pd.Index(partidos["match_id"])
    valores, nulos_azar = {}, {}
    for m in metricas:
        if m.origen == "partidos":
            valores[m.metrica] = a_float(partidos[m.columna])
            nulos_azar[m.metrica] = None
            continue
        df = universos[m.universo]
        if m.columna not in df.columns:
            raise ErrorPatrones(f"{m.metrica}: no existe la columna {m.columna} para el universo {m.universo}")
        x = a_float(df[m.columna])
        g = indice.get_indexer(df["match_id"])
        if (g < 0).any():
            raise ErrorPatrones(f"{m.metrica}: {int((g < 0).sum())} posesiones con match_id fuera de analitica_partidos")
        ok = ~np.isnan(x)
        x, g = x[ok], g[ok]
        n = np.bincount(g, minlength=n_part)
        suma = np.bincount(g, weights=x, minlength=n_part)
        valores[m.metrica] = np.where(n >= MIN_POSESIONES_PARTIDO, suma / np.maximum(n, 1), np.nan)
        suficiente = n[g] >= MIN_POSESIONES_PARTIDO
        nulos_azar[m.metrica] = sd_permutado(x[suficiente], g[suficiente], n_part, rng, permutaciones)
    return valores, nulos_azar


def consistencia(metricas, valores, nulos_azar, permutaciones):
    filas = []
    for m in metricas:
        v = valores[m.metrica]
        v = v[~np.isnan(v)]
        fila = {"metrica": m.metrica, "etiqueta": m.etiqueta, "unidad": m.unidad,
                "nivel_dato": "posesion" if m.origen == "posesiones" else "partido", "n_partidos": len(v)}
        if len(v) < 3:
            fila.update(lectura="sin dato")
            filas.append(fila)
            continue
        sd = float(v.std(ddof=1))
        media = float(v.mean())
        q1, q3 = np.quantile(v, [0.25, 0.75])
        fila.update(media=media, mediana=float(np.median(v)), sd=sd,
                    cv=sd / abs(media) if abs(media) > 1e-9 else np.nan, iqr=float(q3 - q1),
                    p10=float(np.quantile(v, 0.1)), p90=float(np.quantile(v, 0.9)))
        azar = nulos_azar[m.metrica]
        if azar is None:
            fila["lectura"] = "sin referencia de azar"
        else:
            sd_azar = float(azar.mean())
            razon = sd / sd_azar if sd_azar > 0 else np.nan
            p = (1 + int((azar >= sd).sum())) / (1 + permutaciones)
            # parte real: fraccion de la varianza entre partidos que el azar de las posesiones no explica
            parte = max(0.0, 1 - 1 / razon ** 2) if razon > 0 else (0.0 if not np.isnan(razon) else np.nan)
            fila.update(sd_azar=sd_azar, razon_variacion=razon, parte_real=parte, p_permutacion=p)
            if np.isnan(razon):
                fila["lectura"] = "sin dato"
            elif p > ALFA or parte < PARTE_REAL_MODERADA:
                fila["lectura"] = "estable"
            elif parte < PARTE_REAL_ALTA:
                fila["lectura"] = "moderada"
            else:
                fila["lectura"] = "alta"
        filas.append(fila)
    return pd.DataFrame(filas)


def _pendiente(x, y, cod, n_cod):
    # pendiente con efectos fijos de torneo: x e y centrados por torneo
    n = np.bincount(cod, minlength=n_cod)
    xm = np.bincount(cod, weights=x, minlength=n_cod) / np.maximum(n, 1)
    ym = np.bincount(cod, weights=y, minlength=n_cod) / np.maximum(n, 1)
    xc, yc = x - xm[cod], y - ym[cod]
    den = float((xc ** 2).sum())
    return (float((xc * yc).sum()) / den if den > 0 else np.nan), xc, yc


def lectura_tendencia(ic_inf, ic_sup, efecto):
    if np.isnan(ic_inf) or np.isnan(ic_sup) or np.isnan(efecto):
        return "sin dato"
    excluye = ic_inf > 0 or ic_sup < 0
    if excluye and abs(efecto) >= EFECTO_MIN:
        return "tendencia"
    if excluye:
        return "tendencia pequena"
    return "indicio" if abs(efecto) >= EFECTO_MIN else "sin tendencia clara"


def tendencia(metricas, valores, partidos, rng, replicas):
    reg = (partidos["stage"] == "regular").to_numpy() & partidos["match_week"].notna().to_numpy()
    semana = a_float(partidos["match_week"])
    torneo = partidos["torneo"].astype("string").to_numpy()
    span_por_torneo = [np.ptp(semana[reg & (torneo == t)]) for t in np.unique(torneo[reg])]
    span = float(np.median(span_por_torneo))
    filas = []
    for m in metricas:
        y_all = valores[m.metrica]
        ok = reg & ~np.isnan(y_all)
        x, y = semana[ok], y_all[ok]
        nombres, cod = np.unique(torneo[ok], return_inverse=True)
        fila = {"metrica": m.metrica, "etiqueta": m.etiqueta, "unidad": m.unidad, "n_partidos": int(ok.sum()),
                "n_torneos": len(nombres), "span_jornadas": span}
        if ok.sum() < 10 or len(nombres) < 1:
            fila["lectura"] = "sin dato"
            filas.append(fila)
            continue
        pend, xc, yc = _pendiente(x, y, cod, len(nombres))
        sd = float(yc.std(ddof=1))
        idx = rng.integers(0, len(x), (replicas, len(x)))
        boot = np.array([_pendiente(x[i], y[i], cod[i], len(nombres))[0] for i in idx])
        inf, sup = np.nanquantile(boot, [ALFA / 2, 1 - ALFA / 2])
        efecto = pend * span / sd if sd > 0 else np.nan
        e_inf, e_sup = (inf * span / sd, sup * span / sd) if sd > 0 else (np.nan, np.nan)
        rho = float(pd.Series(xc).rank().corr(pd.Series(yc).rank()))
        fila.update(pendiente=pend, pend_ic_inf=float(inf), pend_ic_sup=float(sup), cambio_torneo=pend * span,
                    efecto=efecto, efecto_ic_inf=e_inf, efecto_ic_sup=e_sup, rho_spearman=rho,
                    lectura=lectura_tendencia(e_inf, e_sup, efecto))
        filas.append(fila)
    return pd.DataFrame(filas)


# ---------------------------------------------------------------- tipos de las salidas

def tipar(df, tipos, nombre):
    faltan = [c for c in tipos if c not in df.columns]
    sobran = [c for c in df.columns if c not in tipos]
    if faltan or sobran:
        raise ErrorPatrones(f"{nombre}: columnas que faltan {faltan} y que sobran {sobran}")
    try:
        return df[list(tipos)].astype(tipos)
    except (TypeError, ValueError) as e:
        raise ErrorPatrones(f"{nombre}: no se pudieron fijar los tipos: {type(e).__name__}: {e}") from e


def tipos_perfil():
    t = {"cluster": "Int64", "n_posesiones": "Int64", "pct_posesiones": "float64", "n_partidos": "Int64"}
    for nombre, *_ in FEATURES:
        t[f"{nombre}_mediana"] = "float64"
        t[f"{nombre}_media"] = "float64"
    t.update(pct_tercio_final="float64", con_tiro="float64", xg_media="float64", pases_progresivos_media="float64",
             pases_rompe_lineas_media="float64", obv_neto_media="float64", etiqueta_sugerida="string")
    return t


TIPOS_POSESIONES = {"match_id": "Int64", "possession": "Int64", "cluster": "Int64", "n_pases": "float64",
                    "duracion": "float64", "directness": "float64", "x_inicio": "float64", "x_max": "float64"}
TIPOS_TORNEO = {"torneo": "string", "cluster": "Int64", "n_posesiones": "Int64", "n_posesiones_torneo": "Int64",
                "pct_torneo": "float64", "n_partidos": "Int64"}
TIPOS_K = {"k": "Int64", "inercia": "float64", "silueta": "float64", "pct_cluster_min": "float64",
           "elegido": "boolean", "ari_media": "float64", "ari_p05": "float64", "ari_p95": "float64",
           "n_replicas_ari": "Int64"}
TIPOS_CONSISTENCIA = {"metrica": "string", "etiqueta": "string", "unidad": "string", "nivel_dato": "string",
                      "n_partidos": "Int64", "media": "float64", "mediana": "float64", "sd": "float64",
                      "cv": "float64", "iqr": "float64", "p10": "float64", "p90": "float64", "sd_azar": "float64",
                      "razon_variacion": "float64", "parte_real": "float64", "p_permutacion": "float64",
                      "lectura": "string"}
TIPOS_TENDENCIA = {"metrica": "string", "etiqueta": "string", "unidad": "string", "n_partidos": "Int64",
                   "n_torneos": "Int64", "span_jornadas": "float64", "pendiente": "float64",
                   "pend_ic_inf": "float64", "pend_ic_sup": "float64", "cambio_torneo": "float64",
                   "efecto": "float64", "efecto_ic_inf": "float64", "efecto_ic_sup": "float64",
                   "rho_spearman": "float64", "lectura": "string"}


def completar(df, tipos):
    # una fila "sin dato" no trae todas las columnas: las que faltan quedan nulas
    for c in tipos:
        if c not in df.columns:
            df[c] = np.nan
    return df


# ---------------------------------------------------------------- calculo y validacion

def calcular(args):
    s_k, s_est, s_perm, s_tend = (np.random.default_rng(s) for s in np.random.SeedSequence(args.semilla).spawn(4))
    pos, par, ev = cargar()
    _ok(f"{len(pos)} posesiones de {par['match_id'].nunique()} partidos; {len(ev)} eventos leidos")
    eq = posesiones_america(pos, ev)
    validas = eq[eq["is_valid_possession"]]
    completas = validas[[f[1] for f in FEATURES]].notna().all(axis=1)
    datos = validas[completas].reset_index(drop=True)
    print(f"Posesiones del America sin administrativas: {len(eq)}; validas: {len(validas)}; "
          f"con las {len(FEATURES)} variables: {len(datos)}")
    if len(validas) - len(datos):
        _aviso(f"{len(validas) - len(datos)} posesiones validas quedan fuera del clustering por tener alguna "
               f"variable nula (directness o x_max)")
    if len(datos) < 200:
        raise ErrorPatrones(f"solo {len(datos)} posesiones para el clustering; revisa los filtros")

    cluster, k, tabla_k, aris = agrupar(datos, args, s_k, s_est)
    datos["cluster"] = cluster
    for c in range(1, k + 1):
        datos[f"es_cluster_{c}"] = datos["cluster"] == c
    print("\nSeleccion de k (silueta sobre muestra fija; mas alto = clusters mas separados):")
    print(tabla_k[["k", "inercia", "silueta", "pct_cluster_min", "elegido"]].to_string(index=False,
                                                                                         float_format="{:.3f}".format))
    silueta_k = float(tabla_k.loc[tabla_k["elegido"], "silueta"].iloc[0])
    _ok(f"k = {k} (silueta {silueta_k:.3f}); estabilidad bootstrap por partidos: ARI medio {aris.mean():.3f} "
        f"(p5 {np.quantile(aris, 0.05):.3f}, p95 {np.quantile(aris, 0.95):.3f}, {len(aris)} replicas)")
    if silueta_k < SILUETA_DEBIL:
        _aviso(f"silueta {silueta_k:.3f} < {SILUETA_DEBIL}: los grupos no estan bien separados; leerlos como tipos "
               f"descriptivos y no como categorias naturales")
    if aris.mean() < ARI_MODERADO:
        _aviso(f"ARI medio {aris.mean():.3f} < {ARI_MODERADO}: los clusters cambian mucho al remuestrear partidos")
    elif aris.mean() < ARI_BUENO:
        _aviso(f"ARI medio {aris.mean():.3f} < {ARI_BUENO}: estabilidad moderada; decirlo en el reporte")

    perfil = perfil_clusters(datos, k)
    por_torneo = clusters_por_torneo(datos, par, k)
    if int(perfil["n_posesiones"].sum()) != len(datos):
        raise ErrorPatrones("los tamanos de los clusters no suman las posesiones clusterizadas")
    print("\nPerfil de los clusters (medianas; n = posesiones):")
    cols = ["cluster", "n_posesiones", "pct_posesiones", "pases_mediana", "duracion_mediana", "directness_mediana",
            "x_inicio_mediana", "x_max_mediana", "pct_tercio_final", "con_tiro", "xg_media", "etiqueta_sugerida"]
    print(perfil[cols].to_string(index=False, float_format="{:.2f}".format))

    metricas = METRICAS_BASE + [
        MetricaPartido(f"cluster_{c}", f"Posesiones del cluster {c}", "proporcion", "posesiones",
                       f"es_cluster_{c}", "clusterizadas") for c in range(1, k + 1)]
    universos = {"todas": eq, "validas": validas, "clusterizadas": datos}
    valores, nulos_azar = valores_por_partido(metricas, universos, par, s_perm, args.permutaciones)

    cons = consistencia(metricas, valores, nulos_azar, args.permutaciones)
    tend = tendencia(metricas, valores, par, s_tend, args.replicas)

    por_partido = par[["match_id", "torneo", "match_week", "stage"]].copy()
    por_partido["n_posesiones_validas"] = por_partido["match_id"].map(validas.groupby("match_id").size()).fillna(0)
    por_partido["n_posesiones_cluster"] = por_partido["match_id"].map(datos.groupby("match_id").size()).fillna(0)
    for m in metricas:
        por_partido[m.metrica] = valores[m.metrica]
    bajos = int((por_partido["n_posesiones_cluster"] < MIN_POSESIONES_PARTIDO).sum())
    if bajos:
        _aviso(f"{bajos} partidos con menos de {MIN_POSESIONES_PARTIDO} posesiones clusterizadas")
    cols_cluster = [f"cluster_{c}" for c in range(1, k + 1)]
    suma = por_partido[cols_cluster].sum(axis=1)
    con_dato = por_partido["n_posesiones_cluster"] >= MIN_POSESIONES_PARTIDO
    if not np.allclose(suma[con_dato], 1.0):
        raise ErrorPatrones("el peso de los clusters por partido no suma 1")
    _ok("el peso de los clusters suma 1 en cada partido")

    salida_pos = datos[["match_id", "possession", "cluster", "n_pases", "duracion", "directness", "x_inicio",
                        "x_max"]].copy()
    tipos_partidos = {"match_id": "Int64", "torneo": "string", "match_week": "Int64", "stage": "string",
                      "n_posesiones_validas": "Int64", "n_posesiones_cluster": "Int64",
                      **{m.metrica: "float64" for m in metricas}}
    tablas = {
        SAL_POSESIONES: tipar(salida_pos, TIPOS_POSESIONES, SAL_POSESIONES),
        SAL_PERFIL: tipar(perfil, tipos_perfil(), SAL_PERFIL),
        SAL_TORNEO: tipar(por_torneo, TIPOS_TORNEO, SAL_TORNEO),
        SAL_K: tipar(tabla_k, TIPOS_K, SAL_K),
        SAL_PARTIDOS: tipar(por_partido, tipos_partidos, SAL_PARTIDOS),
        SAL_CONSISTENCIA: tipar(completar(cons, TIPOS_CONSISTENCIA), TIPOS_CONSISTENCIA, SAL_CONSISTENCIA),
        SAL_TENDENCIA: tipar(completar(tend, TIPOS_TENDENCIA), TIPOS_TENDENCIA, SAL_TENDENCIA),
    }
    validar(tablas, par, k, metricas)
    resumen(tablas, k, args)
    return tablas


def validar(tablas, par, k, metricas):
    pos = tablas[SAL_POSESIONES]
    if pos.duplicated(["match_id", "possession"]).any() or pos.isna().any().any():
        raise ErrorPatrones(f"{SAL_POSESIONES}: llave repetida o valores nulos")
    if set(pos["cluster"].unique()) != set(range(1, k + 1)):
        raise ErrorPatrones(f"{SAL_POSESIONES}: los clusters no son exactamente 1 a {k}")
    p = tablas[SAL_PARTIDOS]
    if len(p) != N_PARTIDOS or p["match_id"].duplicated().any() or set(p["match_id"]) != set(par["match_id"]):
        raise ErrorPatrones(f"{SAL_PARTIDOS}: no trae exactamente los {N_PARTIDOS} partidos una vez")
    for nombre in (SAL_CONSISTENCIA, SAL_TENDENCIA):
        t = tablas[nombre]
        if len(t) != len(metricas) or t["metrica"].duplicated().any():
            raise ErrorPatrones(f"{nombre}: no trae una fila por metrica ({len(metricas)})")
    if not set(tablas[SAL_CONSISTENCIA]["lectura"]) <= set(LECTURAS_CONSISTENCIA):
        raise ErrorPatrones(f"{SAL_CONSISTENCIA}: lectura fuera de {LECTURAS_CONSISTENCIA}")
    if not set(tablas[SAL_TENDENCIA]["lectura"]) <= set(LECTURAS_TENDENCIA):
        raise ErrorPatrones(f"{SAL_TENDENCIA}: lectura fuera de {LECTURAS_TENDENCIA}")
    _ok("llaves, partidos, clusters y lecturas validados")


def resumen(tablas, k, args):
    cons, tend = tablas[SAL_CONSISTENCIA], tablas[SAL_TENDENCIA]
    print("\nConsistencia entre partidos (parte_real = 1 - (sd_azar / sd)^2: lo que NO explica el azar de las posesiones;")
    print("lectura: alta >= 50%, moderada 25-50%, estable < 25% o p > 0.05):")
    cols = ["metrica", "n_partidos", "media", "sd", "cv", "razon_variacion", "parte_real", "p_permutacion",
            "lectura"]
    print(cons[cols].to_string(index=False, float_format="{:.3f}".format))
    print("\nTendencia por jornada (fase regular, efectos fijos de torneo; efecto en sd por torneo completo):")
    cols = ["metrica", "n_partidos", "pendiente", "pend_ic_inf", "pend_ic_sup", "efecto", "rho_spearman", "lectura"]
    print(tend[cols].to_string(index=False, float_format="{:.3f}".format))
    n_metricas = int(tend["lectura"].isin(["tendencia", "tendencia pequena"]).sum())
    esperado = ALFA * int((tend["lectura"] != "sin dato").sum())
    if n_metricas:
        _aviso(f"{n_metricas} metricas con IC que excluye 0; con {len(tend)} metricas se esperan ~{esperado:.1f} "
               f"solo por azar. Hablar de 'indicio' salvo que el efecto sea claro")
    ncons = cons["lectura"].value_counts()
    print("\nLectura global de consistencia: " + ", ".join(f"{n} {l}" for l, n in ncons.items()))


# ---------------------------------------------------------------- escritura

def escribir(tablas):
    DIR_SALIDA.mkdir(parents=True, exist_ok=True)
    for viejo in DIR_SALIDA.glob(".tmp_04_patrones_*"):
        shutil.rmtree(viejo, ignore_errors=True)
    tmp = Path(tempfile.mkdtemp(prefix=".tmp_04_patrones_", dir=DIR_SALIDA))
    try:
        for nombre, df in tablas.items():
            df.to_parquet(tmp / nombre, index=False)
    except ERRORES_ESCRITURA as e:
        raise ErrorPatrones(f"no se pudo escribir: {type(e).__name__}: {e}; no se reemplazo nada "
                            f"(carpeta temporal: {tmp})") from e
    for nombre in tablas:
        destino = DIR_SALIDA / nombre
        if destino.exists():
            try:
                os.close(os.open(destino, os.O_RDWR))
            except OSError as e:
                raise ErrorPatrones(f"{destino} esta bloqueado ({e}); cierralo y vuelve a correr. "
                                    f"No se reemplazo nada (carpeta temporal: {tmp})") from e
    hechos = []
    try:
        for nombre in tablas:
            os.replace(tmp / nombre, DIR_SALIDA / nombre)
            hechos.append(nombre)
    except OSError as e:
        raise ErrorPatrones(f"fallo al reemplazar {nombre}: {e}. Ya reemplazados: {hechos}; los demas siguen en "
                            f"{tmp}") from e
    shutil.rmtree(tmp, ignore_errors=True)
    for nombre, df in tablas.items():
        _ok(f"{nombre}: {len(df)} filas, {len(df.columns)} columnas")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sin-escribir", action="store_true", help="calcula y valida pero no escribe")
    parser.add_argument("--k", type=int, default=None, help="fuerza el numero de clusters")
    parser.add_argument("--semilla", type=int, default=SEMILLA)
    parser.add_argument("--replicas", type=int, default=REPLICAS, help="replicas bootstrap de la tendencia")
    parser.add_argument("--permutaciones", type=int, default=PERMUTACIONES, help="permutaciones de la consistencia")
    parser.add_argument("--replicas-estabilidad", type=int, default=REPLICAS_ESTABILIDAD,
                        help="replicas bootstrap por partidos de la estabilidad de los clusters")
    args = parser.parse_args(argv)
    if args.k is not None and args.k < 2:
        parser.error("--k debe ser al menos 2")
    if min(args.replicas, args.permutaciones, args.replicas_estabilidad) < 1:
        parser.error("las replicas y permutaciones deben ser al menos 1")
    t0 = time.time()
    try:
        tablas = calcular(args)
        if args.sin_escribir:
            print("\n--sin-escribir: no se escribio nada en data/processed/")
        else:
            escribir(tablas)
    except ErrorPatrones as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"\nListo en {time.time() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
