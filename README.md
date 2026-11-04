# Team Collaboration & Since AI Hackathon 2026 Workflow

## 1. Quick Onboarding & Repo Access

Repository: <https://github.com/romashkoyp/since_ai_2026>

### 1.1 Invite Collaborators & Grant Write Access

- **Repository Admin:** Go to repo `Settings` -> `Collaborators` -> `Add people` and invite all teammates with **Write/Admin** access.
- **Teammates:** Check GitHub notifications or email invitation link and accept access before attempting to push or branch.

### 1.2 Local Setup & Clone Checklist

- Clone repository locally:

  ```bash
  git clone https://github.com/romashkoyp/since_ai_2026.git
  cd since_ai_2026
  ```

- Verify base branch and remotes:

  ```bash
  git checkout main
  git pull origin main
  ```

### 1.3 Environment Variables (.env) Distribution

- Maintain `.env.example` in repo root with required key names and placeholder values.
- create `.env` file locally and past key value pares.
- NEVER commit `.env` files or secrets to Git.
- content of `.env` file will be shared in Telegram chat (for instance)

---

## 2. Team Architecture & Ownership

### 2.1 Role & Domain Allocation (just for example)

- **Client / UI Lead:** Page layouts, UI state, user flows, and mock integration.
- **Backend / API Lead:** Core API routes, controllers, and integration logic.
- **AI / Integration Lead:** Prompt pipelines, LLM wrappers, external webhooks/services.
- **Data & Schema Lead (Sync Lead):** Database models, migrations, seed script, and contract arbiter.
- **Demo & QA / Pitch Lead:** Pitch slides, live test scenarios, fallback video recording, and contract verification.

### 2.2 Directory Boundaries & Monorepo Structure (for example)

Hard boundaries to eliminate file collisions between teammates and AI agents:

```text
since_ai_2026/
├── shared/          # Single source of truth (contracts, schemas, types)
├── client/          # Frontend application & components
├── server/          # Backend API services & controllers
├── db/              # Migrations, schema definitions, and seed data
└── docs/            # Pitch notes, demo flow, architecture diagrams
```

### 2.3 Single Source of Truth (Contracts & Schemas)

- Contract file: (`shared/contracts.schema.json`).
- Any update to request/response shapes requires team alignment in chat before updating.
- Client and server code must import types from `shared/` rather than inventing parallel models.

---

## 3. Git & Branching Strategy

## 4. AI-Agent Common Rules
