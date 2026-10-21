"""Metricas por contexto (fase 4, tarea 14.6): compara cada metrica entre los niveles de seis contextos.

Uso:
    python scripts/04_contexto.py                 # calcula, valida y escribe en data/processed/
    python scripts/04_contexto.py --sin-escribir  # calcula y valida, sin escribir
    python scripts/04_contexto.py --replicas 200  # menos replicas bootstrap, para probar rapido

Lee las tablas de contexto de data/processed/ (salida de 03_contexto.py) y escribe dos tablas (ver SALIDA_*):
- celdas_contexto.parquet: una fila por (metrica, contexto, nivel) con el valor, su IC del 95%, n_obs,
  n_partidos e inestable.
- comparaciones_contexto.parquet: una fila por (metrica, contexto, nivel, ajuste), nivel contra la referencia
  del contexto, con la diferencia, el tamano de efecto (g de Hedges, h de Cohen o dif/MAD), sus IC y la lectura.

Contextos: score_state, is_home, rival_strength_tercil, minute_bin, stage y numerical_state. Las metricas por
partido solo se cruzan con is_home, rival_strength_tercil y stage. Los IC salen de un bootstrap que remuestrea
partidos completos con una sola matriz de multiplicidades para todas las metricas. score_state trae ademas el
ajuste mitad_x_tercil (diferencia dentro de mitad del partido x tercil del rival, promediada por el n del nivel).

Para agregar una metrica se anade una entrada a METRICAS, sin tocar el resto del codigo. Las reglas y los
criterios de aceptacion estan en docs/spec_04_contexto.md.

Codigos de salida: 0 si todo paso y se escribio (o no se pidio escribir); 1 si fallo una validacion dura, falta
un dato o fallo la escritura. Si falla una validacion no se escribe nada.
"""
import argparse
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pandas as pd
import pyarrow as pa

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
# nombres de las salidas: aprobado por el equipo el 20-oct; ver docs/spec_04_contexto.md
SALIDA_CELDAS = "celdas_contexto.parquet"
SALIDA_COMPARACIONES = "comparaciones_contexto.parquet"
PREFIJO_TMP = ".tmp_04_contexto_"  # distinto de .tmp_contexto_ de 03, que borra sus temporales viejas

POSESIONES = "data/processed/contexto_posesiones.parquet"
PARTIDOS = "data/processed/contexto_partidos.parquet"
EVENTOS = "data/processed/contexto_eventos.parquet"

# parametros de la estadistica
REPLICAS = 2000
SEMILLA = 20261020
MIN_PARTIDOS = 10  # celda inestable con menos partidos
MIN_OBS = 100  # celda de posesion o evento inestable con menos filas
EFECTO_MIN = 0.2  # |efecto| minimo para leer diferencia o indicio
MIN_PARTIDOS_IC = 2  # con menos partidos la celda no varia al remuestrear partidos: IC nulo
MIN_REPLICAS_VIVAS = 0.9  # fraccion minima de replicas no vacias para dar IC
PERCENTILES = (2.5, 97.5)
TOL_IC = 1e-12  # holgura numerica al revisar si el IC contiene el valor puntual
ESCALA_MAD = 1.4826  # MAD a desviacion estandar bajo normalidad
MAX_ELEMENTOS_MEDIANA = 250_000  # replicas x filas por bloque en la mediana ponderada; 1 MB en int32 cabe en cache
PATRON_ID = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class Metrica:
    # Una metrica de evento debe traer es_eq en su propia tabla: contexto_eventos no lo tiene.
    metrica: str  # id: minusculas, digitos y guion bajo
    etiqueta: str  # nombre para graficas
    unidad: str  # lista abierta: s, pases, proporcion, xG, yardas, puntos, goles u otra
    ruta: str  # parquet relativo a la raiz del repo
    llave: tuple  # (match_id, possession), (match_id, index) o (match_id,)
    columna: str  # columna numerica o booleana con el valor
    agregacion: str  # media, mediana, proporcion o ponderada
    filtro: dict = field(default_factory=dict)  # columna = valor (o lista de valores), tras pegar el contexto
    peso: str | None = None  # solo para ponderada

    def __post_init__(self):
        # filtro y llave inmutables; las listas de valores pasan a tuple para usarlas con isin
        filtro = {c: tuple(v) if isinstance(v, (list, tuple, set)) else v for c, v in dict(self.filtro).items()}
        object.__setattr__(self, "filtro", MappingProxyType(filtro))
        object.__setattr__(self, "llave", tuple(self.llave))


_POS = ("match_id", "possession")
_PAR = ("match_id",)
_EQ, _RIVAL = {"es_eq": True}, {"es_eq": False}

