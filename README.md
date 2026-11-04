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

```bash
# 1. Switch to main and pull latest code
git checkout main
git pull origin main

# 2. Create and switch to your feature branch
git checkout -b <branch-name>
```

---

#### Step 2: Build & Commit Locally

```bash
# 1. Verify modified files
git status --short

# 2. Stage only your domain files
git add <domain-folder>/

# 3. Commit
git commit -m "feat(<scope>): <short description>"
```

---

#### Step 3: Sync & Rebase Before Opening PR

```bash
# 1. Fetch latest commits from remote main
git fetch origin main

# 2. Rebase feature branch on top of origin/main
git rebase origin/main
```

*(If conflicts occur: fix files, run `git add <resolved-file>`, and `git rebase --continue`)*

---

#### Step 4: Push Branch, Open PR & Merge to Main

```bash
# Push branch to remote
git push origin <branch-name> --force-with-lease
```

1. Go to GitHub and click **Compare & pull request** -> **Create pull request**.
2. Click **Squash and merge** -> **Confirm squash and merge**.
3. Click **Delete branch**.
4. **Notify Team:** Send a quick message in team chat: *"Merged `<branch-name>` into main. Please run: `git fetch origin main && git rebase origin/main`"*

---

#### Step 5: Reset Developer A's Local State to Main

After merging on GitHub, Developer A resets local workspace:

```bash
# 1. Switch back to main
git checkout main

# 2. Pull the newly merged commit from GitHub
git pull origin main

# 3. Clean up local feature branch
git branch -d <branch-name>
```

---

#### Step 6: How Parallel Teammates Sync with the New Code (Developer B & Others)

Upon receiving Developer A's notification in chat, teammates run in their active branches:

```bash
git fetch origin main
git rebase origin/main
```

---

## 4. AI-Agent Common Rules
