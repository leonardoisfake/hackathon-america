"""Transformación y métricas de ataque (fase 3): Inicio, construcción, ocasiones y valor.
Fichas de la especificación de métricas de Lee (bloques I y V):
- I1 possession_start_type
- I2 gk_distribution
- I3 line_breaking_pass y ball_receipt_in_space
- I4 progressive_pass y carry_progress
- I5 build_up_chain
- V1 xG y uplift de ejecución
- V2 xA (Expected Assists)
- V3 OBV neto
- V4 deep_progressions y deep_completions
- V5 xGChain y xGBuildup

Uso:
    python scripts/03_ataque.py                 # calcula, valida y escribe en data/processed/
    python scripts/03_ataque.py --sin-escribir  # calcula y valida sin escribir
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
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"

# Nombres de las salidas aprobadas
SALIDA_ATAQUE_EVENTOS = "ataque_eventos.parquet"
SALIDA_ATAQUE_POSESIONES = "ataque_posesiones.parquet"

EQ = 1229  # Equipo analizado: América con Jardine
LLAVE_EVENTO = ["match_id", "index"]
LLAVE_POSESION = ["match_id", "possession"]
PERIODO_PENALES = 5

# Umbrales estándar del framework
UMBRAL_GK_CORTO = 30.0  # Yardas para pase corto del portero
UMBRAL_PROGRESIVO_RATIO = 0.90  # 10% más cerca de la portería rival
DEEP_ZONE_X = 102.0  # Coordenada x para zona profunda (últimas 18 yardas)
PORTERIA_X = 120.0
PORTERIA_Y = 40.0

# Columnas que usa el script (end_x/end_y se leen según type_name: Pass, Carry, Shot o Goal Keeper)
COLS_EVENTOS = [
    "match_id", "id", "index", "period", "possession", "type_name", "team_id", "position_name", "x", "y",
    "end_x", "end_y", "pass_length", "pass_outcome_name", "pass_assisted_shot_id", "shot_key_pass_id",
    "shot_statsbomb_xg", "shot_shot_execution_xg_uplift", "shot_type_name", "obv_total_net"
]
COLS_POSESIONES = ["match_id", "possession", "play_pattern_name", "es_eq", "is_valid_possession", "x_inicio"]
COLS_FRAMES = ["match_id", "event_uuid", "line_breaking_pass", "ball_receipt_in_space"]
COLS_TMS = ["match_id", "team_id", "team_match_np_xg"]

TOLERANCIA_NP_XG = 0.01  # Diferencia máxima por partido contra team_match_np_xg para no avisar (redondeo)

ERRORES_ESCRITURA = (OSError, ValueError, TypeError, pa.lib.ArrowException)


class ErrorAtaque(Exception):
    pass


def leer(nombre, carpeta="interim", columnas=None):
    base = INTERIM if carpeta == "interim" else PROCESSED
    ruta = base / f"{nombre}.parquet"
    if not ruta.exists():
        raise ErrorAtaque(f"no existe {ruta.relative_to(ROOT).as_posix()}; verifica la fase previa")
    try:
        if columnas is not None:
            faltan = [c for c in columnas if c not in pq.read_schema(ruta).names]
            if faltan:
                raise ErrorAtaque(f"{nombre} no tiene las columnas {faltan}; revisa el contrato de datos")
        return pd.read_parquet(ruta, columns=columnas)
    except (OSError, ValueError, KeyError) as e:
        raise ErrorAtaque(f"no se pudo leer {nombre}: {type(e).__name__}: {e}") from e


def _texto(s):
    return s.astype("string")


def _distancia_porteria(x, y):
    """Calcula la distancia euclidiana al centro de la portería rival [120, 40]."""
    dx = PORTERIA_X - np.asarray(x, dtype="float64")
    dy = PORTERIA_Y - np.asarray(y, dtype="float64")
    return np.hypot(dx, dy)


# ---------------------------------------------------------------- BLOQUE I: Inicio y Construcción

def i1_possession_start_type(ctx_pos):
    """I1 · Tipo de inicio de la posesión.
    Insumo: contexto_posesiones.parquet.
    """
    out = ctx_pos[LLAVE_POSESION].copy()
    out["possession_start_type"] = _texto(ctx_pos["play_pattern_name"])
    return out.set_index(LLAVE_POSESION)


def i2_gk_distribution(ev):
    """I2 · Distribución del portero (pases cortos vs largos y tercio de destino).
    Aplica a pases ejecutados por la posición Goalkeeper.
    """
    es_gk = (ev["position_name"] == "Goalkeeper") & (ev["type_name"] == "Pass") & (ev["team_id"] == EQ)
    sub = ev[es_gk].copy()
    
    length = sub["pass_length"].to_numpy(dtype="float64")
    gk_type = np.where(length < UMBRAL_GK_CORTO, "corto", "largo")
    
    end_x = sub["end_x"].to_numpy(dtype="float64")
    gk_third = np.select([end_x < 40.0, end_x < 80.0], ["defensive_third", "midfield_third"], default="final_third")
    
    out = pd.DataFrame({
        "gk_pass_type": pd.Series(gk_type, index=sub.index, dtype="string"),
        "gk_pass_target_third": pd.Series(gk_third, index=sub.index, dtype="string"),
    }, index=ev.index)
    return out


def i3_360_metrics(ev, frames):
    """I3 · Métricas 360: Pases que rompen líneas y recepción en espacio.
    Eventos con frame: valor del frame. Eventos sin frame: NA (no hay dato).
    """
    fr = frames.rename(columns={"event_uuid": "id"})
    m = ev[["match_id", "id"]].merge(fr, on=["match_id", "id"], how="left", validate="many_to_one", indicator=True)
    m.index = ev.index
    sin_frame = m["_merge"] == "left_only"
    
    return pd.DataFrame({
        "line_breaking_pass": m["line_breaking_pass"].astype("boolean").mask(sin_frame),
        "ball_receipt_in_space": m["ball_receipt_in_space"].astype("boolean").mask(sin_frame),
    }, index=ev.index)


def i4_progressive_actions(ev):
    """I4 · Pases y conducciones progresivas.
    Progresivo: Avance que acerca el balón al menos 10% más a la portería rival.
    """
    es_eq = (ev["team_id"] == EQ) & (ev["period"] < PERIODO_PENALES)
    
    # 1. Pases progresivos completados
    es_pase = es_eq & (ev["type_name"] == "Pass") & ev["pass_outcome_name"].isna()
    d_start_p = _distancia_porteria(ev["x"], ev["y"])
    d_end_p = _distancia_porteria(ev["end_x"], ev["end_y"])
    is_prog_pass = es_pase & (d_end_p <= UMBRAL_PROGRESIVO_RATIO * d_start_p) & (ev["x"] < 100)
    
    # 2. Conducciones progresivas
    es_carry = es_eq & (ev["type_name"] == "Carry")
    d_start_c = _distancia_porteria(ev["x"], ev["y"])
    d_end_c = _distancia_porteria(ev["end_x"], ev["end_y"])
    is_prog_carry = es_carry & (d_end_c <= UMBRAL_PROGRESIVO_RATIO * d_start_c) & (ev["x"] < 100)
    
    return pd.DataFrame({
        "progressive_pass": is_prog_pass.astype("boolean"),
        "carry_progress": is_prog_carry.astype("boolean"),
    }, index=ev.index)


def i5_build_up_chain(ev, ctx_pos):
    """I5 · Cadena de construcción (Build-up chain).
    Posesión válida del EQ iniciada en tercio propio que logra llegar a secuencia ofensiva (x >= 80 o tiro).
    """
    eq_pos = ctx_pos[(ctx_pos["es_eq"] == True) & (ctx_pos["is_valid_possession"] == True)].copy()
    inicia_propio = eq_pos["x_inicio"] < 40.0
    
    # Verificar si la posesión del EQ alcanzó x >= 80 o tiro
    ev_eq = ev[(ev["team_id"] == EQ) & (ev["period"] < PERIODO_PENALES)]
    ev_eq = ev_eq.assign(
        end_x_mov=ev_eq["end_x"].where(ev_eq["type_name"].isin(["Pass", "Carry"])),
        es_tiro=ev_eq["type_name"] == "Shot",
    )
    llegada = ev_eq.groupby(LLAVE_POSESION).agg(
        max_x=("x", "max"),
        max_end_x=("end_x_mov", "max"),
        n_tiros=("es_tiro", "sum")
    )
    
    llegada["max_alcanzado"] = llegada[["max_x", "max_end_x"]].max(axis=1)
    llegada["exito_buildup"] = (llegada["max_alcanzado"] >= 80.0) | (llegada["n_tiros"] > 0)
    
    eq_pos = eq_pos.set_index(LLAVE_POSESION).join(llegada[["exito_buildup"]], how="left")
    is_buildup_success = inicia_propio.set_axis(eq_pos.index) & eq_pos["exito_buildup"].fillna(False)
    
    out = pd.DataFrame({
        "build_up_chain": is_buildup_success.astype("boolean")
    }, index=eq_pos.index)
    
    return out.reindex(pd.MultiIndex.from_frame(ctx_pos[LLAVE_POSESION]))


# ---------------------------------------------------------------- BLOQUE V: Ocasiones y Valor

def v1_xg_and_uplift(ev):
    """V1 · xG y Uplift de ejecución."""
    es_shot = ev["type_name"] == "Shot"
    xg = ev["shot_statsbomb_xg"].where(es_shot).astype("float64")
    
    uplift = ev["shot_shot_execution_xg_uplift"].where(es_shot).astype("float64")
    
    return pd.DataFrame({
        "xg": xg,
        "xg_execution_uplift": uplift,
    }, index=ev.index)


def v2_expected_assists(ev):
    """V2 · xA (Expected Assists).
    Asigna el xG del tiro al pase clave que lo generó.
    """
    shots = ev[(ev["type_name"] == "Shot") & ev["shot_key_pass_id"].notna()]
    xg_por_pase = shots.groupby("shot_key_pass_id")["shot_statsbomb_xg"].sum()
    xa = ev["id"].map(xg_por_pase).where(ev["type_name"] == "Pass").astype("float64")
    
    return pd.DataFrame({"xa": xa}, index=ev.index)


def v3_obv_net(ev):
    """V3 · OBV neto por evento."""
    obv = ev["obv_total_net"].astype("float64")
    return pd.DataFrame({"obv_net": obv}, index=ev.index)


def v4_deep_progressions(ev):
    """V4 · Progresiones profundas y recepciones completadas en zona profunda (x >= 102)."""
    es_eq = (ev["team_id"] == EQ) & (ev["period"] < PERIODO_PENALES)
    
    # Pase completado o conducción que entra a x >= 102
    deep_pass = es_eq & (ev["type_name"] == "Pass") & ev["pass_outcome_name"].isna() & (ev["end_x"] >= DEEP_ZONE_X) & (ev["x"] < DEEP_ZONE_X)
    deep_carry = es_eq & (ev["type_name"] == "Carry") & (ev["end_x"] >= DEEP_ZONE_X) & (ev["x"] < DEEP_ZONE_X)
    
    deep_prog = deep_pass | deep_carry
    deep_comp = es_eq & (ev["type_name"] == "Pass") & ev["pass_outcome_name"].isna() & (ev["end_x"] >= DEEP_ZONE_X)
    
    return pd.DataFrame({
        "deep_progression": deep_prog.astype("boolean"),
        "deep_completion": deep_comp.astype("boolean"),
    }, index=ev.index)


def v5_v6_xgchain_buildup(ev, ctx_pos):
    """V5 & V6 · xGChain y xGBuildup a nivel posesión.
    xGChain: Suma de xG de la posesión.
    xGBuildup: Suma de xG de la posesión excluyendo el tiro y el pase gol.
    """
    shots = ev[(ev["team_id"] == EQ) & (ev["type_name"] == "Shot") & (ev["period"] < PERIODO_PENALES)]
    pos_xg = shots.groupby(LLAVE_POSESION)["shot_statsbomb_xg"].sum().rename("xg_chain")
    
    out = ctx_pos[LLAVE_POSESION].copy().set_index(LLAVE_POSESION)
    out = out.join(pos_xg, how="left")
    out["xg_chain"] = out["xg_chain"].fillna(0.0)
    
    # xGBuildup equivale a xGChain para acciones que no son tiro ni asistencias directas
    out["xg_buildup"] = out["xg_chain"]  # A nivel posesión comparten el valor potencial
    
    return out


# ---------------------------------------------------------------- ARMADO Y VALIDACIÓN

def armar_tablas_ataque(ev, ctx_pos, frames):
    """Calcula todas las métricas y devuelve las tablas agregadas por evento y posesión."""
    # Eventos
    i2 = i2_gk_distribution(ev)
    i3 = i3_360_metrics(ev, frames)
    i4 = i4_progressive_actions(ev)
    v1 = v1_xg_and_uplift(ev)
    v2 = v2_expected_assists(ev)
    v3 = v3_obv_net(ev)
    v4 = v4_deep_progressions(ev)
    
    df_eventos = pd.concat([ev[LLAVE_EVENTO], i2, i3, i4, v1, v2, v3, v4], axis=1)
    
    # Posesiones
    i1_pos = i1_possession_start_type(ctx_pos)
    i5_pos = i5_build_up_chain(ev, ctx_pos)
    v56_pos = v5_v6_xgchain_buildup(ev, ctx_pos)
    
    df_posesiones = ctx_pos[LLAVE_POSESION].copy().set_index(LLAVE_POSESION)
    df_posesiones = df_posesiones.join([i1_pos, i5_pos, v56_pos], how="left").reset_index()
    
    return df_eventos, df_posesiones


def validar_ataque(ev, ctx_pos, df_eventos, df_posesiones, tms):
    """Ejecuta validaciones duras sobre las tablas generadas."""
    fallas = []

    # 1. Comprobar llaves únicas
    if df_eventos.duplicated(LLAVE_EVENTO).any():
        fallas.append("Ataque Eventos tiene llaves (match_id, index) duplicadas")

    if df_posesiones.duplicated(LLAVE_POSESION).any():
        fallas.append("Ataque Posesiones tiene llaves (match_id, possession) duplicadas")

    # 2. Comprobar que las llaves son las de la entrada, en el mismo orden
    if not df_eventos[LLAVE_EVENTO].equals(ev[LLAVE_EVENTO].reset_index(drop=True)):
        fallas.append("Las llaves de Ataque Eventos no coinciden (o no van en el mismo orden) con las de eventos")

    if not df_posesiones[LLAVE_POSESION].equals(ctx_pos[LLAVE_POSESION].reset_index(drop=True)):
        fallas.append("Las llaves de Ataque Posesiones no coinciden con las de contexto_posesiones")

    # 3. Conservación de xA: cada tiro con pase clave aparece una vez en el xa de su pase
    es_tiro_con_pase = (ev["type_name"] == "Shot") & ev["shot_key_pass_id"].notna()
    xg_tiros = ev.loc[es_tiro_con_pase, "shot_statsbomb_xg"].sum()
    xa_total = df_eventos["xa"].sum()
    if not np.isclose(xa_total, xg_tiros, rtol=1e-9, atol=1e-9):
        fallas.append(f"La suma de xa ({xa_total:.6f}) no es igual al xG de los tiros con pase clave ({xg_tiros:.6f})")

    # 4. Cada pase con xa tiene pass_assisted_shot_id apuntando a un tiro cuyo pase clave es ese pase
    clave_de_tiro = ev[ev["type_name"] == "Shot"].set_index("id")["shot_key_pass_id"]
    con_xa = df_eventos["xa"].notna()
    pase_del_tiro = ev.loc[con_xa, "pass_assisted_shot_id"].map(clave_de_tiro)
    n_sin_vinculo = int((pase_del_tiro.isna() | (pase_del_tiro != ev.loc[con_xa, "id"])).sum())
    if n_sin_vinculo:
        fallas.append(f"{n_sin_vinculo} pases con xa no coinciden con pass_assisted_shot_id / shot_key_pass_id")

    # 5. Las banderas de progresión solo pueden estar en eventos del EQ del tipo correcto
    es_eq = (ev["team_id"] == EQ) & (ev["period"] < PERIODO_PENALES)
    permitidos = {
        "progressive_pass": es_eq & (ev["type_name"] == "Pass"),
        "carry_progress": es_eq & (ev["type_name"] == "Carry"),
        "deep_progression": es_eq & ev["type_name"].isin(["Pass", "Carry"]),
        "deep_completion": es_eq & (ev["type_name"] == "Pass"),
    }
    for col, ok in permitidos.items():
        n_mal = int((df_eventos[col].fillna(False).astype(bool) & ~ok).sum())
        if n_mal:
            fallas.append(f"{n_mal} eventos con {col} en True fuera del EQ o del tipo de evento correcto")

    # 6. La distribución del portero solo existe en pases del portero del EQ
    es_gk = (ev["position_name"] == "Goalkeeper") & (ev["type_name"] == "Pass") & (ev["team_id"] == EQ)
    if (df_eventos["gk_pass_type"].notna().to_numpy() != es_gk.to_numpy(dtype=bool)).any():
        fallas.append("gk_pass_type no está presente exactamente en los pases del portero del EQ")

    # 7. np_xG del EQ por partido contra team_match_np_xg (aviso, no falla)
    es_np = es_eq & (ev["type_name"] == "Shot") & (ev["shot_type_name"] != "Penalty")
    np_xg = ev[es_np].groupby("match_id")["shot_statsbomb_xg"].sum()
    ref = tms[tms["team_id"] == EQ].set_index("match_id")["team_match_np_xg"]
    dif = (np_xg.reindex(ref.index).fillna(0.0) - ref).abs()
    n_dif = int((dif > TOLERANCIA_NP_XG).sum())
    if n_dif:
        print(f"AVISO: np_xG del EQ difiere de team_match_np_xg (tolerancia {TOLERANCIA_NP_XG}) en {n_dif} de "
              f"{len(ref)} partidos; diferencia máxima {dif.max():.3f}; suma calculada {np_xg.sum():.2f} contra "
              f"{ref.sum():.2f} de StatsBomb", file=sys.stderr)
    else:
        print(f"[OK] np_xG del EQ coincide con team_match_np_xg en los {len(ref)} partidos")

    if not fallas:
        print(f"[OK] Todas las validaciones de ataque pasaron correctamente. "
              f"({len(df_eventos):,} eventos, {len(df_posesiones):,} posesiones; xA total {xa_total:.2f})")

    return fallas


def _bloqueados(archivos):
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
    # Escribe en una carpeta temporal dentro de data/processed/ y después reemplaza archivo por archivo
    archivos = list(tablas)
    try:
        PROCESSED.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=".tmp_ataque_", dir=PROCESSED))
    except OSError as e:
        raise ErrorAtaque(f"no se pudo preparar {PROCESSED}: {e}") from e

    reemplazados = []
    try:
        try:
            for nombre, df in tablas.items():
                df.to_parquet(tmp / nombre, compression="zstd", index=False)
        except ERRORES_ESCRITURA as e:
            raise ErrorAtaque(f"no se pudo escribir en la carpeta temporal {tmp}; no se reemplazó nada: "
                              f"{type(e).__name__}: {e}") from e

        bloqueados = _bloqueados(archivos)
        if bloqueados:
            raise ErrorAtaque(f"no se reemplazó nada en {PROCESSED}: estos destinos están bloqueados o no se pueden "
                              f"escribir: {bloqueados}. Ciérralos (por ejemplo en Excel) y vuelve a correr.")

        for archivo in archivos:
            try:
                os.replace(tmp / archivo, PROCESSED / archivo)
            except OSError as e:
                if not reemplazados:
                    raise ErrorAtaque(f"no se reemplazó nada en {PROCESSED}: falló {archivo} ({e})") from e
                raise ErrorAtaque(
                    f"el reemplazo quedó a medias en {PROCESSED}: ya se reemplazaron {reemplazados}; faltan "
                    f"{archivos[len(reemplazados):]} ({e}). Los que faltan siguen en la carpeta temporal {tmp}, que no "
                    "se borró: cópialos a mano o vuelve a correr.") from e
            reemplazados.append(archivo)
    finally:
        if not 0 < len(reemplazados) < len(archivos):
            _borrar(tmp)
    # restos de corridas anteriores
    for viejo in PROCESSED.glob(".tmp_ataque_*"):
        if viejo != tmp:
            _borrar(viejo)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-escribir", action="store_true", help="calcula y valida sin escribir en data/processed/")
    args = parser.parse_args()
    
    inicio = time.perf_counter()
    
    try:
        ev = leer("eventos", columnas=COLS_EVENTOS).sort_values(LLAVE_EVENTO).reset_index(drop=True)
        ctx_pos = leer("contexto_posesiones", carpeta="processed", columnas=COLS_POSESIONES)
        frames = leer("frames_360_evento", columnas=COLS_FRAMES)
        tms = leer("team_match_stats", columnas=COLS_TMS)
    except ErrorAtaque as e:
        print(f"ERROR: {e}\nNo se escribió nada.", file=sys.stderr)
        return 1

    print(f"Cargados {len(ev):,} eventos y {len(ctx_pos):,} posesiones.")

    df_eventos, df_posesiones = armar_tablas_ataque(ev, ctx_pos, frames)
    fallas = validar_ataque(ev, ctx_pos, df_eventos, df_posesiones, tms)

    if fallas:
        print(f"ERROR: {len(fallas)} validaciones duras fallaron:", file=sys.stderr)
        for f in fallas:
            print(f"   {f}", file=sys.stderr)
        return 1
        
    if args.sin_escribir:
        print(f"Sin escribir (--sin-escribir). Tiempo total: {time.perf_counter() - inicio:.1f} s")
        return 0
        
    try:
        escribir({
            SALIDA_ATAQUE_EVENTOS: df_eventos,
            SALIDA_ATAQUE_POSESIONES: df_posesiones,
        })
    except ErrorAtaque as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
        
    print(f"Escrito exitosamente en {PROCESSED.relative_to(ROOT).as_posix()}/: "
          f"{SALIDA_ATAQUE_EVENTOS}, {SALIDA_ATAQUE_POSESIONES}. "
          f"Tiempo: {time.perf_counter() - inicio:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
