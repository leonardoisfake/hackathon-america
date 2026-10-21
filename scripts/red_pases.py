import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from mplsoccer import Pitch

AQUI = Path(__file__).resolve().parent
ARCHIVO = "eventos_parquet"
TORNEOS = ["Apertura 2023", "Apertura 2024", "Clausura 2024", "Clausura 2025"]
CARPETA_SALIDA = AQUI / "graficas"
MIN_PASES_JUGADOR = 100
MIN_PASES_ENLACE = 15

COLUMNAS = ["match_id", "id", "torneo", "period", "type_name", "team_name", "player_name", "es_equipo_analizado",
            "x", "y", "x_eq", "y_eq", "end_x", "end_y", "duel_type_name", "pass_type_name", "pass_outcome_name",
            "pass_completed", "pass_recipient_name", "shot_outcome_name", "shot_statsbomb_xg"]


def buscar_archivo():
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(ARCHIVO)
    for candidato in [ruta, AQUI / ruta, Path.cwd() / ruta]:
        if candidato.is_file():
            return candidato
    sys.exit(f"No encuentro '{ruta}'. Ponlo junto al script o pasa la ruta: python 5_red_pases.py mi_archivo.parquet")


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


# 5. Red de pases
fig, axs = cuadricula(f"Red de pases de {equipo}", (18, 12))
pitch_r = Pitch(pitch_type="statsbomb", line_color="#555")
for ax, t in zip(axs, torneos):
    d = por_torneo[t]
    pases = d[(d["type_name"] == "Pass") & d["es_equipo_analizado"]]
    completados = pases[(pases["pass_completed"].fillna(False).astype(bool)) & pases["pass_recipient_name"].notna()]

    posiciones = completados.groupby("player_name").agg(x=("x_eq", "mean"), y=("y_eq", "mean"), count=("x_eq", "count"))
    posiciones = posiciones[posiciones["count"] >= MIN_PASES_JUGADOR]

    enlaces = (completados.groupby(["player_name", "pass_recipient_name"]).id.count().reset_index()
               .rename(columns={"player_name": "pasador", "pass_recipient_name": "receptor", "id": "pass_count"}))
    enlaces = enlaces.merge(posiciones[["x", "y"]], left_on="pasador", right_index=True)
    enlaces = enlaces.merge(posiciones[["x", "y"]], left_on="receptor", right_index=True, suffixes=["", "_end"])
    enlaces = enlaces[enlaces["pass_count"] >= MIN_PASES_ENLACE]

    pitch_r.draw(ax=ax)
    pitch_r.lines(enlaces.x, enlaces.y, enlaces.x_end, enlaces.y_end, lw=enlaces.pass_count / enlaces.pass_count.max() * 7,
                  color="#1f4e9c", alpha=.5, ax=ax, zorder=1)
    pitch_r.scatter(posiciones.x, posiciones.y, s=posiciones["count"] / posiciones["count"].max() * 900 + 60,
                    color="#57920f", edgecolors="black", ax=ax, zorder=2)
    for jugador, r in posiciones.iterrows():
        pitch_r.annotate(jugador.split()[0], xy=(r.x, r.y), ax=ax, ha="center", va="center", fontsize=8, zorder=3)
    titulo_panel(ax, t)
fig.text(0.5, 0.05, f"Posición promedio del torneo. Jugadores con al menos {MIN_PASES_JUGADOR} pases completados y "
         f"conexiones de al menos {MIN_PASES_ENLACE} pases. Grosor y tamaño relativos a cada torneo.", ha="center", fontsize=11)
guardar(fig, "5_red_pases.png")

plt.show()