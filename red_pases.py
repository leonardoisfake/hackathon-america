import matplotlib.pyplot as plt
import pandas as pd
from mplsoccer import Pitch

partido = pd.read_parquet("eventos.parquet")

equipo = partido.loc[partido["es_equipo_analizado"], "team_name"].iloc[0]

pases_partido = partido[(partido["type_name"] == "Pass") & (partido["es_equipo_analizado"])]
completados = pases_partido[(pases_partido["pass_completed"] == True) & pases_partido["pass_recipient_name"].notna()]

firstSub = partido[(partido["type_name"] == "Substitution") & (partido["es_equipo_analizado"])]["minute"].min()
if pd.isna(firstSub):
    firstSub = partido["minute"].max() + 1
completados_cambio = completados

average_locations = (completados_cambio.groupby("player_name").agg(x=("x_eq", "mean"), y=("y_eq", "mean"), count=("x_eq", "count")))

pass_between = (completados_cambio.groupby(["player_name", "pass_recipient_name"]).id.count().reset_index() .rename(columns={"player_name": "pasador", "pass_recipient_name": "receptor", "id": "pass_count"}))

pass_between = pass_between.merge(average_locations[["x", "y"]], left_on="pasador", right_index=True)
pass_between = pass_between.merge(average_locations[["x", "y"]], left_on="receptor", right_index=True,suffixes=["", "_end"])
pass_between = pass_between[pass_between["pass_count"] > 1]


pitch = Pitch(pitch_type="statsbomb", line_color="#555")
fig, ax = pitch.draw(figsize=(10, 6.5))
pitch.lines(pass_between.x, pass_between.y, pass_between.x_end, pass_between.y_end,lw=pass_between.pass_count * 0.8, color="#1f4e9c", alpha=.5, ax=ax, zorder=1)
pitch.scatter(average_locations.x, average_locations.y, s=average_locations["count"] * 25,color="#57920f", edgecolors="black", ax=ax, zorder=2)
for jugador, r in average_locations.iterrows():
    pitch.annotate(jugador.split()[0], xy=(r.x, r.y), ax=ax, ha="center", va="center", fontsize=8, zorder=3)
ax.set_title(f"Red de pases de {equipo} hasta el minuto completo")
plt.show()