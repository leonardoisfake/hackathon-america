"""Contrato de datos ejecutable: lee docs/contrato_datos.csv.

    from contrato import vacio, validar          # con scripts/ en el sys.path
    df = vacio("eventos")                        # DataFrame vacio con los dtypes del contrato
    informe = validar(df_limpio, "eventos")      # imprime el resultado y lo devuelve

Desde la raiz: python scripts/contrato.py eventos data/interim/muestra/eventos.parquet
"""
import sys
from pathlib import Path

import pandas as pd

RUTA_CSV = Path(__file__).resolve().parents[1] / "docs" / "contrato_datos.csv"
TIPOS_VALIDOS = {"Int64", "float64", "boolean", "string", "category", "datetime64[ns]"}


def cargar(ruta=RUTA_CSV):
    # Contrato completo como DataFrame (tabla, columna, tipo, origen, regla).
    return pd.read_csv(ruta, encoding="utf-8")


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
    dt = serie.dtype
    if esperado == "category":
        return isinstance(dt, pd.CategoricalDtype)
    if esperado == "string":
        # pandas 3 lee el texto como 'str' y no como 'string'; se aceptan los dos
        return pd.api.types.is_string_dtype(dt) and not isinstance(dt, pd.CategoricalDtype) and dt != object
    if esperado == "datetime64[ns]":
        return pd.api.types.is_datetime64_any_dtype(dt)
    return str(dt) == esperado


def validar(df, tabla, imprimir=True):
    # Compara df contra el contrato. Devuelve dict con faltantes, sobrantes, tipo_incorrecto y ok.
    esperado = dict(esquema(tabla))
    faltantes = [c for c in esperado if c not in df.columns]
    sobrantes = [c for c in df.columns if c not in esperado]
    tipo_mal = [(c, esperado[c], str(df[c].dtype)) for c in esperado if c in df.columns and not _coincide(esperado[c], df[c])]
    informe = {"tabla": tabla, "filas": len(df), "columnas": len(df.columns), "faltantes": faltantes,
               "sobrantes": sobrantes, "tipo_incorrecto": tipo_mal,
               "ok": not (faltantes or sobrantes or tipo_mal)}
    if imprimir:
        estado = "OK" if informe["ok"] else "FALLA"
        print(f"[{estado}] {tabla}: {len(df)} filas, {len(df.columns)} columnas (contrato: {len(esperado)})")
        if faltantes:
            print(f"   faltantes ({len(faltantes)}): {faltantes}")
        if sobrantes:
            print(f"   sobrantes ({len(sobrantes)}): {sobrantes}")
        if tipo_mal:
            print(f"   tipo incorrecto ({len(tipo_mal)}):")
            for c, e, o in tipo_mal:
                print(f"      {c}: esperado {e}, obtenido {o}")
    return informe


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Uso: python scripts/contrato.py <tabla> <archivo.parquet>")
    sys.exit(0 if validar(pd.read_parquet(sys.argv[2]), sys.argv[1])["ok"] else 1)
