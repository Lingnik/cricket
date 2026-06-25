# dataset2 -- general RP-log turn dataset (candidate)

- Logs: 29 (14 Cricket in-scene + 15 breadth)
- Pose-turns: 1584 (target >=1500)
- All logs pass deterministic validators (line coverage, round-trip fidelity, contiguous seqs).
- Pipeline: tools/rplog_to_jsonl.py --render -> Opus per-line map -> tools/rplog_assemble.py

## PENDING before training-ready
1. Name canonicalization reduce: ~191 raw actor strings -> canonical registry (Atsvara/Atsvara Tarasar, Johanna/Johanna Siri te Danaan, Ecks/Kracen Ecks, ...).
2. Opus judge/spot-check: validators do NOT catch mis-attribution (He_Was_Doing dropped the Devaronian officer; 5 poses carry empty actor).

| log | rows | poses | actors | set |
|---|---:|---:|---:|---|
| Second_Battle_of_Mon_Calamari_First_Assault | 179 | 130 | 21 | Cricket |
| Fourth_Battle_of_Corellia | 154 | 117 | 25 | Cricket |
| Charity_Ball | 149 | 108 | 19 | Cricket |
| Rescue_of_Danik_Kreldin | 122 | 105 | 10 | Cricket |
| Ghastly_Gala | 112 | 92 | 16 | Cricket |
| Hangars_Hazards_Hangovers | 95 | 80 | 5 | Cricket |
| Johanna_is_a_Witch | 103 | 67 | 3 | Cricket |
| The_Second_Battle_of_Chandrila | 82 | 56 | 8 | Cricket |
| Bespin_Blows_Up | 63 | 48 | 11 | Cricket |
| Motherhood | 57 | 47 | 10 | Cricket |
| Ballistic_Equipment_Parts | 27 | 20 | 4 | Cricket |
| Birthday_Baroness | 31 | 20 | 10 | Cricket |
| Droid_Control_-_The_Ladies_Prefer_Electrum | 32 | 18 | 4 | Cricket |
| He_Was_Doing_You_A_Favour | 21 | 12 | 2 | Cricket |
| Who_s_Sane_Now | 76 | 66 | 8 | breadth |
| StarOps_Promotion_Ceremony | 67 | 59 | 12 | breadth |
| Trapped_in_Trinumvira | 75 | 58 | 6 | breadth |
| Many_Thoughts_Little_Words | 64 | 57 | 2 | breadth |
| SW1_Log_2001-01-05 | 67 | 53 | 8 | breadth |
| Luke_s_Response | 65 | 51 | 5 | breadth |
| Snowball_Fight | 55 | 47 | 8 | breadth |
| Surprise_Gastus_Went_Boom | 61 | 47 | 11 | breadth |
| Aurejin_Saves_Jessalyn | 58 | 44 | 4 | breadth |
| Lover_s_Quarrel_in_the_Dome | 69 | 43 | 4 | breadth |
| Coming_In_From_The_Cold_-_Part_2 | 55 | 42 | 2 | breadth |
| Meet_Kyyel | 51 | 38 | 2 | breadth |
| Battle_of_Selene_Part_II | 61 | 29 | 9 | breadth |
| Let_the_Tour_Begin | 34 | 20 | 5 | breadth |
| A_Sith_Interrogation | 17 | 10 | 4 | breadth |
