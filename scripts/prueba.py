import pandas as pd
dm = pd.read_parquet("data/processed/jugadores/diagnostico_minutos.parquet")
r = dm[(dm["dif"].abs() > 1.5) & (dm["match_id"] != 3918375)]
pos = pd.read_parquet("data/interim/posiciones.parquet")
cols = ["match_id", "player_id", "posicion_idx", "from", "to", "from_period", "to_period", "start_reason", "end_reason"]
print(pos.merge(r[["match_id", "player_id"]], on=["match_id", "player_id"])[cols].sort_values(["match_id", "posicion_idx"]).to_string(index=False))