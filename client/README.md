# client/

Frontend application and components (**Client / UI Lead**).

## Owns

- Streamlit operator cockpit (fleet triage, explainable alert cards, sandbox, replay UI)
- Page layouts, UI state, user flows, and mock integration

## Layout

```text
client/
└── src/          # UI entrypoints and components go here
```

## Do

- Put new UI under `client/src/`
- Consume alert shapes from `shared/contracts.schema.json`
- Edit only files under `client/`

## Don't

- Alter `shared/` (read-only for this role)
- Put detector / ML / sim code here — that stays in `retrofit/`
- Edit `server/`, `db/`, or `docs/` unless explicitly assigned
