import sys
from pathlib import Path

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from mplsoccer import Pitch

AQUI = Path(__file__).resolve().parent
ARCHIVO = "eventos_parquet"
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
CARPETA_SALIDA = AQUI / "graficas"

COLUMNAS = ["match_id", "id", "torneo", "period", "type_name", "team_name", "player_name", "es_equipo_analizado",
            "x", "y", "x_eq", "y_eq", "end_x", "end_y", "duel_type_name", "pass_type_name", "pass_outcome_name",
            "pass_completed", "pass_recipient_name", "shot_outcome_name", "shot_statsbomb_xg"]


def buscar_archivo():
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(ARCHIVO)
    for candidato in [ruta, AQUI / ruta, Path.cwd() / ruta]:
        if candidato.is_file():
            return candidato
    sys.exit(f"No encuentro '{ruta}'. Ponlo junto al script o pasa la ruta: python 1_actividad_defensiva.py mi_archivo.parquet")


ruta = buscar_archivo()
disponibles = pd.read_parquet(ruta).columns
faltan = [c for c in COLUMNAS if c not in disponibles]
if faltan:
    sys.exit(f"A {ruta.name} le faltan columnas: {faltan}. Este script espera la tabla limpia 'eventos', no el parquet crudo.")

eventos = pd.read_parquet(ruta, columns=COLUMNAS)
eventos["torneo"] = eventos["torneo"].astype(str)
eventos["es_equipo_analizado"] = eventos["es_equipo_analizado"].fillna(False).astype(bool)
equipo = eventos.loc[eventos["es_equipo_analizado"], "team_name"].iloc[0]

torneos = [t for t in TORNEOS if t in set(eventos["torneo"])]
for t in set(TORNEOS) - set(torneos):
    print(f"Aviso: el torneo '{t}' no está en el archivo (torneos encontrados: {sorted(eventos['torneo'].unique())})")
if not torneos:
    sys.exit("Ningún torneo de la lista coincide con la columna torneo.")

CARPETA_SALIDA.mkdir(exist_ok=True)
por_torneo = {t: eventos[eventos["torneo"] == t] for t in torneos}


def cuadricula(titulo, figsize, **kw):
    fig, axs = plt.subplots(2, 2, figsize=figsize, **kw)
    fig.suptitle(titulo, fontsize=22, fontweight="bold")
    for ax in axs.flat[len(torneos):]:
        ax.axis("off")
    return fig, axs.flat


def titulo_panel(ax, t, extra=""):
    partidos = por_torneo[t]["match_id"].nunique()
    ax.set_title(f"{t}  ({partidos} partidos){extra}", fontsize=14, fontweight="bold")


def guardar(fig, nombre):
    ruta_png = CARPETA_SALIDA / nombre
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    print("Guardado:", ruta_png)


# 1. Actividad defensiva: América vs rival
tipos = ["Pressure", "Foul Committed", "Interception", "Block"]
colores = ["#171832", "#323A60", "#45537F", "#7183A3", "#B5C6D5", "#D3DEE4", "#DEDFE0",
           "#F2BAAD", "#F7A18E", "#F17B67", "#E84335", "#E11F19", "#B40B0E"]
cmap = LinearSegmentedColormap.from_list("statsbomb", colores)
pitch = Pitch(pitch_type="statsbomb", line_zorder=2, line_color="black")

estadisticas = {}
for t, d in por_torneo.items():
    defensivas = d[(d["period"] < 5) & (
        d["type_name"].isin(tipos)
        | ((d["type_name"] == "Duel") & (d["duel_type_name"] == "Tackle"))
        | ((d["type_name"] == "Pass") & (d["pass_type_name"] == "Interception"))
    )].dropna(subset=["x", "y"])
    propias = defensivas[defensivas["es_equipo_analizado"]]
    rival = defensivas[~defensivas["es_equipo_analizado"]]
    s = pitch.bin_statistic(propias.x, propias.y, statistic="count", bins=(6, 5))
    s_rival = pitch.bin_statistic(rival.x, rival.y, statistic="count", bins=(6, 5))
    s["statistic"] = s["statistic"] / s["statistic"].sum() * 100 - s_rival["statistic"] / s_rival["statistic"].sum() * 100
    estadisticas[t] = s
limite = max(np.abs(s["statistic"]).max() for s in estadisticas.values())

fig, axs = cuadricula(f"¿Dónde defiende {equipo} frente a su rival?", (16, 11))
for ax, t in zip(axs, torneos):
    pitch.draw(ax=ax)
    hm = pitch.heatmap(estadisticas[t], ax=ax, cmap=cmap, vmin=-limite, vmax=limite, zorder=1)
    pitch.label_heatmap(estadisticas[t], ax=ax, str_format="{:+.1f}", fontsize=11, fontweight="bold", ha="center", va="center",
                        zorder=3, path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    titulo_panel(ax, t)
cbar = fig.colorbar(hm, ax=list(axs[:len(torneos)]), shrink=0.6, pad=0.02)
cbar.set_ticks([-limite, 0, limite])
cbar.set_ticklabels(["menos que\nel rival", "igual", "más que\nel rival"], fontsize=11)
fig.text(0.5, 0.04, f"Puntos porcentuales: % de las acciones defensivas de {equipo} en cada zona menos el % del rival. "
         "Ataque de izquierda a derecha.", ha="center", fontsize=11)
guardar(fig, "1_actividad_defensiva.png")

plt.show()