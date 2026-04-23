# Roster / port-battle report — design reminder

When you build staff-facing roster or “who to bring” tooling, the intended direction included **ranking players by how well their hangar rows match a scenario** (e.g. Rate I port battle).

## “Best suited” tiers (guidelines)

Scenario config will later define **acceptable** ships, upgrades, and consumables per role / scenario. Classification is per **(player, hangar row)** against that config and the scenario’s **rate** (e.g. Rate I port battle).

1. **Tier 1**  
   **Ship**, **upgrades**, and **consumables** are exactly aligned with the acceptable choices (acceptable sets are TBD in config).

2. **Tier 2**  
   They have the **correct ship** (an approved ship for the scenario), but **not** all accepted upgrades or consumables.

3. **Tier 3**  
   They do **not** have one of the **approved ships**, but they **do** have a ship of the **same rate** as the scenario.

4. **Tier 4**  
   They have **neither** an approved / ideal ship **nor** any ship of the scenario’s current rate.

Sort / present results by: **scenario ship priority order** (e.g. 12 Apostolov, La Royale, …) → **tier** (1 best, 4 worst) → then player identity. Same player with multiple qualifying rows can be listed per ship or deduped by “best row per ship” — decide when you implement.

## Data you already have

- Per user: `users.ships_json` → `ships[]` with `ship_id`, `upgrades[]`, `consumables[]`, `instance_id`.
- Catalog: `app/data/ships_catalog.json` → `rate`, `name`, `class` keyed by `id` (`ship_id`).

## Still to build later

- Who may run reports (officers, admirals, etc.) and scope (guild vs all).
- Scenario config: rate filter, **ordered** approved `ship_id` list, and the **acceptable** upgrade + consumable choices per ship (defines Tier 1 vs Tier 2 boundaries).
- API or export + UI; optional SQL denormalization if scans get slow.

`User.can_read_all_profiles()` exists for admirals / leaders / alliance leaders but is not wired to hangar views yet — hook or replace when you add permissions.
