import sys
from pathlib import Path
 
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import pandas as pd
from matplotlib.lines import Line2D
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
    sys.exit(f"No encuentro '{ruta}'. Ponlo junto al script o pasa la ruta: python 2_mapa_pases.py mi_archivo.parquet")
 
 
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
 
 
pitch = Pitch(pitch_type="statsbomb", pitch_color="#101010", line_color="#8a97a3", line_zorder=3)
cmap_flujo = LinearSegmentedColormap.from_list("flujo", ["#101010", "#1f3b63", "#2f6f9f", "#4fa3c7"])
 
fig, axs = cuadricula(f"Hacia dónde circula el balón - {equipo}", (18, 11))
fig.set_facecolor("#101010")
fig.suptitle(f"Hacia dónde circula el balón - {equipo}", fontsize=22, fontweight="bold", color="white")
for ax, t in zip(axs, torneos):
    d = por_torneo[t]
    pases = d[(d["type_name"] == "Pass") & d["es_equipo_analizado"] & d["pass_outcome_name"].isna()]
    pases = pases.dropna(subset=["x", "y", "end_x", "end_y"])
    pitch.draw(ax=ax)
    stat = pitch.bin_statistic(pases.x, pases.y, statistic="count", bins=(8, 6), normalize=True)
    pitch.heatmap(stat, ax=ax, cmap=cmap_flujo, zorder=1)
    pitch.flow(pases.x, pases.y, pases.end_x, pases.end_y, bins=(8, 6), arrow_type="same", arrow_length=8,
               color="#f4f1de", ax=ax, zorder=4, width=1.4, headwidth=4, headlength=4)
    ax.set_title(f"{t}  ({d['match_id'].nunique()} partidos, {len(pases)} pases completados)", color="white", fontsize=13, pad=8)
    ax.annotate("", xy=(0.62, -0.02), xytext=(0.38, -0.02), xycoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color="#8a97a3", lw=1.5))
 
fig.text(0.5, 0.03, "Cada flecha es la dirección promedio de los pases completados que salen de esa zona; el azul más claro marca las zonas desde donde salen más pases. Ataque de izquierda a derecha.",
         ha="center", color="#c8d0d8", fontsize=11)
guardar(fig, "2_flujo_pases.png")
plt.show()