# registro de metricas: para agregar una basta una entrada nueva
METRICAS = [
    Metrica("duracion", "Duración de la posesión", "s", POSESIONES, _POS, "duracion", "mediana", _EQ),
    Metrica("pases", "Pases por posesión", "pases", POSESIONES, _POS, "n_pases", "media", _EQ),
    Metrica("con_tiro", "Posesiones con tiro", "proporcion", POSESIONES, _POS, "con_tiro", "proporcion", _EQ),
    Metrica("xg", "xG por posesión", "xG", POSESIONES, _POS, "xg", "media", _EQ),
    Metrica("valida", "Posesiones válidas", "proporcion", POSESIONES, _POS, "is_valid_possession", "proporcion",
            _EQ),
    Metrica("altura_inicio", "Altura de inicio de la posesión", "yardas", POSESIONES, _POS, "x_inicio", "media",
            _EQ),
    Metrica("inicio_ultimo_tercio", "Posesiones que empiezan en el último tercio", "proporcion", POSESIONES, _POS,
            "inicio_ultimo_tercio", "proporcion", _EQ),
    Metrica("balon_parado", "Posesiones a balón parado", "proporcion", POSESIONES, _POS, "es_balon_parado",
            "proporcion", _EQ),
    Metrica("tiempo_con_balon", "Parte del tiempo de posesión del América", "proporcion", POSESIONES, _POS,
            "es_eq", "ponderada", peso="duracion"),
    Metrica("xg_rival", "xG del rival por posesión", "xG", POSESIONES, _POS, "xg", "media", _RIVAL),
    Metrica("con_tiro_rival", "Posesiones del rival con tiro", "proporcion", POSESIONES, _POS, "con_tiro",
            "proporcion", _RIVAL),
    Metrica("puntos", "Puntos por partido", "puntos", PARTIDOS, _PAR, "puntos", "media"),
    Metrica("goles_favor", "Goles a favor por partido", "goles", PARTIDOS, _PAR, "goles_eq", "media"),
    Metrica("goles_contra", "Goles en contra por partido", "goles", PARTIDOS, _PAR, "goles_rival", "media"),
    Metrica("tiempo_ganando", "Parte del partido ganando", "proporcion", PARTIDOS, _PAR, "tiempo_ganando", "media"),
    Metrica("tiempo_perdiendo", "Parte del partido perdiendo", "proporcion", PARTIDOS, _PAR, "tiempo_perdiendo",
            "media"),
]

NIVEL_DATO = {("match_id", "possession"): "posesion", ("match_id", "index"): "evento", ("match_id",): "partido"}
TABLA_CONTEXTO = {"posesion": POSESIONES, "evento": EVENTOS, "partido": PARTIDOS}
AGREGACIONES = {"media", "mediana", "proporcion", "ponderada"}
TIPO_EFECTO = {"media": "g de Hedges", "proporcion": "h de Cohen", "ponderada": "h de Cohen", "mediana": "dif/MAD"}

# niveles de cada contexto en orden, la referencia primero
NIVELES = {
    "score_state": ["empatando", "perdiendo", "ganando"],
    "is_home": ["visitante", "local"],
    "rival_strength_tercil": ["débil", "medio", "fuerte"],
    "minute_bin": ["0-15", "15-30", "30-45", "45+", "45-60", "60-75", "75-90", "90+", "ET"],
    "stage": ["regular", "fase final"],
    "numerical_state": ["igualdad", "inferioridad", "superioridad"],
}
REFERENCIA = {c: niveles[0] for c, niveles in NIVELES.items()}
CONTEXTOS_PARTIDO = ["is_home", "rival_strength_tercil", "stage"]  # los que no cambian dentro del partido
CONTEXTOS_POR_NIVEL = {"posesion": list(NIVELES), "evento": list(NIVELES), "partido": CONTEXTOS_PARTIDO}

# ajuste del marcador: mitad del partido x tercil del rival
CONTEXTO_AJUSTADO = "score_state"
PRIMER_TIEMPO = {"0-15", "15-30", "30-45", "45+"}  # el resto, incluido ET, es segundo tiempo
N_ESTRATOS = 2 * len(NIVELES["rival_strength_tercil"])
NOMBRES_ESTRATOS = [f"{mitad}-{t}" for mitad in ("1T", "2T") for t in NIVELES["rival_strength_tercil"]]

# filas administrativas que se quitan siempre: la de posesion viene del contexto, la de evento de la tabla propia
ADMIN_POSESION = "es_administrativa"
ADMIN_EVENTO = "es_administrativo"

LECTURAS = ["diferencia", "diferencia pequena", "indicio", "sin diferencia clara"]

COLUMNAS_CELDAS = {
    "metrica": "string", "etiqueta_metrica": "string", "unidad": "string", "agregacion": "string",
    "nivel_dato": "string", "contexto": "string", "nivel": "string", "es_referencia": "boolean",
    "valor": "float64", "ic_inf": "float64", "ic_sup": "float64", "n_obs": "Int64", "n_partidos": "Int64",
    "inestable": "boolean",
}
COLUMNAS_COMPARACIONES = {
    "metrica": "string", "contexto": "string", "nivel": "string", "referencia": "string", "ajuste": "string",
    "diferencia": "float64", "dif_ic_inf": "float64", "dif_ic_sup": "float64", "tipo_efecto": "string",
    "efecto": "float64", "efecto_ic_inf": "float64", "efecto_ic_sup": "float64", "n_obs_nivel": "Int64",
    "n_obs_ref": "Int64", "n_partidos_nivel": "Int64", "n_partidos_ref": "Int64", "inestable": "boolean",
    "lectura": "string",
}
LLAVE_CELDAS = ["metrica", "contexto", "nivel"]
LLAVE_COMPARACIONES = ["metrica", "contexto", "nivel", "ajuste"]

ERRORES_ESCRITURA = (OSError, ValueError, TypeError, pa.lib.ArrowException)


class ErrorContexto(Exception):
    pass


def _ok(msg):
    print(f"[OK] {msg}")


def _aviso(msg):
    print(f"AVISO: {msg}")


# ---------------------------------------------------------------- carga

