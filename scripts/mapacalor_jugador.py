import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from mplsoccer import Pitch
from scipy.ndimage import gaussian_filter

AQUI = Path(__file__).resolve().parent
EQUIPO_ID = 1229
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
N_JUGADORES = 11
CARPETA_SALIDA = AQUI / "graficas"

BUSCAR_STATS = ["player_match_stats.parquet", "player_match_stats"]
BUSCAR_EVENTOS = ["eventos_parquet", "eventos.parquet"]
CARPETAS = [AQUI, Path.cwd(), AQUI / "data" / "interim", AQUI / "data" / "raw" / "parquet"]

SIN_POSICION = ["Starting XI", "Half Start", "Half End", "Substitution", "Tactical Shift", "Injury Stoppage",
                "Referee Ball-Drop", "Player Off", "Player On", "Bad Behaviour", "Own Goal For", "Own Goal Against"]
COLUMNAS_EVENTOS = ["match_id", "torneo", "period", "type_name", "team_name", "player_id", "player_name",
                    "es_equipo_analizado", "x", "y"]
cmap = LinearSegmentedColormap.from_list("zona", ["#ffffff", "#ffe3d6", "#f9b79c", "#ef7b5c", "#d9382f", "#9e1220"])


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


ruta_ev = buscar(BUSCAR_EVENTOS, "los eventos")
faltan = [c for c in COLUMNAS_EVENTOS if c not in pd.read_parquet(ruta_ev).columns]
if faltan:
    sys.exit(f"A {ruta_ev.name} le faltan columnas: {faltan}. Este script espera la tabla limpia 'eventos'.")
eventos = pd.read_parquet(ruta_ev, columns=COLUMNAS_EVENTOS)
eventos["torneo"] = eventos["torneo"].astype(str)
eventos["es_equipo_analizado"] = eventos["es_equipo_analizado"].fillna(False).astype(bool)
eventos = eventos[eventos["es_equipo_analizado"] & (eventos["period"] < 5) & ~eventos["type_name"].isin(SIN_POSICION)]
eventos = eventos.dropna(subset=["x", "y", "player_id"]).copy()
eventos["player_id"] = eventos["player_id"].astype("int64")
eventos["match_id"] = eventos["match_id"].astype("int64")
equipo = eventos["team_name"].iloc[0]

ruta_stats = buscar(BUSCAR_STATS, "player_match_stats")
cols = ["match_id", "team_id", "player_id", "player_name", "player_match_minutes"]
faltan = [c for c in cols if c not in pd.read_parquet(ruta_stats).columns]
if faltan:
    sys.exit(f"A {ruta_stats.name} le faltan columnas: {faltan}")
stats = pd.read_parquet(ruta_stats, columns=cols)
stats = stats[stats["team_id"].astype("Int64") == EQUIPO_ID].copy()
stats["player_id"] = stats["player_id"].astype("int64")
stats["match_id"] = stats["match_id"].astype("int64")
stats["player_match_minutes"] = pd.to_numeric(stats["player_match_minutes"], errors="coerce")
mapa = eventos[["match_id", "torneo"]].drop_duplicates("match_id")
stats = stats.merge(mapa, on="match_id", how="inner")

torneos = [t for t in TORNEOS if t in set(stats["torneo"])]
for t in set(TORNEOS) - set(torneos):
    print(f"Aviso: no hay datos del torneo '{t}'.")
if not torneos:
    sys.exit(f"Ningún torneo coincide. Torneos en los datos: {sorted(stats['torneo'].unique())}")

pitch = Pitch(pitch_type="statsbomb", line_color="#444444", line_zorder=3, pad_top=2, pad_bottom=2)
CARPETA_SALIDA.mkdir(exist_ok=True)

for t in torneos:
    s = stats[stats["torneo"] == t]
    minutos = s.groupby("player_id")["player_match_minutes"].sum().sort_values(ascending=False).head(N_JUGADORES)
    nombres = s.groupby("player_id")["player_name"].agg(lambda x: x.iloc[0])
    partidos = s.groupby("player_id")["match_id"].nunique()
    ev_t = eventos[eventos["torneo"] == t]

    fig, axs = plt.subplots(3, 4, figsize=(20, 12.5))
    fig.suptitle(f"{equipo} - {t}", fontsize=26, fontweight="bold", y=1.0)
    fig.subplots_adjust(top=0.88)
    fig.text(0.5, 0.935, f"Zonas donde estuvo cada uno de los {len(minutos)} jugadores con más minutos "
             "(posición de sus acciones con balón y sin balón)", ha="center", fontsize=14)
    plano = axs.flatten()

    for ax, (pid, mins) in zip(plano, minutos.items()):
        d = ev_t[ev_t["player_id"] == pid]
        pitch.draw(ax=ax)
        if len(d) >= 5:
            stat = pitch.bin_statistic(d.x, d.y, statistic="count", bins=(48, 32))
            suave = gaussian_filter(stat["statistic"], 2.2)
            suave = np.where(suave < suave.max() * 0.06, np.nan, suave)
            stat["statistic"] = suave
            pitch.heatmap(stat, ax=ax, cmap=cmap, zorder=1, alpha=0.9)
            pitch.scatter(d.x.mean(), d.y.mean(), ax=ax, s=90, color="white", edgecolors="black", linewidth=1.5, zorder=4)
        ax.set_title(f"{corto_nombre(nombres[pid])}\n{int(partidos[pid])} partidos, {int(mins)} min, {len(d)} acciones",
                     fontsize=12, fontweight="bold")

    for ax in plano[len(minutos):]:
        ax.axis("off")
    if len(minutos) < len(plano):
        plano[len(minutos)].text(0.0, 0.5, "Cuanto más oscuro el rojo, más\nacciones del jugador en esa zona\n"
                                 "(cada mapa se mide contra el\npropio jugador).\n\nEl punto blanco es su posición\npromedio.\n\n"
                                 "América ataca de izquierda a derecha.", fontsize=11.5, va="center", ha="left")

    ruta_png = CARPETA_SALIDA / f"mapa_calor_jugadores_{t.replace(' ', '_')}.png"
    fig.savefig(ruta_png, dpi=120, bbox_inches="tight")
    print("Guardado:", ruta_png)

plt.show()