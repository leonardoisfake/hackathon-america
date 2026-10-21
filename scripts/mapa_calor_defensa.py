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
    sys.exit(f"No encuentro '{ruta}'. Ponlo junto al script o pasa la ruta: python 3_mapa_calor_defensivo.py mi_archivo.parquet")


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


ACCIONES = ["Ball Recovery", "Duel", "Interception", "Clearance", "Block"]
colores = ["#ffffff", "#fde0c5", "#facba6", "#f59e72", "#f17b50", "#e8553a", "#c8302a", "#8f1d21"]
cmap = LinearSegmentedColormap.from_list("defensivo", colores)
pitch = Pitch(pitch_type="statsbomb", line_zorder=2, line_color="#222222")

estadisticas, totales = {}, {}
for t, d in por_torneo.items():
    acc = d[d["type_name"].isin(ACCIONES) & d["es_equipo_analizado"] & (d["period"] < 5)].dropna(subset=["x", "y"])
    estadisticas[t] = pitch.bin_statistic(acc.x, acc.y, statistic="count", bins=(6, 5), normalize=True)
    totales[t] = len(acc)
vmax = max(s["statistic"].max() for s in estadisticas.values())

fig, axs = cuadricula(f"Acciones defensivas de {equipo}", (16, 11))
for ax, t in zip(axs, torneos):
    pitch.draw(ax=ax)
    hm = pitch.heatmap(estadisticas[t], ax=ax, cmap=cmap, vmin=0, vmax=vmax, zorder=1, edgecolors="white")
    pitch.label_heatmap(estadisticas[t], ax=ax, str_format="{:.0%}", fontsize=12, fontweight="bold", ha="center", va="center",
                        zorder=3, path_effects=[pe.withStroke(linewidth=3, foreground="white")])
    titulo_panel(ax, t, extra=f", {totales[t]} acciones")
cbar = fig.colorbar(hm, ax=list(axs[:len(torneos)]), shrink=0.6, pad=0.02)
cbar.set_ticks([0, vmax])
cbar.set_ticklabels(["menos", "más"], fontsize=12)
fig.text(0.5, 0.04, "Porcentaje de las acciones defensivas del torneo en cada zona (Ball Recovery, Duel, Interception, Clearance, Block). "
         "América ataca de izquierda a derecha.", ha="center", fontsize=11)
guardar(fig, "3_mapa_calor_defensivo.png")
plt.show()