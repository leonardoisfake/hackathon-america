import math
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from mplsoccer import VerticalPitch

partido = pd.read_parquet("eventos.parquet")
equipo = partido.loc[partido["es_equipo_analizado"], "team_name"].iloc[0]

pases_equipo = partido[(partido["type_name"] == "Pass") & partido["es_equipo_analizado"]]
pases_equipo = pases_equipo.dropna(subset=["x", "y", "end_x", "end_y"])
jugadores = pases_equipo["player_name"].value_counts().index.tolist()

columnas = 4
filas = math.ceil(len(jugadores) / columnas)
pitch = VerticalPitch(pitch_type="statsbomb", goal_type="box", line_color="#888", linewidth=1)
fig, axs = plt.subplots(filas, columnas, figsize=(columnas * 4.2, filas * 6.2))

for ax, jugador in zip(axs.flat, jugadores):
    pases = pases_equipo[pases_equipo["player_name"] == jugador]
    completos = pases[pases["pass_completed"] == True]
    incompletos = pases[pases["pass_completed"] == False]
    pitch.draw(ax=ax)
    pitch.arrows(completos.x, completos.y, completos.end_x, completos.end_y, ax=ax,
                 color="green", alpha=.8, width=1.8, headwidth=4, headlength=4)
    pitch.arrows(incompletos.x, incompletos.y, incompletos.end_x, incompletos.end_y, ax=ax,
                 color="red", alpha=.8, width=1.8, headwidth=4, headlength=4)
    ax.set_title(f"{jugador}\n{len(completos)} completos, {len(incompletos)} incompletos", fontsize=11, fontweight="bold")

for ax in axs.flat[len(jugadores):]:
    ax.axis("off")

leyenda = [Line2D([], [], color="green", lw=3, label="Pases completos"),
           Line2D([], [], color="red", lw=3, label="Pases incompletos")]
fig.legend(handles=leyenda, loc="lower center", ncol=2, fontsize=14, frameon=False)
fig.tight_layout(rect=(0, 0.03, 1, 0.97))
plt.show()