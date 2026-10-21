import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mplsoccer import Radar

AQUI = Path(__file__).resolve().parent
EQUIPO_ID = 1229
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
N_JUGADORES = 11
MIN_MINUTOS_ESCALA = 300
CARPETA_SALIDA = AQUI / "graficas"

BUSCAR_STATS = ["player_match_stats.parquet", "player_match_stats"]
BUSCAR_POSICIONES = ["posiciones.parquet", "posiciones"]
BUSCAR_TORNEOS = ["eventos_parquet", "eventos.parquet", "partidos.parquet", "partidos"]
CARPETAS = [AQUI, Path.cwd(), AQUI / "data" / "interim", AQUI / "data" / "raw" / "parquet"]

ROL_POR_POSITION_ID = {
    1: "Portero",
    3: "Defensa central", 4: "Defensa central", 5: "Defensa central",
    2: "Lateral / Carrilero", 6: "Lateral / Carrilero", 7: "Lateral / Carrilero", 8: "Lateral / Carrilero",
    9: "Pivote", 10: "Pivote", 11: "Pivote",
    12: "Interior / Ofensivo", 13: "Interior / Ofensivo", 14: "Interior / Ofensivo", 15: "Interior / Ofensivo",
    16: "Interior / Ofensivo", 18: "Interior / Ofensivo", 19: "Interior / Ofensivo", 20: "Interior / Ofensivo",
    17: "Extremo / Delantero", 21: "Extremo / Delantero", 22: "Extremo / Delantero",
    23: "Extremo / Delantero", 24: "Extremo / Delantero", 25: "Extremo / Delantero",
}

# (columna, etiqueta, tipo)  tipo: "total" = suma de todo el torneo, "ratio" = media ponderada por minutos,
# "vallas" = número de partidos con 0 goles recibidos
METRICAS = {
    "Portero": [
        ("player_match_save_ratio", "% paradas", "ratio"),
        ("player_match_gsaa", "Goles evitados\n(PSxG)", "total"),
        ("player_match_passing_ratio", "% pases\ncompletados", "ratio"),
        ("player_match_claim_success", "% balones\natrapados", "ratio"),
        ("player_match_goals_conceded", "Vallas\ninvictas", "vallas"),
    ],
    "Defensa central": [
        ("player_match_successful_aerials", "Duelos aéreos\nganados", "total"),
        ("player_match_clearances", "Despejes", "total"),
        ("player_match_interceptions", "Intercepciones", "total"),
        ("player_match_passing_ratio", "% pases\ncompletados", "ratio"),
        ("player_match_challenge_ratio", "% duelos\ndefensivos ganados", "ratio"),
    ],
    "Lateral / Carrilero": [
        ("player_match_crosses_into_box", "Centros al\nárea", "total"),
        ("player_match_successful_crosses", "Centros\nexitosos", "total"),
        ("player_match_dribbles", "Regates\ncompletados", "total"),
        ("player_match_ball_recoveries", "Recuperaciones", "total"),
        ("player_match_key_passes", "Pases clave", "total"),
    ],
    "Pivote": [
        ("player_match_lbp_completed", "Pases que rompen\nlíneas", "total"),
        ("player_match_ball_recoveries", "Recuperaciones", "total"),
        ("player_match_passing_ratio", "% pases\ncompletados", "ratio"),
        ("player_match_tackles", "Entradas con\néxito", "total"),
        ("player_match_challenge_ratio", "% duelos\nganados", "ratio"),
    ],
    "Interior / Ofensivo": [
        ("player_match_assists", "Asistencias", "total"),
        ("player_match_key_passes", "Pases clave", "total"),
        ("player_match_op_f3_passes", "Pases último\ntercio", "total"),
        ("player_match_deep_progressions", "Progresiones\nprofundas", "total"),
        ("player_match_xa", "xA (ocasiones\ngeneradas)", "total"),
    ],
    "Extremo / Delantero": [
        ("player_match_goals", "Goles", "total"),
        ("player_match_np_xg", "xG (sin penales)", "total"),
        ("player_match_np_shots_on_target", "Remates a\npuerta", "total"),
        ("player_match_dribbles", "Regates con\néxito", "total"),
        ("player_match_touches_inside_box", "Toques en el\nárea", "total"),
    ],
}
COLOR_ROL = {"Portero": "#7a5195", "Defensa central": "#0F2A52", "Lateral / Carrilero": "#2a7f62",
             "Pivote": "#b5651d", "Interior / Ofensivo": "#B8912B", "Extremo / Delantero": "#B40B0E"}
