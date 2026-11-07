# db/

Migrations, schema definitions, and seed data (**Data & Schema Lead / Sync Lead**).

## Owns

- Database models, migrations, and seed scripts for product persistence
- Contract arbitration for `shared/contracts.schema.json` (team alignment required before edits)

## Layout

```text
db/
├── migrations/   # ordered schema migrations
└── seeds/        # seed / fixture data
```

## Do

- Put migrations under `db/migrations/` and seeds under `db/seeds/`
- Align breaking schema or contract changes with the team in chat
- Edit only files under `db/` (and `shared/` when acting as Sync Lead)

## Don't

- Invent alert field names that diverge from `shared/contracts.schema.json`
- Edit `client/`, `server/`, or `retrofit/` unless explicitly assigned
