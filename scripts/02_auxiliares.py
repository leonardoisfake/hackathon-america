"""Tablas auxiliares del contrato v0.2: related_events, tactics_lineup, defensive_responsibility y shot_freeze_frame.

Uso (desde la raiz del repo):
    python scripts/02_auxiliares.py --solo-partido 3995374   # escribe en data/interim/muestra/
    python scripts/02_auxiliares.py                          # todos los partidos de partidos.parquet, en data/interim/
    python OTRA_CARPETA/02_auxiliares.py --raiz RUTA_DEL_REPO  # si el script no vive en scripts/

Entradas:
    data/interim/partidos.parquet          match_id validos (C18)
    data/interim/eventos.parquet           para revisar huerfanos, related_index y que los padres de shot_freeze_frame sean tiros
    data/raw/parquet/events__*.parquet     las 4 listas anidadas, como texto JSON (no estan en eventos.parquet)

Salidas (data/interim/, o data/interim/muestra/ con --solo-partido):
    related_events.parquet, tactics_lineup.parquet, defensive_responsibility.parquet, shot_freeze_frame.parquet

Cada tabla sale con las columnas, tipos y llave de docs/contrato/<tabla>.md y se ordena por su llave. Antes de
escribir se revisa: contrato.validar() en las 4, llaves sin duplicar, cada (match_id, index) presente en eventos y
que los padres de shot_freeze_frame sean Shot. Si algo falla no se escribe nada. Se escribe en una carpeta temporal
y despues se reemplaza archivo por archivo.

Codigos de salida: 0 si todo se escribio; 1 si hay un error de datos, contrato, revision o escritura;
2 si el partido pedido con --solo-partido no esta en partidos.parquet.
"""
import argparse
import contextlib
import glob
import json
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

# managers no se arma aqui: C20 lo deja resumido en las columnas entrenador_* de partidos
TABLAS = ["related_events", "tactics_lineup", "defensive_responsibility", "shot_freeze_frame"]
LLAVES = {
    "related_events": ["match_id", "index", "related_id"],
    "tactics_lineup": ["match_id", "index", "player_id"],
    "defensive_responsibility": ["match_id", "index", "player_id"],
    "shot_freeze_frame": ["match_id", "index", "jugador_idx"],
}
# columna cruda con la lista JSON de cada tabla
LISTAS = {
    "related_events": "related_events",
    "tactics_lineup": "tactics.lineup",
    "defensive_responsibility": "defensive_responsibility.players",
    "shot_freeze_frame": "shot.freeze_frame",
}
# filas del crudo explotado de los 91 partidos (docs/contrato/README.md); solo se comparan, no detienen nada
FILAS_ESPERADAS = {"related_events": 606_902, "tactics_lineup": 5_714, "defensive_responsibility": 1_794_080,
                   "shot_freeze_frame": 30_057}


class ErrorAuxiliar(Exception):
    pass


@contextlib.contextmanager
def en_evento(tabla, mid, idx):
    # Un error al leer la lista de un evento sale con la tabla, el match_id y el index.
    try:
        yield
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as e:
        raise ErrorAuxiliar(f"{tabla}: match_id {mid}, index {idx}: {type(e).__name__}: {e}") from e


def leer_lista(valor):
    # Texto JSON a lista; una lista ya parseada pasa tal cual y el nulo da lista vacia.
    if isinstance(valor, str):
        valor = json.loads(valor)
    elif valor is None or (pd.api.types.is_scalar(valor) and pd.isna(valor)):
        return []
    if isinstance(valor, (list, np.ndarray)):
        return list(valor)
    raise TypeError(f"se esperaba texto JSON con una lista, una lista o nulo, y llego {type(valor).__name__}")


# ---------- lectura ----------

def leer_partidos(interim, solo_partido):
    p = pd.read_parquet(interim / "partidos.parquet", columns=["match_id"])
    ids = sorted(int(x) for x in p["match_id"].dropna())
    if solo_partido is not None:
        ids = [x for x in ids if x == solo_partido]
    return ids


