# Roster / port-battle report — design reminder

When you build staff-facing roster or “who to bring” tooling, the intended direction included **ranking players by how well their hangar rows match a scenario** (e.g. Rate I port battle).

## “Best suited” tiers (idea to keep)

For each **(player, hangar row)** that matches the scenario filter (e.g. catalog `rate` is Rate I, or a defined ship list):

1. **Tier 1 — Ideal**  
   Player has the ship **and** upgrades (consumables too if you define rules) match the **ideal loadout** for that ship/role in the scenario config.

2. **Tier 2 — Acceptable**  
   Same ship, loadout meets a **relaxed** rule set (e.g. must-haves only, or a score above a threshold).

3. **Tier 3 — Listed but weak**  
   Same ship, but placeholders like “Not Unlocked Yet”, missing optional slots, or non-ideal upgrades.

Sort / present results by: **scenario ship priority order** (e.g. 12 Apostolov, La Royale, …) → **tier** → then player identity. Same player with multiple qualifying rows can be listed per ship or deduped by “best row per ship” — decide when you implement.

## Data you already have

- Per user: `users.ships_json` → `ships[]` with `ship_id`, `upgrades[]`, `consumables[]`, `instance_id`.
- Catalog: `app/data/ships_catalog.json` → `rate`, `name`, `class` keyed by `id` (`ship_id`).

## Still to build later

- Who may run reports (officers, admirals, etc.) and scope (guild vs all).
- Scenario config: rate filter, **ordered** `ship_id` list, ideal / acceptable upgrade rules per ship.
- API or export + UI; optional SQL denormalization if scans get slow.

`User.can_read_all_profiles()` exists for admirals / leaders / alliance leaders but is not wired to hangar views yet — hook or replace when you add permissions.