MINUTOS = "player_match_minutes"


def buscar(nombres, descripcion):
    for carpeta in CARPETAS:
        for nombre in nombres:
            ruta = carpeta / nombre
            if ruta.is_file():
                return ruta
    sys.exit(f"No encuentro {descripcion}. Busqué {nombres} en: {[str(c) for c in CARPETAS]}")


def corto_nombre(n):
    p = str(n).split()
    return p[0] if len(p) == 1 else f"{p[0]} {p[-1]}"


columnas_usadas = sorted({c for ms in METRICAS.values() for c, _, _ in ms})
cols = ["match_id", "team_id", "player_id", "player_name", MINUTOS] + columnas_usadas
ruta_stats = buscar(BUSCAR_STATS, "player_match_stats")
faltan = [c for c in cols if c not in pd.read_parquet(ruta_stats).columns]
if faltan:
    sys.exit(f"A {ruta_stats.name} le faltan columnas: {faltan}")
stats = pd.read_parquet(ruta_stats, columns=cols)
stats = stats[stats["team_id"].astype("Int64") == EQUIPO_ID].copy()
if stats.empty:
    sys.exit(f"No hay filas del equipo {EQUIPO_ID} en {ruta_stats.name}.")
for c in [MINUTOS] + columnas_usadas:
    stats[c] = pd.to_numeric(stats[c], errors="coerce").astype(float)
stats["player_id"] = stats["player_id"].astype("int64")
stats["match_id"] = stats["match_id"].astype("int64")
stats["player_name"] = stats["player_name"].astype(str)

ruta_torneos = buscar(BUSCAR_TORNEOS, "el archivo que asigna torneo a cada match_id")
mapa = pd.read_parquet(ruta_torneos, columns=["match_id", "torneo"]).drop_duplicates("match_id")
mapa["torneo"] = mapa["torneo"].astype(str)
mapa["match_id"] = mapa["match_id"].astype("int64")
stats = stats.merge(mapa, on="match_id", how="left").dropna(subset=["torneo"])

ruta_pos = buscar(BUSCAR_POSICIONES, "posiciones")
pos = pd.read_parquet(ruta_pos, columns=["match_id", "team_id", "player_id", "position_id", "from", "to"])
pos = pos[pos["team_id"].astype("Int64") == EQUIPO_ID].dropna(subset=["position_id"]).copy()
pos["match_id"] = pos["match_id"].astype("int64")
pos["player_id"] = pos["player_id"].astype("int64")
pos["rol"] = pos["position_id"].astype(int).map(ROL_POR_POSITION_ID)
pos = pos.dropna(subset=["rol"])
inicio = pd.to_timedelta(pos["from"], errors="coerce").dt.total_seconds()
fin = pd.to_timedelta(pos["to"], errors="coerce").dt.total_seconds()
pos["segundos"] = (fin.fillna(95 * 60) - inicio).clip(lower=0)
pos = pos.merge(mapa, on="match_id", how="left").dropna(subset=["torneo"])
rol_principal = (pos.groupby(["torneo", "player_id", "rol"])["segundos"].sum().reset_index()
                 .sort_values("segundos", ascending=False).drop_duplicates(["torneo", "player_id"])
                 .set_index(["torneo", "player_id"])["rol"])


def agregar(d):
    minutos = d[MINUTOS].sum()
    fila = {"minutos": minutos, "partidos": d["match_id"].nunique()}
    for rol, ms in METRICAS.items():
        for col, _, tipo in ms:
            if tipo == "total":
                fila[col] = d[col].sum(min_count=1)
            elif tipo == "ratio":
                v = d[col]
                peso = d.loc[v.notna(), MINUTOS]
                fila[col] = (v.dropna() * peso).sum() / peso.sum() if peso.sum() > 0 else np.nan
            else:
                v = d[col].dropna()
                fila[col] = float((v == 0).sum()) if len(v) else np.nan
    return pd.Series(fila)


tabla = (stats.groupby(["torneo", "player_id"]).apply(agregar, include_groups=False).reset_index())
nombres = stats.groupby("player_id")["player_name"].agg(lambda s: s.iloc[0]).map(corto_nombre)
tabla["nombre"] = tabla["player_id"].map(nombres)
tabla["rol"] = [rol_principal.get((t, p)) for t, p in zip(tabla["torneo"], tabla["player_id"])]

