# Inventario de descarga

- Fecha de ejecucion: 2026-10-17 13:12
- Entrenador `manager_id` 1000116, equipo `team_id` 1229
- Temporadas: 108, 235, 281, 317
- Modo: completo
- Partidos en D1: 91

## Esperado contra obtenido

| concepto | esperado | obtenido | estado |
|---|---|---|---|
| partidos | 91 | 91 | ok |
| liguilla | 25 | 25 | ok |
| es_final | 8 | 8 | ok |

## Filas por tabla

| tabla | filas | columnas | mb | archivos |
|---|---|---|---|---|
| partidos | 91 | 65 | 0.1 | partidos.parquet (0.1 MB) |
| events | 317849 | 180 | 60.1 | events__Apertura_2023.parquet (16.1 MB), events__Apertura_2024.parquet (15.4 MB), events__Clausura_2024.parquet (15.2 MB), events__Clausura_2025.parquet (13.3 MB) |
| frames_360 | 283700 | 11 | 39.3 | frames_360.parquet (39.3 MB) |
| lineups | 182 | 6 | 0.2 | lineups.parquet (0.2 MB) |
| team_match_stats | 182 | 207 | 0.3 | team_match_stats.parquet (0.3 MB) |
| player_match_stats | 2817 | 178 | 1.2 | player_match_stats.parquet (1.2 MB) |

Linea base: 2728 filas, 213 columnas, team_match_stats_liga.parquet (1.9 MB). Excluidos por Complete/Normal: 0 (se listan abajo si los hay).

## Partidos por torneo y fase

| torneo | liguilla | regular | es_final |
|---|---|---|---|
| Apertura 2023 | 6 | 17 | 2 |
| Apertura 2024 | 7 | 17 | 2 |
| Clausura 2024 | 6 | 17 | 2 |
| Clausura 2025 | 6 | 15 | 2 |

## Cobertura 360

- Eventos con frame 360 (`id` = `event_uuid`): 283700 de 317849 (89.3%)
- Por partido: minimo 82.7%, maximo 95.0%

## Columnas convertidas a texto

| tabla | columna | motivo |
|---|---|---|
| events | tactics.lineup | lista o dict -> texto JSON |
| events | related_events | lista o dict -> texto JSON |
| events | location | lista o dict -> texto JSON |
| events | defensive_responsibility.categories | lista o dict -> texto JSON |
| events | defensive_responsibility.players | lista o dict -> texto JSON |
| events | pass.end_location | lista o dict -> texto JSON |
| events | carry.end_location | lista o dict -> texto JSON |
| events | shot.end_location | lista o dict -> texto JSON |
| events | shot.freeze_frame | lista o dict -> texto JSON |
| events | goalkeeper.end_location | lista o dict -> texto JSON |
| frames_360 | visible_area | lista o dict -> texto JSON |
| frames_360 | freeze_frame | lista o dict -> texto JSON |
| frames_360 | visible_player_counts | lista o dict -> texto JSON |
| frames_360 | distances_from_edge_of_visible_area | lista o dict -> texto JSON |
| lineups | lineup | lista o dict -> texto JSON |
| lineups | formations | lista o dict -> texto JSON |
| lineups | events | lista o dict -> texto JSON |
| partidos | home_team.managers | lista o dict -> texto JSON |
| partidos | away_team.managers | lista o dict -> texto JSON |

## Partidos excluidos o fallidos

| match_id | fecha | motivo |
|---|---|---|
| 3972023 | 2025-01-17 | excluido: otro manager (Diego Alberto Cervantes Chávez) |
| 3972016 | 2025-01-11 | excluido: otro manager (Diego Alberto Cervantes Chávez) |

## Detalle por partido