def leer_eventos_crudos(raw, ids, contrato_df):
    # Solo match_id, index, las 4 listas y las columnas crudas que nombra el origen del contrato (id, team.id, ...).
    archivos = sorted(glob.glob(str(raw / "events__*.parquet")))
    if not archivos:
        raise ErrorAuxiliar(f"no hay archivos events__*.parquet en {raw}")
    origenes = set(contrato_df.loc[contrato_df["tabla"].isin(TABLAS), "origen"].astype(str))
    pedidas = {"match_id", "index", *LISTAS.values()}
    partes = []
    for a in archivos:
        nombres = pq.read_schema(a).names
        faltan = sorted(pedidas - set(nombres))
        if faltan:
            raise ErrorAuxiliar(f"{Path(a).name}: faltan columnas crudas {faltan}")
        columnas = [x for x in nombres if x in pedidas or x in origenes]
        print(f"lee {Path(a).name}")
        partes.append(pq.read_table(a, columns=columnas, filters=[("match_id", "in", ids)]))
    df = pa.concat_tables(partes, promote_options="permissive").to_pandas()
    return df.sort_values(["match_id", "index"]).reset_index(drop=True)


def leer_eventos_limpios(interim, ids):
    return pd.read_parquet(interim / "eventos.parquet", columns=["match_id", "index", "id", "type_name"],
                           filters=[("match_id", "in", ids)])


def con_lista(raw, tabla, columnas):
    # Filas del crudo que traen la lista de la tabla, con las columnas pedidas.
    col = LISTAS[tabla]
    return raw.loc[raw[col].notna(), ["match_id", "index", *columnas, col]].itertuples(index=False, name=None)


# ---------- una funcion por tabla ----------

def armar_related_events(raw, eventos):
    filas = {"match_id": [], "index": [], "id": [], "related_id": []}
    for mid, idx, uuid, lista in con_lista(raw, "related_events", ["id"]):
        with en_evento("related_events", mid, idx):
            for rel in leer_lista(lista):
                filas["match_id"].append(mid)
                filas["index"].append(idx)
                filas["id"].append(uuid)
                filas["related_id"].append(rel)
    df = pd.DataFrame(filas)
    # related_index: el index del evento cuyo id es related_id en el mismo partido; nulo si no aparece
    df["related_id"] = df["related_id"].astype("string").str.strip()
    destino = eventos[["match_id", "id", "index"]].rename(columns={"id": "related_id", "index": "related_index"})
    destino = destino.astype({"match_id": "int64", "related_id": "string"})
    df = df.merge(destino, how="left", on=["match_id", "related_id"], validate="many_to_one")
    return df


def armar_tactics_lineup(raw):
    filas = {c: [] for c in ("match_id", "index", "team_id", "tactics_formation", "jersey_number", "player_id",
                             "player_name", "position_id", "position_name")}
    for mid, idx, equipo, formacion, lista in con_lista(raw, "tactics_lineup", ["team.id", "tactics.formation"]):
        with en_evento("tactics_lineup", mid, idx):
            for j in leer_lista(lista):
                posicion = j.get("position") or {}
                filas["match_id"].append(mid)
                filas["index"].append(idx)
                filas["team_id"].append(equipo)
                filas["tactics_formation"].append(formacion)
                filas["jersey_number"].append(j.get("jersey_number"))
                filas["player_id"].append(j["player"]["id"])
                filas["player_name"].append(j["player"].get("name"))
                filas["position_id"].append(posicion.get("id"))
                filas["position_name"].append(posicion.get("name"))
    return pd.DataFrame(filas)


def armar_defensive_responsibility(raw):
    filas = {c: [] for c in ("match_id", "index", "player_id", "probability", "interception_like_probability",
                             "pressure_like_probability")}
    for mid, idx, lista in con_lista(raw, "defensive_responsibility", []):
        with en_evento("defensive_responsibility", mid, idx):
            for j in leer_lista(lista):
                filas["match_id"].append(mid)
                filas["index"].append(idx)
                filas["player_id"].append(j["player_id"])
                filas["probability"].append(j.get("probability"))
                # nulo legitimo: StatsBomb omite la llave cuando no aplica
                filas["interception_like_probability"].append(j.get("interception_like_probability"))
                filas["pressure_like_probability"].append(j.get("pressure_like_probability"))
    return pd.DataFrame(filas)