def derivar(ruta, df):
    # Columnas derivadas de las tablas de la fase 3, para que cada metrica apunte a un nombre de columna.
    df = df.copy()
    if ruta == POSESIONES:
        df["con_tiro"] = df["n_tiros"] > 0
        df["inicio_ultimo_tercio"] = df["third_inicio"].astype("string") == "final_third"
    elif ruta == PARTIDOS:
        ge, gr = df["goles_eq"], df["goles_rival"]
        df["puntos"] = (3 * (ge > gr).astype("Int64") + (ge == gr).astype("Int64")).astype("Float64")
        total = df["minutos_ganando"] + df["minutos_empatando"] + df["minutos_perdiendo"]
        total = total.where(total > 0)
        df["tiempo_ganando"] = df["minutos_ganando"] / total
        df["tiempo_perdiendo"] = df["minutos_perdiendo"] / total
    return df


class Tablas:
    # Lee cada parquet una sola vez (contexto_eventos solo si alguna metrica lo pide) y arma el contexto por nivel.
    def __init__(self):
        self._tablas, self._contextos = {}, {}

    def tabla(self, ruta):
        if ruta not in self._tablas:
            archivo = ROOT / ruta
            if not archivo.exists():
                raise ErrorContexto(f"no existe {ruta}; corre antes 03_contexto.py")
            try:
                self._tablas[ruta] = derivar(ruta, pd.read_parquet(archivo))
            except (OSError, ValueError, KeyError) as e:
                raise ErrorContexto(f"no se pudo leer {ruta}: {type(e).__name__}: {e}") from e
        return self._tablas[ruta]

    def contexto(self, nivel_dato):
        if nivel_dato not in self._contextos:
            ctx = self.tabla(TABLA_CONTEXTO[nivel_dato])
            if nivel_dato == "posesion":
                ctx = ctx.merge(self.tabla(PARTIDOS)[["match_id", "is_home"]], how="left", on="match_id",
                                validate="many_to_one")
            self._contextos[nivel_dato] = ctx
        return self._contextos[nivel_dato]


def validar_registro(metricas):
    fallas = []
    ids = [m.metrica for m in metricas]
    if len(ids) != len(set(ids)):
        fallas.append(f"METRICAS: ids repetidos {sorted({i for i in ids if ids.count(i) > 1})}")
    for m in metricas:
        if not isinstance(m.metrica, str) or not PATRON_ID.match(m.metrica):
            fallas.append(f"{m.metrica!r}: el id solo lleva minusculas, digitos y guion bajo")
        if not isinstance(m.etiqueta, str) or not m.etiqueta.strip():
            fallas.append(f"{m.metrica}: etiqueta vacia")
        nivel_dato = NIVEL_DATO.get(m.llave)
        if nivel_dato is None:
            fallas.append(f"{m.metrica}: llave {m.llave} no es de posesion, evento ni partido")
        elif m.ruta in TABLA_CONTEXTO.values() and m.ruta != TABLA_CONTEXTO[nivel_dato]:
            fallas.append(f"{m.metrica}: {m.ruta} es la tabla de contexto de otro nivel, no de {nivel_dato}")
        if m.agregacion not in AGREGACIONES:
            fallas.append(f"{m.metrica}: agregacion {m.agregacion!r} no es una de {sorted(AGREGACIONES)}")
        if (m.agregacion == "ponderada") != (m.peso is not None):
            fallas.append(f"{m.metrica}: peso solo y siempre con agregacion ponderada")
    return fallas


@dataclass
class Datos:
    # Filas usadas por una metrica: valor x, peso w, indice de partido g y el contexto crudo de cada fila.
    x: np.ndarray
    w: np.ndarray
    g: np.ndarray
    contexto: pd.DataFrame
    peso_cero: int  # filas quitadas por peso 0 (solo ponderada)


def _es_numerica(serie):
    return pd.api.types.is_bool_dtype(serie) or pd.api.types.is_numeric_dtype(serie)


def _condicion(serie, valor):
    # Filtro columna = valor, o columna en la lista de valores; los nulos no pasan.
    cond = serie.isin(valor) if isinstance(valor, tuple) else serie == valor
    return cond.astype("boolean").fillna(False)


