# Agent Operating Rules

1. SCOPE: You may ONLY edit files inside your assigned domain (`<assigned-folder>/`). Never touch files outside it.
2. CONTRACTS: Files in `shared/` are READ-ONLY unless you are Sync Lead acting on an agreed contract change. Import types from `shared/`, never invent parallel alert fields.
3. DOMAINS: `retrofit/` = AI (detector/sim/ML); `client/` = UI; `server/` = API; `db/` = migrations/seeds; `docs/` = pitch/demo. Do not move code across these boundaries without team agreement.
4. DEPENDENCIES: Never edit root or domain `package.json` / lockfiles / run install commands unless the user explicitly asks. Prefer requesting dependency additions in team chat.
5. DIFF HYGIENE: Do not touch imports, configs, or formatting of unrelated lines.