def armar_shot_freeze_frame(raw):
    filas = {c: [] for c in ("match_id", "index", "jugador_idx", "teammate", "player_id", "player_name",
                             "position_id", "position_name", "x", "y")}
    for mid, idx, lista in con_lista(raw, "shot_freeze_frame", []):
        with en_evento("shot_freeze_frame", mid, idx):
            for k, j in enumerate(leer_lista(lista)):
                posicion = j.get("position") or {}
                loc = list(j.get("location") or []) + [None, None]
                filas["match_id"].append(mid)
                filas["index"].append(idx)
                filas["jugador_idx"].append(k)
                filas["teammate"].append(j.get("teammate"))
                filas["player_id"].append(j["player"]["id"])
                filas["player_name"].append(j["player"].get("name"))
                filas["position_id"].append(posicion.get("id"))
                filas["position_name"].append(posicion.get("name"))
                filas["x"].append(loc[0])
                filas["y"].append(loc[1])
    return pd.DataFrame(filas)


# ---------- contrato ----------

def convertir(serie, tipo):
    # Mismo criterio que 02_limpieza.py: ningun valor no nulo puede quedar nulo al convertir.
    if tipo in ("Int64", "float64"):
        if pd.api.types.is_bool_dtype(serie.dtype) or pd.api.types.infer_dtype(serie, skipna=True) == "boolean":
            raise TypeError(f"llegan booleanos y el contrato pide {tipo}")
        out = pd.to_numeric(serie, errors="coerce")
        malos = serie.notna() & out.isna()
        if malos.any():
            raise ValueError(f"{int(malos.sum())} valores no se pueden convertir a {tipo}, "
                             f"por ejemplo {serie[malos].unique()[:5].tolist()}")
        return out.astype(tipo)
    if tipo == "boolean":
        return serie.astype("boolean")
    if tipo == "string":
        return serie.astype("string").str.strip()
    if tipo == "category":
        return serie.astype("string").str.strip().astype("category")
    raise ValueError(f"tipo que este script no maneja: {tipo}")


def aplicar_contrato(df, tabla, contrato_df):
    # Columnas en el orden del contrato, con su tipo, relleno y puede_faltar; las que no estan en el contrato se van.
    filas = contrato_df[contrato_df["tabla"] == tabla]
    out = {}
    for f in filas.itertuples(index=False):
        if f.columna in df.columns:
            try:
                serie = convertir(df[f.columna], f.tipo)
            except (ValueError, TypeError) as e:
                raise ErrorAuxiliar(f"{tabla}.{f.columna} (tipo {f.tipo}): {e}") from e
        elif f.puede_faltar:
            serie = pd.Series(pd.NA, index=df.index).pipe(convertir, f.tipo)
        else:
            raise ErrorAuxiliar(f"{tabla}.{f.columna}: no se armo y el contrato no la marca como puede_faltar")
        if pd.notna(f.relleno) and f.relleno == "False":
            serie = serie.fillna(False)
        out[f.columna] = serie
    return pd.DataFrame(out, index=df.index).sort_values(LLAVES[tabla]).reset_index(drop=True)


# ---------- revisiones ----------

def existe(hija, padre):
    # Mascara: filas de `hija` cuya llave (mismas columnas, mismo orden) esta en `padre`.
    return pd.MultiIndex.from_frame(hija).isin(pd.MultiIndex.from_frame(padre)) & hija.notna().all(axis=1).to_numpy()


def revisar(tablas, eventos, contrato):
    # Devuelve la lista de problemas (vacia si todo esta bien) y el conteo de related_id encontrados.
    problemas = []
    llave_ev = eventos[["match_id", "index"]]
    for nombre, df in tablas.items():
        if not contrato.validar(df, nombre)["ok"]:
            problemas.append(f"{nombre}: no cumple el contrato (ver arriba)")
        dup = int(df.duplicated(LLAVES[nombre]).sum())
        if dup:
            problemas.append(f"{nombre}: {dup} llaves duplicadas en {LLAVES[nombre]}")
        huerfanos = int((~existe(df[["match_id", "index"]], llave_ev)).sum())
        if huerfanos:
            problemas.append(f"{nombre}: {huerfanos} filas con (match_id, index) que no esta en eventos")
    tiros = eventos.loc[eventos["type_name"] == "Shot", ["match_id", "index"]]
    no_tiro = ~existe(tablas["shot_freeze_frame"][["match_id", "index"]], tiros)
    if no_tiro.any():
        ejemplos = tablas["shot_freeze_frame"].loc[no_tiro, ["match_id", "index"]].drop_duplicates().head(5)
        problemas.append(f"shot_freeze_frame: {int(no_tiro.sum())} filas cuyo evento padre no es Shot, "
                         f"por ejemplo {ejemplos.values.tolist()}")
    # related_index no nulo = el related_id existe como id de un evento del mismo partido
    encontrados = int(tablas["related_events"]["related_index"].notna().sum())
    return problemas, encontrados


