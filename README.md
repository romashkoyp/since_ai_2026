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

---

### 3.1 Step-by-Step Execution Guide & Git Commands

#### Step 1: Start a New Feature from Existing Code (Developer A)

Before writing any code, always ensure your local `main` matches the remote repository:

```bash
# 1. Switch to main and pull latest code
git checkout main
git pull origin main

# 2. Create and switch to your feature branch
git checkout -b feat/client-dashboard
```

---

#### Step 2: Build & Commit Locally

Work with your AI agent or editor. Keep commits focused on your domain:

```bash
# 1. Verify modified files (ensure no accidental files were changed)
git status --short

# 2. Stage only your domain files
git add client/

# 3. Commit with a clear descriptive message
git commit -m "feat(client): implement dashboard layout and mock stats"
```

---

#### Step 3: Sync & Rebase Before Opening PR (Critical Step!)

While Developer A was building, **Developer B** merged changes into `main`. Developer A must rebase onto the newest `main` before submitting:

```bash
# 1. Fetch the latest commits from GitHub
git fetch origin main

# 2. Replay your feature branch commits on top of origin/main
git rebase origin/main
```

---

#### Step 4: Push Branch, Open PR & Merge to Main

Once rebase is clean, push your branch to GitHub:

```bash
# Push branch to remote (use --force-with-lease if you previously pushed this branch before rebase)
git push origin feat/client-dashboard --force-with-lease
```

1. Go to GitHub and click **Compare & pull request**.
2. Give it a short summary and select a teammate for a quick 30-second review.
3. Merge using **Squash and Merge** to maintain a clean linear history on `main`.
4. Delete the remote feature branch on GitHub.

---

#### Step 5: How Parallel Teammates Sync with the New Code (Developer B & Others)

Whenever any feature merges into `main`, all other teammates working on active branches should immediately pull those changes into their work:

```bash
# From within your active feature branch:
git fetch origin main
git rebase origin/main
```

This ensures everyone always builds on the latest ground truth and prevents huge merge conflicts later.

---

## 4. AI-Agent Common Rules