| match_id | fecha | torneo | fase | es_final | rival | res | eventos | frames | pct_360 | last_updated_360 | descargado |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3889637 | 2023-07-01 | Apertura 2023 | regular | False | Juárez | 1-2 | 3893 | 3647 | 93.7 | 2023-07-01T14:20:34.669214 | 2026-10-17 |
| 3889660 | 2023-07-16 | Apertura 2023 | regular | False | Puebla | 3-0 | 4133 | 3823 | 92.5 | 2023-07-16T21:55:43.616199 | 2026-10-17 |
| 3889669 | 2023-08-21 | Apertura 2023 | regular | False | Atlas | 1-1 | 3397 | 3046 | 89.7 | 2023-08-24T10:19:24.178299 | 2026-10-17 |
| 3889681 | 2023-08-24 | Apertura 2023 | regular | False | Necaxa | 3-2 | 3636 | 3217 | 88.5 | 2023-09-03T13:38:51.466490 | 2026-10-17 |
| 3889685 | 2023-08-27 | Apertura 2023 | regular | False | León | 1-1 | 3411 | 3095 | 90.7 | 2023-08-29T12:06:51.047384 | 2026-10-17 |
| 3889699 | 2023-09-03 | Apertura 2023 | regular | False | Cruz Azul | 3-2 | 3566 | 3107 | 87.1 | 2023-09-05T20:07:33.507778 | 2026-10-17 |
| 3889702 | 2023-09-17 | Apertura 2023 | regular | False | Guadalajara | 4-0 | 3346 | 2875 | 85.9 | 2023-10-29T02:09:54.488951 | 2026-10-17 |
| 3889653 | 2023-09-21 | Apertura 2023 | regular | False | Querétaro | 2-1 | 3118 | 2699 | 86.6 | 2023-09-23T20:46:41.038766 | 2026-10-17 |
| 3889715 | 2023-09-24 | Apertura 2023 | regular | False | Toluca | 1-1 | 3808 | 3486 | 91.5 | 2023-09-25T10:11:33.056633 | 2026-10-17 |
| 3889725 | 2023-10-01 | Apertura 2023 | regular | False | Pumas UNAM | 1-0 | 3357 | 3000 | 89.4 | 2023-10-01T18:25:03.476699 | 2026-10-17 |
| 3889728 | 2023-10-04 | Apertura 2023 | regular | False | Pachuca | 4-0 | 3672 | 3224 | 87.8 | 2023-10-14T02:12:48.725474 | 2026-10-17 |
| 3889732 | 2023-10-07 | Apertura 2023 | regular | False | Mazatlán | 2-1 | 3683 | 3354 | 91.1 | 2023-10-29T02:04:18.432069 | 2026-10-17 |
| 3889744 | 2023-10-22 | Apertura 2023 | regular | False | Santos Laguna | 4-3 | 3652 | 3316 | 90.8 | 2023-11-04T16:55:30.196403 | 2026-10-17 |
| 3889758 | 2023-10-29 | Apertura 2023 | regular | False | Monterrey | 3-0 | 3786 | 3323 | 87.8 | 2024-09-28T13:11:03.577603 | 2026-10-17 |
| 3889769 | 2023-11-02 | Apertura 2023 | regular | False | Atlético San Luis | 1-0 | 4018 | 3650 | 90.8 | 2023-11-02T16:55:16.788160 | 2026-10-17 |
| 3889775 | 2023-11-05 | Apertura 2023 | regular | False | Tijuana | 3-0 | 3799 | 3341 | 87.9 | 2023-11-06T12:02:49.985548 | 2026-10-17 |
| 3889786 | 2023-11-12 | Apertura 2023 | regular | False | Tigres UANL | 0-0 | 3733 | 3171 | 84.9 | 2023-12-08T20:45:25.955220 | 2026-10-17 |
| 3917452 | 2023-11-30 | Apertura 2023 | liguilla | False | León | 2-2 | 3739 | 3426 | 91.6 | 2023-11-30T16:50:31.053189 | 2026-10-17 |
| 3917453 | 2023-12-03 | Apertura 2023 | liguilla | False | León | 2-0 | 3400 | 3058 | 89.9 | 2023-12-31T00:42:40.989289 | 2026-10-17 |
| 3917856 | 2023-12-07 | Apertura 2023 | liguilla | False | Atlético San Luis | 5-0 | 3896 | 3635 | 93.3 | 2023-12-08T11:00:48.093305 | 2026-10-17 |
| 3917858 | 2023-12-10 | Apertura 2023 | liguilla | False | Atlético San Luis | 0-2 | 4195 | 3752 | 89.4 | 2023-12-11T11:49:27.975190 | 2026-10-17 |
| 3918374 | 2023-12-15 | Apertura 2023 | liguilla | True | Tigres UANL | 1-1 | 3807 | 3482 | 91.5 | 2024-02-13T12:22:27.685279 | 2026-10-17 |
| 3918375 | 2023-12-18 | Apertura 2023 | liguilla | True | Tigres UANL | 3-0 | 4187 | 3783 | 90.4 | 2024-02-13T12:23:30.297161 | 2026-10-17 |
| 3918957 | 2024-01-14 | Clausura 2024 | regular | False | Tijuana | 2-0 | 3161 | 2788 | 88.2 | 2024-01-23T01:34:55.080506 | 2026-10-17 |
| 3919103 | 2024-01-21 | Clausura 2024 | regular | False | Querétaro | 2-0 | 3606 | 3289 | 91.2 | 2024-01-21T15:15:35.232037 | 2026-10-17 |
| 3918969 | 2024-01-25 | Clausura 2024 | regular | False | Juárez | 2-0 | 3438 | 3083 | 89.7 | 2024-02-03T19:25:40.918944 | 2026-10-17 |
| 3918974 | 2024-01-28 | Clausura 2024 | regular | False | Necaxa | 0-0 | 3647 | 3072 | 84.2 | 2024-02-10T22:10:53.297347 | 2026-10-17 |
| 3918991 | 2024-02-04 | Clausura 2024 | regular | False | Monterrey | 1-1 | 3721 | 3318 | 89.2 | 2024-06-12T03:37:32.224120 | 2026-10-17 |
| 3919001 | 2024-02-11 | Clausura 2024 | regular | False | León | 1-0 | 3048 | 2703 | 88.7 | 2024-02-21T10:36:43.335339 | 2026-10-17 |
| 3919008 | 2024-02-18 | Clausura 2024 | regular | False | Pachuca | 1-2 | 3463 | 3099 | 89.5 | 2024-02-26T10:38:29.308869 | 2026-10-17 |
| 3919016 | 2024-02-22 | Clausura 2024 | regular | False | Mazatlán | 2-2 | 3550 | 3199 | 90.1 | 2024-02-22T13:48:19.887860 | 2026-10-17 |
| 3919022 | 2024-02-25 | Clausura 2024 | regular | False | Cruz Azul | 1-0 | 3581 | 3168 | 88.5 | 2024-02-25T17:35:54.988877 | 2026-10-17 |
| 3919036 | 2024-03-03 | Clausura 2024 | regular | False | Atlas | 5-1 | 3771 | 3474 | 92.1 | 2024-03-14T16:38:12.399615 | 2026-10-17 |
| 3919045 | 2024-03-10 | Clausura 2024 | regular | False | Tigres UANL | 2-0 | 3366 | 3006 | 89.3 | 2024-05-21T19:04:45.344447 | 2026-10-17 |
| 3919055 | 2024-03-17 | Clausura 2024 | regular | False | Guadalajara | 0-0 | 3731 | 3290 | 88.2 | 2024-03-17T13:46:42.162549 | 2026-10-17 |
| 3919062 | 2024-03-30 | Clausura 2024 | regular | False | Atlético San Luis | 2-1 | 3266 | 2744 | 84.0 | 2024-03-30T14:49:28.794468 | 2026-10-17 |
| 3919069 | 2024-04-07 | Clausura 2024 | regular | False | Santos Laguna | 1-1 | 3538 | 3233 | 91.4 | 2024-04-07T20:40:13.555433 | 2026-10-17 |
| 3919081 | 2024-04-14 | Clausura 2024 | regular | False | Toluca | 5-1 | 3290 | 2890 | 87.8 | 2024-04-14T16:57:03.741445 | 2026-10-17 |
| 3919088 | 2024-04-21 | Clausura 2024 | regular | False | Pumas UNAM | 1-2 | 3711 | 3418 | 92.1 | 2024-04-21T19:48:16.153060 | 2026-10-17 |
| 3919094 | 2024-04-27 | Clausura 2024 | regular | False | Puebla | 2-1 | 3553 | 3248 | 91.4 | 2024-04-27T13:17:46.619652 | 2026-10-17 |
| 3936617 | 2024-05-09 | Clausura 2024 | liguilla | False | Pachuca | 1-1 | 3371 | 2838 | 84.2 | 2024-05-15T16:49:34.590495 | 2026-10-17 |
| 3936618 | 2024-05-12 | Clausura 2024 | liguilla | False | Pachuca | 1-1 | 3567 | 3189 | 89.4 | 2024-05-21T13:23:37.940150 | 2026-10-17 |
| 3937184 | 2024-05-16 | Clausura 2024 | liguilla | False | Guadalajara | 0-0 | 3817 | 3387 | 88.7 | 2024-05-23T16:11:48.298368 | 2026-10-17 |
| 3937186 | 2024-05-19 | Clausura 2024 | liguilla | False | Guadalajara | 1-0 | 3483 | 3007 | 86.3 | 2024-05-19T16:20:08.069518 | 2026-10-17 |
| 3937694 | 2024-05-24 | Clausura 2024 | liguilla | True | Cruz Azul | 1-1 | 3594 | 3276 | 91.2 | 2024-06-11T03:25:44.035399 | 2026-10-17 |
| 3937695 | 2024-05-27 | Clausura 2024 | liguilla | True | Cruz Azul | 1-0 | 3474 | 3079 | 88.6 | 2024-06-11T11:02:19.294223 | 2026-10-17 |
| 3939819 | 2024-07-06 | Apertura 2024 | regular | False | Atlético San Luis | 1-2 | 3315 | 2986 | 90.1 | 2024-07-09T06:18:19.255996 | 2026-10-17 |
| 3939825 | 2024-07-13 | Apertura 2024 | regular | False | Querétaro | 3-1 | 3476 | 3068 | 88.3 | 2024-07-17T02:00:15.132978 | 2026-10-17 |
| 3939841 | 2024-07-18 | Apertura 2024 | regular | False | Tigres UANL | 0-1 | 3697 | 3341 | 90.4 | 2024-07-24T15:16:36.182668 | 2026-10-17 |
| 3939848 | 2024-07-21 | Apertura 2024 | regular | False | Juárez | 2-1 | 3417 | 3121 | 91.3 | 2024-07-27T15:11:05.854368 | 2026-10-17 |
| 3939859 | 2024-08-25 | Apertura 2024 | regular | False | Puebla | 0-1 | 3615 | 3304 | 91.4 | 2024-09-08T16:36:03.027909 | 2026-10-17 |
| 3939867 | 2024-09-01 | Apertura 2024 | regular | False | Cruz Azul | 1-4 | 3387 | 3062 | 90.4 | 2024-09-24T05:21:59.575672 | 2026-10-17 |
| 3939876 | 2024-09-15 | Apertura 2024 | regular | False | Guadalajara | 1-0 | 3087 | 2740 | 88.8 | 2024-09-15T12:52:20.302645 | 2026-10-17 |
| 3939883 | 2024-09-18 | Apertura 2024 | regular | False | Atlas | 3-0 | 3658 | 3326 | 90.9 | 2024-09-18T10:48:42.968365 | 2026-10-17 |
| 3939892 | 2024-09-22 | Apertura 2024 | regular | False | Necaxa | 1-1 | 3406 | 3057 | 89.8 | 2024-11-02T14:55:59.382543 | 2026-10-17 |
| 3939905 | 2024-09-30 | Apertura 2024 | regular | False | Pumas UNAM | 0-1 | 3362 | 2975 | 88.5 | 2024-10-04T01:49:41.139862 | 2026-10-17 |
| 3939911 | 2024-10-06 | Apertura 2024 | regular | False | León | 1-1 | 3123 | 2835 | 90.8 | 2025-01-06T12:00:56.113036 | 2026-10-17 |
| 3939923 | 2024-10-20 | Apertura 2024 | regular | False | Santos Laguna | 3-0 | 3142 | 2864 | 91.2 | 2024-10-27T09:45:49.159444 | 2026-10-17 |
| 3939933 | 2024-10-24 | Apertura 2024 | regular | False | Tijuana | 2-2 | 3825 | 3519 | 92.0 | 2024-10-24T17:05:40.352054 | 2026-10-17 |
| 3939941 | 2024-10-28 | Apertura 2024 | regular | False | Monterrey | 2-1 | 3256 | 2879 | 88.4 | 2024-10-28T15:22:50.695776 | 2026-10-17 |
| 3939943 | 2024-11-02 | Apertura 2024 | regular | False | Mazatlán | 5-0 | 3484 | 3181 | 91.3 | 2024-11-02T13:10:37.889966 | 2026-10-17 |
| 3939959 | 2024-11-07 | Apertura 2024 | regular | False | Pachuca | 2-1 | 3436 | 3048 | 88.7 | 2024-11-18T06:31:06.074147 | 2026-10-17 |
| 3939915 | 2024-11-10 | Apertura 2024 | regular | False | Toluca | 0-4 | 3183 | 2784 | 87.5 | 2024-11-20T20:58:26.620867 | 2026-10-17 |
| 3968407 | 2024-11-22 | Apertura 2024 | liguilla | False | Tijuana | 2-2 | 3264 | 2863 | 87.7 | 2024-12-04T13:23:36.900287 | 2026-10-17 |
| 3969391 | 2024-11-28 | Apertura 2024 | liguilla | False | Toluca | 2-0 | 3452 | 3103 | 89.9 | 2024-12-19T14:08:39.930158 | 2026-10-17 |
| 3969395 | 2024-11-30 | Apertura 2024 | liguilla | False | Toluca | 2-0 | 3248 | 2920 | 89.9 | 2025-01-18T00:19:36.499267 | 2026-10-17 |
| 3970307 | 2024-12-06 | Apertura 2024 | liguilla | False | Cruz Azul | 0-0 | 3077 | 2702 | 87.8 | 2024-12-28T21:25:29.976608 | 2026-10-17 |
| 3970308 | 2024-12-09 | Apertura 2024 | liguilla | False | Cruz Azul | 4-3 | 3202 | 2792 | 87.2 | 2025-04-13T19:09:53.379707 | 2026-10-17 |
| 3971432 | 2024-12-13 | Apertura 2024 | liguilla | True | Monterrey | 2-1 | 3346 | 2940 | 87.9 | 2024-12-27T02:55:04.647833 | 2026-10-17 |
| 3971433 | 2024-12-16 | Apertura 2024 | liguilla | True | Monterrey | 1-1 | 3834 | 3510 | 91.5 | 2024-12-25T15:07:32.762861 | 2026-10-17 |
| 3972039 | 2025-01-26 | Clausura 2025 | regular | False | Santos Laguna | 4-1 | 3564 | 3183 | 89.3 | 2025-01-26T17:43:25.290717 | 2026-10-17 |
| 3972043 | 2025-01-29 | Clausura 2025 | regular | False | Atlético San Luis | 3-0 | 3612 | 3084 | 85.4 | 2025-01-29T13:55:22.922153 | 2026-10-17 |
| 3972053 | 2025-02-01 | Clausura 2025 | regular | False | Juárez | 4-0 | 3759 | 3356 | 89.3 | 2025-02-02T10:43:06.044523 | 2026-10-17 |
| 3972062 | 2025-02-08 | Clausura 2025 | regular | False | Puebla | 2-1 | 3409 | 3119 | 91.5 | 2025-02-08T15:25:51.561322 | 2026-10-17 |
| 3972074 | 2025-02-15 | Clausura 2025 | regular | False | Necaxa | 2-3 | 3199 | 2644 | 82.7 | 2025-02-15T17:45:40.669276 | 2026-10-17 |
| 3972080 | 2025-02-20 | Clausura 2025 | regular | False | León | 1-1 | 3542 | 3105 | 87.7 | 2025-03-03T15:40:04.315541 | 2026-10-17 |
| 3972087 | 2025-02-23 | Clausura 2025 | regular | False | Pumas UNAM | 2-0 | 3327 | 3003 | 90.3 | 2025-02-23T15:21:42.950181 | 2026-10-17 |
| 3972100 | 2025-03-01 | Clausura 2025 | regular | False | Toluca | 3-0 | 3775 | 3355 | 88.9 | 2025-03-06T18:19:38.492784 | 2026-10-17 |
| 3972111 | 2025-03-09 | Clausura 2025 | regular | False | Guadalajara | 0-0 | 3015 | 2721 | 90.2 | 2025-03-09T15:26:56.555752 | 2026-10-17 |
| 3972118 | 2025-03-16 | Clausura 2025 | regular | False | Atlas | 3-1 | 3119 | 2797 | 89.7 | 2025-03-22T23:37:41.915704 | 2026-10-17 |
| 3972127 | 2025-03-30 | Clausura 2025 | regular | False | Tigres UANL | 3-0 | 3319 | 2829 | 85.2 | 2025-04-11T15:24:31.599695 | 2026-10-17 |
| 3972136 | 2025-04-05 | Clausura 2025 | regular | False | Pachuca | 0-1 | 3401 | 3232 | 95.0 | 2025-04-14T16:37:25.790097 | 2026-10-17 |
| 3972145 | 2025-04-13 | Clausura 2025 | regular | False | Cruz Azul | 0-0 | 3858 | 3370 | 87.4 | 2025-05-04T03:31:53.784605 | 2026-10-17 |
| 3972155 | 2025-04-17 | Clausura 2025 | regular | False | Monterrey | 0-1 | 3458 | 3128 | 90.5 | 2025-04-18T00:52:48.486631 | 2026-10-17 |
| 3972162 | 2025-04-19 | Clausura 2025 | regular | False | Mazatlán | 5-0 | 3051 | 2550 | 83.6 | 2025-04-20T13:54:04.712716 | 2026-10-17 |
| 3993382 | 2025-05-08 | Clausura 2025 | liguilla | False | Pachuca | 0-0 | 3308 | 2975 | 89.9 | 2025-05-16T00:43:01.119553 | 2026-10-17 |
| 3993383 | 2025-05-11 | Clausura 2025 | liguilla | False | Pachuca | 2-0 | 3453 | 2871 | 83.1 | 2025-05-22T06:23:02.372717 | 2026-10-17 |
| 3994837 | 2025-05-16 | Clausura 2025 | liguilla | False | Cruz Azul | 0-1 | 3157 | 2928 | 92.7 | 2025-06-05T11:13:21.407353 | 2026-10-17 |
| 3994839 | 2025-05-19 | Clausura 2025 | liguilla | False | Cruz Azul | 2-1 | 2898 | 2488 | 85.9 | 2025-05-27T03:56:22.232660 | 2026-10-17 |
| 3995373 | 2025-05-23 | Clausura 2025 | liguilla | True | Toluca | 0-0 | 3283 | 2975 | 90.6 | 2025-05-31T11:38:41.532973 | 2026-10-17 |
| 3995374 | 2025-05-26 | Clausura 2025 | liguilla | True | Toluca | 0-2 | 3071 | 2759 | 89.8 | 2025-06-19T02:35:10.157305 | 2026-10-16 |