# ---------- escritura ----------

def escribir(salida, tablas):
    # Escribe en una carpeta temporal dentro de `salida` y despues reemplaza archivo por archivo.
    try:
        salida.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=".tmp_auxiliares_", dir=salida))
    except OSError as e:
        raise ErrorAuxiliar(f"no se pudo preparar {salida}: {e}") from e
    hechos = []
    try:
        for nombre, df in tablas.items():
            df.to_parquet(tmp / f"{nombre}.parquet", compression="zstd", index=False)
        for nombre in tablas:
            os.replace(tmp / f"{nombre}.parquet", salida / f"{nombre}.parquet")
            hechos.append(nombre)
    except (OSError, ValueError) as e:
        if hechos:
            raise ErrorAuxiliar(f"el reemplazo quedo a medias en {salida}: ya se reemplazaron {hechos}; el resto sigue "
                                f"en la carpeta temporal {tmp}, que no se borro ({e})") from e
        raise ErrorAuxiliar(f"no se reemplazo nada en {salida}: {type(e).__name__}: {e}") from e
    finally:
        if len(hechos) in (0, len(tablas)):
            shutil.rmtree(tmp, ignore_errors=True)


def resumen(tablas, encontrados, muestra, segundos):
    print("\nFilas por tabla:")
    for nombre, df in tablas.items():
        esperado = FILAS_ESPERADAS[nombre]
        if muestra:
            nota = "muestra de un partido; no se compara"
        elif len(df) == esperado:
            nota = "cuadra"
        else:
            nota = f"NO cuadra: diferencia {len(df) - esperado:+,} (esperadas en el crudo de los 91 partidos)"
        print(f"   {nombre}: {len(df):,} filas (esperadas {esperado:,}; {nota})")
    total = len(tablas["related_events"])
    print(f"related_id que existen como id en eventos del mismo partido: {encontrados:,} de {total:,} "
          f"({total - encontrados:,} sin evento, quedan con related_index nulo)")
    print(f"Tiempo: {segundos:.1f} s")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--solo-partido", type=int, metavar="MATCH_ID", help="arma un partido y escribe en data/interim/muestra/")
    p.add_argument("--raiz", type=Path, default=Path(__file__).resolve().parents[1], metavar="RUTA_DEL_REPO",
                   help="raiz del repo (por defecto, la carpeta padre de la del script)")
    args = p.parse_args()
    inicio = time.perf_counter()
    raiz = args.raiz.resolve()
    sys.path.insert(0, str(raiz / "scripts"))  # contrato.py esta en scripts/
    import contrato

    interim = raiz / "data" / "interim"
    salida = interim / "muestra" if args.solo_partido is not None else interim
    try:
        contrato_df = contrato.cargar()
        ids = leer_partidos(interim, args.solo_partido)
        if not ids:
            if args.solo_partido is not None:
                print(f"ERROR: match_id {args.solo_partido} no esta en data/interim/partidos.parquet", file=sys.stderr)
                return 2
            raise ErrorAuxiliar("data/interim/partidos.parquet no tiene partidos")
        raw = leer_eventos_crudos(raiz / "data" / "raw" / "parquet", ids, contrato_df)
        eventos = leer_eventos_limpios(interim, ids)
        armadas = {
            "related_events": armar_related_events(raw, eventos),
            "tactics_lineup": armar_tactics_lineup(raw),
            "defensive_responsibility": armar_defensive_responsibility(raw),
            "shot_freeze_frame": armar_shot_freeze_frame(raw),
        }
        del raw
        tablas = {nombre: aplicar_contrato(df, nombre, contrato_df) for nombre, df in armadas.items()}
        del armadas
    except (ErrorAuxiliar, OSError) as e:
        print(f"ERROR: {e}\nNo se escribio nada.", file=sys.stderr)
        return 1

    problemas, encontrados = revisar(tablas, eventos, contrato)
    if problemas:
        for x in problemas:
            print(f"ERROR: {x}", file=sys.stderr)
        print("No se escribio nada.", file=sys.stderr)
        return 1
    try:
        escribir(salida, tablas)
    except ErrorAuxiliar as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    resumen(tablas, encontrados, args.solo_partido is not None, time.perf_counter() - inicio)
    print(f"Escrito en {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