def preparar(m, tablas, partidos_idx):
    # Pega el contexto por la llave, quita administrativas, aplica el filtro y los nulos de la metrica.
    nivel_dato = NIVEL_DATO[m.llave]
    llave = list(m.llave)
    ctx = tablas.contexto(nivel_dato)
    tabla = ctx if m.ruta == TABLA_CONTEXTO[nivel_dato] else tablas.tabla(m.ruta)
    propias = [c for c in (m.columna, m.peso) if c is not None]
    faltan = [c for c in llave + propias if c not in tabla.columns]
    if faltan:
        return None, [f"{m.metrica}: {faltan} no existe en {m.ruta}"]
    no_numericas = [f"{c} ({tabla[c].dtype})" for c in propias if not _es_numerica(tabla[c])]
    if no_numericas:
        return None, [f"{m.metrica}: {no_numericas} no es numerica ni booleana en {m.ruta}"]
    repetidas = int(tabla.duplicated(llave).sum())
    if repetidas:
        return None, [f"{m.metrica}: {repetidas} filas con la llave {llave} repetida en {m.ruta}"]
    contextos = CONTEXTOS_POR_NIVEL[nivel_dato]
    extra = [ADMIN_POSESION] if nivel_dato == "posesion" else []
    if tabla is ctx:
        df = ctx
    else:
        de_tabla = [c for c in dict.fromkeys(propias + list(m.filtro) + [ADMIN_EVENTO])
                    if c in tabla.columns and c not in llave + contextos + extra]
        de_ctx = [c for c in dict.fromkeys(list(m.filtro) + contextos + extra)
                  if c not in de_tabla and c in ctx.columns and c not in llave]
        try:
            df = tabla[llave + de_tabla].merge(ctx[llave + de_ctx], how="left", on=llave, validate="one_to_one",
                                               indicator=True)
        except ValueError as e:  # incluye MergeError y llaves de tipos incompatibles
            return None, [f"{m.metrica}: no se pudo pegar el contexto por {llave}: {type(e).__name__}: {e}"]
        sin_contexto = (df["_merge"] == "left_only").to_numpy()
        if sin_contexto.any():
            ejemplo = df.loc[sin_contexto, llave].head(3).to_dict("records")
            return None, [f"{m.metrica}: {int(sin_contexto.sum())} filas de {m.ruta} sin su llave en "
                          f"{TABLA_CONTEXTO[nivel_dato]}, por ejemplo {ejemplo}"]
        df = df.drop(columns="_merge")
    faltan = [c for c in list(m.filtro) + contextos + extra if c not in df.columns]
    if faltan:
        return None, [f"{m.metrica}: {faltan} no estan en {m.ruta} ni en su contexto"]
    # antes de filtrar: un partido ajeno (por ejemplo del grupo de contraste) no debe perderse en silencio
    ajenos = partidos_idx.get_indexer(df["match_id"]) < 0
    if ajenos.any():
        return None, [f"{m.metrica}: {int(ajenos.sum())} filas con match_id nulo o fuera de contexto_partidos"]
    if extra and df[ADMIN_POSESION].isna().any():
        return None, [f"{m.metrica}: {int(df[ADMIN_POSESION].isna().sum())} filas con {ADMIN_POSESION} nula"]

    usar = pd.Series(True, index=df.index)
    if extra:
        usar &= ~df[ADMIN_POSESION].astype("boolean")
    if ADMIN_EVENTO in df.columns:
        usar &= ~_condicion(df[ADMIN_EVENTO], True)
    for col, valor in m.filtro.items():
        usar &= _condicion(df[col], valor)
    usar &= df[m.columna].notna()
    peso_cero = 0
    if m.peso is not None:
        usar &= df[m.peso].notna()
        cero = usar & (df[m.peso] == 0).astype("boolean").fillna(False)
        peso_cero = int(cero.sum())
        usar &= ~cero
    df = df[usar.to_numpy(dtype=bool)]

    fallas = []
    g = partidos_idx.get_indexer(df["match_id"])
    x = df[m.columna].astype("float64").to_numpy()
    w = df[m.peso].astype("float64").to_numpy() if m.peso is not None else np.ones(len(df))
    if m.agregacion in ("proporcion", "ponderada") and ((x < 0) | (x > 1)).any():
        fallas.append(f"{m.metrica}: {m.agregacion} con valores fuera de [0, 1]")
    if (w < 0).any():
        fallas.append(f"{m.metrica}: peso negativo en {int((w < 0).sum())} filas")
    return Datos(x, w, g, df[contextos].reset_index(drop=True), peso_cero), fallas


def niveles_texto(serie, contexto):
    # Nivel en texto: is_home a local/visitante, numerical_state por signo, el resto como viene.
    if contexto == "is_home":
        b = serie.astype("boolean")
        return pd.Series(np.where(b.fillna(False), "local", "visitante"), dtype="string").mask(b.isna().to_numpy())
    if contexto == "numerical_state":
        v = serie.astype("Float64").to_numpy(dtype="float64", na_value=np.nan)
        texto = np.select([v < 0, v == 0, v > 0], ["inferioridad", "igualdad", "superioridad"], default="")
        return pd.Series(texto, dtype="string").mask(np.isnan(v))
    return serie.astype("string").reset_index(drop=True)


def codigos(serie, contexto):
    # Posicion del nivel en NIVELES[contexto]; -1 si es nulo o no esta en la lista.
    texto = niveles_texto(serie, contexto)
    return pd.Categorical(texto, categories=NIVELES[contexto]).codes.astype("int64"), int(texto.notna().sum())


def estratos(contexto):
    # Mitad del partido x tercil del rival (0 a 5); -1 si falta minute_bin o tercil.
    mb = contexto["minute_bin"].astype("string")
    mitad = np.where(mb.isin(PRIMER_TIEMPO).fillna(False).to_numpy(dtype=bool), 0, 1)
    tercil, _ = codigos(contexto["rival_strength_tercil"], "rival_strength_tercil")
    return np.where(mb.notna().to_numpy(dtype=bool) & (tercil >= 0), mitad * len(NIVELES["rival_strength_tercil"])
                    + tercil, -1)


# ---------------------------------------------------------------- bootstrap

def matriz_bootstrap(n_partidos, replicas, semilla):
    # Multiplicidades B x partidos de un remuestreo de partidos con reemplazo.
    rng = np.random.default_rng(semilla)
    idx = rng.integers(0, n_partidos, size=(replicas, n_partidos))
    plano = (idx + np.arange(replicas)[:, None] * n_partidos).ravel()
    return np.bincount(plano, minlength=replicas * n_partidos).reshape(replicas, n_partidos).astype("float64")


