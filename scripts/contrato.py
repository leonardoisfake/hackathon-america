"""Contrato de datos ejecutable: lee docs/contrato/contrato_datos.csv.

    from contrato import vacio, validar          # con scripts/ en el sys.path
    df = vacio("eventos")                        # DataFrame vacio con los dtypes del contrato
    informe = validar(df_limpio, "eventos")      # imprime el resultado y lo devuelve

Desde la raiz: python scripts/contrato.py eventos data/interim/muestra/eventos.parquet
"""
import sys
from pathlib import Path

import pandas as pd

RUTA_CSV = Path(__file__).resolve().parents[1] / "docs" / "contrato" / "contrato_datos.csv"
TIPOS_VALIDOS = {"Int64", "float64", "boolean", "string", "category", "datetime64[us]"}
COLUMNAS = ["tabla", "columna", "tipo", "origen", "regla", "relleno", "puede_faltar"]
# tipos de evento que no entran al analisis tactico (C5); se conservan con es_administrativo = True
ADMINISTRATIVOS = ("Half Start", "Half End", "Starting XI", "Tactical Shift", "Substitution", "Player On",
                   "Player Off", "Injury Stoppage", "Referee Ball-Drop", "Camera On")


def cargar(ruta=RUTA_CSV):
    """Contrato completo como DataFrame.

    relleno es texto ("False") o <NA>; preguntar con pd.notna(f["relleno"]), porque comparar <NA> con "False"
    lanza error. puede_faltar es bool. Desde la v0.2 el csv debe traer relleno y puede_faltar.
    """
    c = pd.read_csv(ruta, encoding="utf-8", dtype={"relleno": "string", "puede_faltar": "string"})
    faltan = [x for x in COLUMNAS if x not in c.columns]
    if faltan:
        raise ValueError(f"{ruta}: faltan las columnas {faltan}")
    malos = sorted(map(str, set(c["tipo"]) - TIPOS_VALIDOS))
    if malos:
        raise ValueError(f"{ruta}: tipos fuera de TIPOS_VALIDOS: {malos}")
    pf = c["puede_faltar"]
    if pf.isna().any() or not pf.isin(["True", "False"]).all():
        raise ValueError(f"{ruta}: puede_faltar debe ser True o False en todas las filas; "
                         f"valores encontrados: {sorted(map(str, set(pf)))}")
    c["puede_faltar"] = (pf == "True").astype(bool)
    relleno = c["relleno"]
    malos = sorted(map(str, set(relleno.dropna()) - {"False"}))
    if malos:
        raise ValueError(f"{ruta}: relleno solo admite vacio o False; valores encontrados: {malos}")
    fuera = c.loc[relleno.notna() & (c["tipo"] != "boolean"), ["tabla", "columna", "tipo"]]
    if not fuera.empty:
        raise ValueError(f"{ruta}: relleno solo va en columnas boolean: {fuera.values.tolist()}")
    return c


def tablas():
    return sorted(cargar()["tabla"].unique())


def esquema(tabla):
    # Lista ordenada de (columna, tipo) de una tabla.
    c = cargar()
    c = c[c["tabla"] == tabla]
    if c.empty:
        raise KeyError(f"Tabla desconocida: {tabla!r}. Tablas del contrato: {tablas()}")
    return list(zip(c["columna"], c["tipo"]))


def vacio(tabla):
    # DataFrame vacio con las columnas y dtypes del contrato.
    return pd.DataFrame({col: pd.Series(dtype=tipo) for col, tipo in esquema(tabla)})


def _coincide(esperado, serie):
    # Las fechas se comparan exactas: otra resolucion o una zona horaria no pasan.
    dt = serie.dtype
    if esperado == "category":
        # las categorias deben ser texto; una columna toda nula puede traer categorias vacias de tipo object
        return isinstance(dt, pd.CategoricalDtype) and pd.api.types.infer_dtype(dt.categories) in ("string", "empty")
    if esperado == "string":
        # pandas 3 lee el texto como 'str' y no como 'string'; se aceptan los dos
        return pd.api.types.is_string_dtype(dt) and not isinstance(dt, pd.CategoricalDtype) and dt != object
    return str(dt) == esperado


def validar(df, tabla, imprimir=True):
    # Compara df contra el contrato. Devuelve dict con faltantes, sobrantes, tipo_incorrecto, nulos_con_relleno y ok.
    esperado = dict(esquema(tabla))
    c = cargar()
    con_relleno = c.loc[(c["tabla"] == tabla) & c["relleno"].notna(), "columna"].tolist()
    faltantes = [x for x in esperado if x not in df.columns]
    sobrantes = [x for x in df.columns if x not in esperado]
    tipo_mal = [(x, esperado[x], _describir(df[x])) for x in esperado if x in df.columns and not _coincide(esperado[x], df[x])]
    # una columna con relleno ya se lleno en la limpieza, asi que no debe traer nulos
    nulos_relleno = [(x, int(df[x].isna().sum())) for x in con_relleno if x in df.columns and df[x].isna().any()]
    informe = {"tabla": tabla, "filas": len(df), "columnas": len(df.columns), "faltantes": faltantes,
               "sobrantes": sobrantes, "tipo_incorrecto": tipo_mal, "nulos_con_relleno": nulos_relleno,
               "ok": not (faltantes or sobrantes or tipo_mal or nulos_relleno)}
    if imprimir:
        estado = "OK" if informe["ok"] else "FALLA"
        print(f"[{estado}] {tabla}: {len(df)} filas, {len(df.columns)} columnas (contrato: {len(esperado)})")
        if faltantes:
            print(f"   faltantes ({len(faltantes)}): {faltantes}")
        if sobrantes:
            print(f"   sobrantes ({len(sobrantes)}): {sobrantes}")
        if tipo_mal:
            print(f"   tipo incorrecto ({len(tipo_mal)}):")
            for x, e, o in tipo_mal:
                print(f"      {x}: esperado {e}, obtenido {o}")
        if nulos_relleno:
            print(f"   nulos en columnas con relleno ({len(nulos_relleno)}): {nulos_relleno}")
    return informe


def _describir(serie):
    dt = serie.dtype
    if isinstance(dt, pd.CategoricalDtype):
        return f"category (categorias {pd.api.types.infer_dtype(dt.categories)})"
    return str(dt)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Uso: python scripts/contrato.py <tabla> <archivo.parquet>")
    sys.exit(0 if validar(pd.read_parquet(sys.argv[2]), sys.argv[1])["ok"] else 1)
