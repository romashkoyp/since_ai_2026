# shared/

Single source of truth for **product-boundary** contracts between domains.

## Owns

- `contracts.schema.json` — alert / prediction shapes that couple `retrofit/` → `client/` / `server/`
- Shared types derived from that contract (when added)

## Do

- Import alert field names and enums from `contracts.schema.json`
- Propose contract changes in team chat; Data & Schema Lead (Sync Lead) applies them

## Don't

- Invent parallel alert models in `client/`, `server/`, or `retrofit/`
- Copy full dataset table schemas here — those stay in `retrofit/src/retrofit_sim/schema.py`
- Edit this folder unless you are Sync Lead or the team agreed on the change

Treat this folder as **read-only** for Client, Backend, and AI leads.