def _mediana_ponderada(v, g, mx_int):
    # Mediana de la muestra expandida por las multiplicidades del partido de cada fila (v ordenado), por bloques.
    out = np.full(mx_int.shape[0], np.nan)
    if v.size == 0:
        return out
    bloque = max(1, int(MAX_ELEMENTOS_MEDIANA // v.size))
    for i in range(0, mx_int.shape[0], bloque):
        acum = np.cumsum(mx_int[i:i + bloque][:, g], axis=1, dtype=np.int32)
        total = acum[:, -1]
        bajo = (acum <= ((total - 1) // 2)[:, None]).sum(axis=1)
        alto = (acum <= (total // 2)[:, None]).sum(axis=1)
        med = (v[np.minimum(bajo, v.size - 1)] + v[np.minimum(alto, v.size - 1)]) / 2
        out[i:i + bloque] = np.where(total > 0, med, np.nan)
    return out


@dataclass
class Celdas:
    # Fila 0 = muestra original, filas 1..B = replicas. n, valor y ss (suma de cuadrados) por celda.
    n: np.ndarray
    valor: np.ndarray
    ss: np.ndarray
    n_partidos: np.ndarray
    filas: list  # valores ordenados por celda (solo mediana, para la escala MAD)


def agregar(d, celda, n_celdas, mx, agregacion):
    # Estadisticos suficientes por (partido, celda) multiplicados por las multiplicidades de cada replica.
    G = mx.shape[1]
    ok = celda >= 0
    clave = d.g[ok] * n_celdas + celda[ok]
    x, w = d.x[ok], d.w[ok]

    def suma(pesos=None):
        return np.bincount(clave, weights=pesos, minlength=G * n_celdas).reshape(G, n_celdas).astype("float64")

    n_gc = suma()
    n = mx @ n_gc
    n_partidos = (n_gc > 0).sum(axis=0)
    filas = []
    with np.errstate(divide="ignore", invalid="ignore"):
        if agregacion == "mediana":
            mx_int = mx.astype(np.int32)
            valor = np.full((mx.shape[0], n_celdas), np.nan)
            for c in range(n_celdas):
                sel = celda[ok] == c
                orden = np.argsort(x[sel], kind="stable")
                v, gc = x[sel][orden], d.g[ok][sel][orden]
                valor[:, c] = _mediana_ponderada(v, gc, mx_int)
                filas.append(v)
            ss = np.full_like(valor, np.nan)
        else:
            sw, swx, swx2 = mx @ suma(w), mx @ suma(w * x), mx @ suma(w * x * x)
            valor = np.where(sw > 0, swx / sw, np.nan)
            ss = np.maximum(swx2 - swx * valor, 0.0)
            valor[n == 0] = np.nan
    return Celdas(n, valor, ss, n_partidos, filas)


def _escala_mad(v1, v0):
    # 1.4826 x MAD de la union de las dos celdas, cada fila centrada en la mediana de su celda.
    if v1.size == 0 or v0.size == 0:
        return np.nan
    desv = np.concatenate([np.abs(v1 - np.median(v1)), np.abs(v0 - np.median(v0))])
    escala = ESCALA_MAD * np.median(desv)
    return escala if escala > 0 else np.nan


def dif_y_efecto(c, i, r, agregacion):
    # Diferencia nivel - referencia y efecto estandarizado, en la muestra original (fila 0) y cada replica.
    with np.errstate(divide="ignore", invalid="ignore"):
        d = c.valor[:, i] - c.valor[:, r]
        if agregacion == "media":
            n1, n0 = c.n[:, i], c.n[:, r]
            gl = n1 + n0 - 2
            sp = np.sqrt((c.ss[:, i] + c.ss[:, r]) / gl)
            j = 1 - 3 / (4 * (n1 + n0) - 9)
            e = np.where((gl > 0) & (sp > 0), j * d / sp, np.nan)
        elif agregacion in ("proporcion", "ponderada"):
            p1, p0 = np.clip(c.valor[:, i], 0, 1), np.clip(c.valor[:, r], 0, 1)
            e = 2 * np.arcsin(np.sqrt(p1)) - 2 * np.arcsin(np.sqrt(p0))
        else:
            e = d / _escala_mad(c.filas[i], c.filas[r])
    return d, e


def ajuste_estratos(ce, k, agregacion):
    # mitad_x_tercil: estratos fijados en la muestra original (las dos celdas con n > 0), promedio ponderado por
    # el n del nivel; una replica en que alguno de esos estratos queda vacio es nula (misma mascara en el efecto).
    S = N_ESTRATOS
    n1, n0 = ce.n[:, k * S:(k + 1) * S], ce.n[:, :S]
    usados = np.flatnonzero((n1[0] > 0) & (n0[0] > 0))
    if usados.size == 0:
        return np.full(ce.n.shape[0], np.nan), np.full(ce.n.shape[0], np.nan), usados
    pares = [dif_y_efecto(ce, k * S + s, s, agregacion) for s in usados]
    pesos = n1[:, usados]
    vacio = ((n1[:, usados] == 0) | (n0[:, usados] == 0)).any(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        d = (pesos * np.column_stack([p[0] for p in pares])).sum(axis=1) / pesos.sum(axis=1)
        e = (pesos * np.column_stack([p[1] for p in pares])).sum(axis=1) / pesos.sum(axis=1)
    d[vacio], e[vacio] = np.nan, np.nan
    return d, e, usados


def _vivas(replicas):
    return float(np.isfinite(replicas).mean()) if replicas.size else 0.0


def _ic(replicas):
    # Percentiles de las replicas con valor; nulo si quedan menos de MIN_REPLICAS_VIVAS.
    if _vivas(replicas) < MIN_REPLICAS_VIVAS:
        return np.nan, np.nan
    lo, hi = np.percentile(replicas[np.isfinite(replicas)], PERCENTILES)
    return float(lo), float(hi)


def _num(v):
    return float(v) if np.isfinite(v) else np.nan


def lectura(lo, hi, e, inestable):
    if not (np.isfinite(lo) and np.isfinite(hi) and np.isfinite(e)) or not (lo > 0 or hi < 0):
        return "sin diferencia clara"
    grande = abs(e) >= EFECTO_MIN
    if inestable:
        return "indicio" if grande else "sin diferencia clara"
    return "diferencia" if grande else "diferencia pequena"


@dataclass
class Notas:
    # Avisos informativos que se juntan entre metricas y se imprimen una vez.
    vacias: list = field(default_factory=list)  # (contexto, nivel, fraccion de replicas vacias)
    un_partido: list = field(default_factory=list)  # (contexto, nivel) con IC nulo por tener un partido
    pocas_vivas: list = field(default_factory=list)  # (metrica, contexto, nivel, celda o ajuste) con IC nulo
    estratos: list = field(default_factory=list)  # (estrato, nivel, n_partidos) con menos de MIN_PARTIDOS


def comparar_contexto(m, nivel_dato, d, contexto, mx, notas):
    # Celdas y comparaciones de una metrica en un contexto; mas el ajuste mitad_x_tercil en score_state.
    niveles = NIVELES[contexto]
    L = len(niveles)
    cod, con_contexto = codigos(d.contexto[contexto], contexto)
    c = agregar(d, cod, L, mx, m.agregacion)
    n_obs, n_par = c.n[0].astype("int64"), c.n_partidos.astype("int64")
    inestable = (n_par < MIN_PARTIDOS) | ((n_obs < MIN_OBS) if nivel_dato != "partido" else False)
    sin_ic = n_par < MIN_PARTIDOS_IC  # celda vacia o de un partido: su valor no varia al remuestrear
    celdas, comps = [], []
    for k, nivel in enumerate(niveles):
        lo = hi = np.nan
        if sin_ic[k]:
            if n_obs[k] > 0:
                notas.un_partido.append((contexto, nivel))
        else:
            vivas = _vivas(c.valor[1:, k])
            lo, hi = _ic(c.valor[1:, k])
            if vivas < MIN_REPLICAS_VIVAS:
                notas.pocas_vivas.append((m.metrica, contexto, nivel, "celda"))
            elif vivas < 1:
                notas.vacias.append((contexto, nivel, 1 - vivas))
        celdas.append({"metrica": m.metrica, "etiqueta_metrica": m.etiqueta, "unidad": m.unidad,
                       "agregacion": m.agregacion, "nivel_dato": nivel_dato, "contexto": contexto, "nivel": nivel,
                       "es_referencia": k == 0, "valor": _num(c.valor[0, k]), "ic_inf": lo, "ic_sup": hi,
                       "n_obs": n_obs[k], "n_partidos": n_par[k], "inestable": bool(inestable[k])})

    ajustadas = {}
    if contexto == CONTEXTO_AJUSTADO and nivel_dato in ("posesion", "evento"):
        est = estratos(d.contexto)
        celda_est = np.where((cod >= 0) & (est >= 0), cod * N_ESTRATOS + est, -1)
        ce = agregar(d, celda_est, L * N_ESTRATOS, mx, m.agregacion)
        for k in range(1, L):
            dif, efe, usados = ajuste_estratos(ce, k, m.agregacion)
            ajustadas[k] = (dif, efe)
            for s in usados:
                for nombre, idx in ((niveles[k], k * N_ESTRATOS + s), (niveles[0], s)):
                    if ce.n_partidos[idx] < MIN_PARTIDOS:
                        notas.estratos.append((NOMBRES_ESTRATOS[s], nombre, int(ce.n_partidos[idx])))

    for k in range(1, L):
        variantes = [("simple", dif_y_efecto(c, k, 0, m.agregacion))]
        if k in ajustadas:
            variantes.append(("mitad_x_tercil", ajustadas[k]))
        inest = bool(inestable[k] or inestable[0])
        for ajuste, (dif, efe) in variantes:
            dlo = dhi = elo = ehi = np.nan
            if not (sin_ic[k] or sin_ic[0]):
                dlo, dhi = _ic(dif[1:])
                elo, ehi = _ic(efe[1:])
                if min(_vivas(dif[1:]), _vivas(efe[1:])) < MIN_REPLICAS_VIVAS:
                    notas.pocas_vivas.append((m.metrica, contexto, niveles[k], ajuste))
            comps.append({"metrica": m.metrica, "contexto": contexto, "nivel": niveles[k],
                          "referencia": niveles[0], "ajuste": ajuste, "diferencia": _num(dif[0]),
                          "dif_ic_inf": dlo, "dif_ic_sup": dhi, "tipo_efecto": TIPO_EFECTO[m.agregacion],
                          "efecto": _num(efe[0]), "efecto_ic_inf": elo, "efecto_ic_sup": ehi,
                          "n_obs_nivel": n_obs[k], "n_obs_ref": n_obs[0], "n_partidos_nivel": n_par[k],
                          "n_partidos_ref": n_par[0], "inestable": inest,
                          "lectura": lectura(dlo, dhi, efe[0], inest)})

    fallas = []
    if int(n_obs.sum()) != con_contexto:
        fallas.append(f"{m.metrica} x {contexto}: suma de n_obs {int(n_obs.sum())} != {con_contexto} filas con "
                      "contexto no nulo (hay niveles fuera de la lista fija)")
    return celdas, comps, fallas


# ---------------------------------------------------------------- validacion y salida

def a_tabla(filas, columnas):
    df = pd.DataFrame(filas, columns=list(columnas))
    return df.astype(columnas)


def validar_salidas(celdas, comps):
    fallas = []
    for nombre, df, columnas, llave in [(SALIDA_CELDAS, celdas, COLUMNAS_CELDAS, LLAVE_CELDAS),
                                        (SALIDA_COMPARACIONES, comps, COLUMNAS_COMPARACIONES, LLAVE_COMPARACIONES)]:
        tipos = {c: str(t) for c, t in df.dtypes.items()}
        if list(df.columns) != list(columnas) or tipos != columnas:
            fallas.append(f"{nombre}: columnas o tipos distintos de los acordados: {tipos}")
        if df.duplicated(llave).any():
            fallas.append(f"{nombre}: llave {llave} duplicada en {int(df.duplicated(llave).sum())} filas")
    sin_valor = celdas[(celdas["n_obs"] > 0) & celdas["valor"].isna()]
    if not sin_valor.empty:
        fallas.append(f"{SALIDA_CELDAS}: valor nulo en {len(sin_valor)} celdas con n_obs > 0: "
                      f"{sin_valor[LLAVE_CELDAS].head(5).to_dict('records')}")
    if not fallas:
        _ok(f"salidas: columnas y tipos acordados, llaves unicas; valor no nulo en las {int((celdas['n_obs'] > 0).sum())}"
            " celdas con n_obs > 0")
    return fallas


def avisos_ic(celdas, comps, notas):
    # Informativos: IC que no contiene el valor puntual, IC nulos y celdas o estratos con pocos partidos.
    fuera = []
    for nombre, df, valor, lo, hi in [(SALIDA_CELDAS, celdas, "valor", "ic_inf", "ic_sup"),
                                      (SALIDA_COMPARACIONES, comps, "diferencia", "dif_ic_inf", "dif_ic_sup"),
                                      (SALIDA_COMPARACIONES, comps, "efecto", "efecto_ic_inf", "efecto_ic_sup")]:
        malo = df[(df[valor] < df[lo] - TOL_IC) | (df[valor] > df[hi] + TOL_IC)]
        for r in malo.itertuples():
            fuera.append(f"{nombre}:{r.metrica}/{r.contexto}/{r.nivel}/{valor}")
    if fuera:
        _aviso(f"{len(fuera)} IC no contienen el valor puntual (bootstrap asimetrico o con pocas replicas): "
               f"{fuera[:5]}{' ...' if len(fuera) > 5 else ''}")
    else:
        _ok("todos los IC calculados contienen su valor puntual")
    if notas.un_partido:
        niveles = sorted({f"{c}={n}" for c, n in notas.un_partido})
        _aviso(f"IC nulo en {len(notas.un_partido)} celdas de un solo partido ({', '.join(niveles)}); sus "
               "comparaciones quedan sin IC y con lectura sin diferencia clara")
    if notas.pocas_vivas:
        _aviso(f"IC nulo por tener menos de {MIN_REPLICAS_VIVAS:.0%} de replicas con valor en {len(notas.pocas_vivas)} "
               f"casos: {notas.pocas_vivas[:5]}{' ...' if len(notas.pocas_vivas) > 5 else ''}")
    if notas.vacias:
        peor = {}
        for contexto, nivel, frac in notas.vacias:
            peor[(contexto, nivel)] = max(frac, peor.get((contexto, nivel), 0.0))
        detalle = ", ".join(f"{c}={n} {f:.1%}" for (c, n), f in sorted(peor.items(), key=lambda t: -t[1]))
        _aviso(f"celdas que quedan vacias en alguna replica (esas replicas no entran en su IC), maximo por nivel: "
               f"{detalle}")
    minimos = {}
    for estrato, nivel, n in notas.estratos:
        minimos[(estrato, nivel)] = min(n, minimos.get((estrato, nivel), n))
    for estrato in NOMBRES_ESTRATOS:
        celdas_flojas = [f"{nivel} {n}" for (e, nivel), n in minimos.items() if e == estrato]
        if celdas_flojas:
            _aviso(f"ajuste mitad_x_tercil: el estrato {estrato} entra con menos de {MIN_PARTIDOS} partidos en "
                   f"{', '.join(celdas_flojas)} (minimo entre metricas); la fila ajustada lleva el inestable de la "
                   "simple")


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
        raise ErrorContexto(f"no se pudo preparar {PROCESSED}: {e}") from e
    reemplazados = []
    try:
        try:
            for nombre, df in tablas.items():
                df.to_parquet(tmp / nombre, compression="zstd", index=False)
        except ERRORES_ESCRITURA as e:
            raise ErrorContexto(f"no se pudo escribir en la carpeta temporal {tmp}; no se reemplazo nada: "
                                f"{type(e).__name__}: {e}") from e
        bloqueados = _bloqueados(archivos)
        if bloqueados:
            raise ErrorContexto(f"no se reemplazo nada en {PROCESSED}: estos destinos estan bloqueados o no se pueden "
                                f"escribir: {bloqueados}. Cierralos y vuelve a correr.")
        for archivo in archivos:
            try:
                os.replace(tmp / archivo, PROCESSED / archivo)
                reemplazados.append(archivo)
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
    finally:
        if not 0 < len(reemplazados) < len(archivos):
            _borrar(tmp)
    for viejo in PROCESSED.glob(f"{PREFIJO_TMP}*"):
        if viejo != tmp:
            _borrar(viejo)


def resumen(celdas, comps):
    print(f"{SALIDA_CELDAS}: {len(celdas):,} filas; {SALIDA_COMPARACIONES}: {len(comps):,} filas")
    conteo = comps["lectura"].value_counts().reindex(LECTURAS, fill_value=0)
    print("comparaciones por lectura: " + ", ".join(f"{k} {v}" for k, v in conteo.items()))
    for lect in LECTURAS[:3]:
        sel = comps[comps["lectura"] == lect]
        print(f"{lect} ({len(sel)}):")
        for r in sel.itertuples():
            print(f"   {r.metrica} | {r.contexto} {r.nivel} vs {r.referencia} ({r.ajuste}): "
                  f"dif {r.diferencia:+.4g} [{r.dif_ic_inf:+.4g}, {r.dif_ic_sup:+.4g}], "
                  f"{r.tipo_efecto} {r.efecto:+.2f}")


def calcular(metricas, tablas, replicas, semilla):
    # Devuelve (celdas, comparaciones, fallas) para todas las metricas del registro.
    partidos = tablas.tabla(PARTIDOS)["match_id"]
    fallas = validar_registro(metricas)
    if partidos.isna().any() or partidos.duplicated().any():
        fallas.append("contexto_partidos: match_id nulo o repetido")
    if fallas:
        return None, None, fallas
    partidos_idx = pd.Index(np.sort(partidos.astype("int64").to_numpy()))
    m_boot = matriz_bootstrap(len(partidos_idx), replicas, semilla)
    mx = np.vstack([np.ones(len(partidos_idx)), m_boot])  # fila 0 = muestra original
    print(f"bootstrap: {replicas} replicas de {len(partidos_idx)} partidos, semilla {semilla}")

    celdas, comps, notas = [], [], Notas()
    for m in metricas:
        nivel_dato = NIVEL_DATO[m.llave]
        if nivel_dato == "evento" and "es_eq" not in m.filtro:
            _aviso(f"{m.metrica}: metrica de evento sin filtro por es_eq; mezcla los eventos de los dos equipos")
        d, f = preparar(m, tablas, partidos_idx)
        fallas += f
        if d is None or f:
            continue
        cero = f"; {d.peso_cero} filas con peso 0 fuera" if m.peso is not None else ""
        print(f"{m.metrica}: {len(d.x):,} filas de {len(np.unique(d.g))} partidos ({nivel_dato}, {m.agregacion}{cero})")
        for contexto in CONTEXTOS_POR_NIVEL[nivel_dato]:
            ce, co, f = comparar_contexto(m, nivel_dato, d, contexto, mx, notas)
            celdas += ce
            comps += co
            fallas += f
    if fallas:
        return None, None, fallas
    celdas_df, comps_df = a_tabla(celdas, COLUMNAS_CELDAS), a_tabla(comps, COLUMNAS_COMPARACIONES)
    _ok(f"suma de n_obs por contexto = filas con contexto no nulo, en las {len(metricas)} metricas")
    fallas += validar_salidas(celdas_df, comps_df)
    avisos_ic(celdas_df, comps_df, notas)
    return celdas_df, comps_df, fallas


def main():
    try:
        sys.stdout.reconfigure(errors="replace")  # niveles con acento en consolas sin UTF-8
    except AttributeError:
        pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sin-escribir", action="store_true", help="calcula y valida sin escribir en data/processed/")
    p.add_argument("--replicas", type=int, default=REPLICAS, help=f"replicas bootstrap (por defecto {REPLICAS})")
    p.add_argument("--semilla", type=int, default=SEMILLA, help=f"semilla del bootstrap (por defecto {SEMILLA})")
    args = p.parse_args()
    if args.replicas < 1:
        p.error("--replicas debe ser al menos 1")
    inicio = time.perf_counter()

    try:
        celdas, comps, fallas = calcular(METRICAS, Tablas(), args.replicas, args.semilla)
    except ErrorContexto as e:
        print(f"ERROR: {e}\nNo se escribio nada.", file=sys.stderr)
        return 1
    if fallas:
        print(f"ERROR: {len(fallas)} validaciones duras fallaron:", file=sys.stderr)
        for x in fallas:
            print(f"   {x}", file=sys.stderr)
        print("No se escribio nada.", file=sys.stderr)
        return 1
    resumen(celdas, comps)
    if args.sin_escribir:
        print(f"Sin escribir (--sin-escribir). {time.perf_counter() - inicio:.1f} s")
        return 0
    try:
        escribir({SALIDA_CELDAS: celdas, SALIDA_COMPARACIONES: comps})
    except ErrorContexto as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"Escrito en {PROCESSED.relative_to(ROOT).as_posix()}/: {SALIDA_CELDAS}, {SALIDA_COMPARACIONES}. "
          f"{time.perf_counter() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