torneos = [t for t in TORNEOS if t in set(tabla["torneo"])]
for t in set(TORNEOS) - set(torneos):
    print(f"Aviso: no hay datos del torneo '{t}'.")
if not torneos:
    sys.exit(f"Ningún torneo coincide. Torneos en los datos: {sorted(tabla['torneo'].unique())}")

limites = {}
pool = tabla[(tabla["minutos"] >= MIN_MINUTOS_ESCALA) & tabla["rol"].notna()]
for rol, ms in METRICAS.items():
    sub = pool[pool["rol"] == rol]
    for col, _, tipo in ms:
        v = sub[col].dropna()
        if v.empty:
            limites[(rol, col)] = (0.0, 1.0)
            continue
        lo = 0.0 if tipo in ("total", "vallas") else float(v.min())
        if col == "player_match_gsaa":
            lo = min(0.0, float(v.min()))
        hi = float(v.max())
        pad = (hi - lo) * 0.08 or 0.1
        limites[(rol, col)] = (lo - (pad if lo < 0 or tipo == "ratio" else 0), hi + pad)

radares = {}
for rol, ms in METRICAS.items():
    lo = [limites[(rol, c)][0] for c, _, _ in ms]
    hi = [limites[(rol, c)][1] for c, _, _ in ms]
    radares[rol] = Radar([e for _, e, _ in ms], lo, hi, round_int=[False] * len(ms),
                         num_rings=4, ring_width=1, center_circle_radius=1)


def formato(valor, tipo, col):
    if pd.isna(valor):
        return "s/d"
    if tipo == "ratio":
        return f"{valor:.0%}"
    return f"{valor:.0f}" if abs(valor - round(valor)) < 1e-9 else f"{valor:.1f}"


CARPETA_SALIDA.mkdir(exist_ok=True)
for t in torneos:
    d = tabla[tabla["torneo"] == t].sort_values("minutos", ascending=False).head(N_JUGADORES)
    d = d[d["rol"].notna()]
    n = len(d)
    fig, axs = plt.subplots(3, 4, figsize=(18, 15.5))
    fig.suptitle(f"América - {t}", fontsize=26, fontweight="bold", y=0.985)
    fig.text(0.5, 0.947, f"Los {n} jugadores con más minutos, con las métricas de su posición principal", ha="center", fontsize=14)
    plano = axs.flatten()

    for ax, (_, fila) in zip(plano, d.iterrows()):
        rol = fila["rol"]
        ms = METRICAS[rol]
        radar = radares[rol]
        color = COLOR_ROL[rol]
        valores = []
        for c, _, _ in ms:
            lo, hi = limites[(rol, c)]
            v = fila[c] if pd.notna(fila[c]) else lo
            valores.append(min(max(v, lo), hi))
        radar.setup_axis(ax=ax)
        radar.draw_circles(ax=ax, facecolor="#f2f2f2", edgecolor="#cccccc")
        res = radar.draw_radar(valores, ax=ax, kwargs_radar={"facecolor": color, "alpha": 0.6},
                               kwargs_rings={"facecolor": color, "alpha": 0.1})
        radar.draw_param_labels(ax=ax, fontsize=8)
        for (x, y), (c, _, tipo) in zip(res[2], ms):
            ax.text(x, y, formato(fila[c], tipo, c), fontsize=8, ha="center", va="center", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=color, lw=0.6, alpha=0.9))
        ax.set_title(f"{fila['nombre']}\n{rol}\n{int(fila['partidos'])} partidos, {int(fila['minutos'])} min",
                     fontsize=11.5, fontweight="bold", y=1.07)

    for ax in plano[n:]:
        ax.axis("off")
    if n < len(plano):
        plano[n].text(0.0, 0.5, "Cada jugador se mide en la posición\nque más minutos jugó en el torneo.\n\n"
                      "Los conteos son el total de toda la\ntemporada y los porcentajes están\nponderados por minutos.\n\n"
                      "La escala es la misma para los 4 torneos\ny se calcula con los jugadores de esa\nposición con al menos "
                      f"{MIN_MINUTOS_ESCALA} min en un torneo.", fontsize=10.5, va="center", ha="left")

    ruta_png = CARPETA_SALIDA / f"radar_posiciones_{t.replace(' ', '_')}.png"
    fig.savefig(ruta_png, dpi=130, bbox_inches="tight")
    print("Guardado:", ruta_png)

plt.show()