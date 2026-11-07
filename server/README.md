# server/

Backend API services and controllers (**Backend / API Lead**).

## Owns

- Thin API routes that serve alerts, assets, and integration endpoints for the cockpit
- Controllers and service wiring over prediction / asset data

## Layout

```text
server/
└── src/          # routes, controllers, and services go here
```

## Do

- Put new API code under `server/src/`
- Import alert shapes from `shared/contracts.schema.json`
- Edit only files under `server/`

## Don't

- Alter `shared/` (read-only for this role)
- Move SENTRY / LUMI / sim into this folder — that stays in `retrofit/`
- Edit `client/`, `db/`, or `docs/` unless explicitly assigned
