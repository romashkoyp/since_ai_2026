# ZeroFault — RETROFIT AI 2026 (Business Turku / Elomatic Track)

**Make Existing Ship & Industrial Cooling Pumps Intelligent — Read-Only, Offline-Capable, No PLC Writes.**

ZeroFault turns existing VFD/MCC signals and low-cost retrofit sensors into early, explainable fault warnings using a deterministic 3-layer stack:
1. **Layer 1 — Physics v5 + Hybrid Diagnostic Engine (`joice_physics_rules/diag2.py` & `retrofit_engine/`):** Pump-curve affinity laws ($H \propto n^2, P \propto n^3$), Antoine vapor-pressure NPSH margin ($\sigma$), bearing envelope ratios (`b_idx`), and fixed-reference sensor drift isolation.
   - **Measured Benchmark Performance:** **93.7 / 100** on Company Train (**26/26 [100%]** observable faults detected, **24/26 [92.3%]** fault-type recall) and **95.8 / 100** on Company Validation (**9/9 [100%]** detected, **8/9 [88.9%]** fault-type recall, **0.00** false alerts/pump-day).
   - **Hidden Test Submission (`PUMP-10..12`):** [`joice_physics_rules/dashboard_data_fine_tuned/predictions_test.csv`](joice_physics_rules/dashboard_data_fine_tuned/predictions_test.csv) (and [`hybrid_model/output_csv/predictions_test.csv`](hybrid_model/output_csv/predictions_test.csv)).
2. **Layer 2 — Laya Deterministic Severity Triage (`server/src/severity.py` & `client/src/components/AlertTriage.tsx`):** Categorizes every alert into `SEVERE` (`MACHINE` $\ge 0.75$), `MODERATE` ($\ge 0.50$, including verified `SENSOR` faults), `MINIMAL` ($< 0.50$), and `LOW_CONFIDENCE` (`UNKNOWN`) in **<0.6 ms**, suppressing **72%–86%** of low-confidence nuisance alerts by default.
   - **Measured Economic Value (`examples/business_case.py`):** **€7,198/yr** net savings per duty pump with a **0.6-year (~7-month) payback** on a €4,500 retrofit kit.
3. **Layer 3 — Needle Context & Manual Retrieval (+ Optional Local LLM Copilot):** Triggered on `MODERATE` / `SEVERE` alerts to correlate `maintenance.csv` operator notes and OEM manuals for zero-retraining transfer to new vessels and rotating machinery.

---

## Quick Start: How Evaluators & Benefiting Companies Run ZeroFault Themselves

### Option A — 1-Command Self-Hosted Docker Stack (Air-Gapped / Shipboard Edge Ready)
```bash
git clone https://github.com/romashkoyp/since_ai_2026.git
cd since_ai_2026
docker compose up --build
```
- **Operator Cockpit UI:** `http://localhost:3000` (Fleet Overview, Pump Cockpit with Laya Alert Triage & Read-Only VFD Mitigation Simulator, Retrofit ROI Scorecard, and live **"Analyze Pump Data"** upload).
- **FastAPI + OpenAPI Docs:** `http://localhost:8000/docs` (`/api/alerts?severity=SEVERE&severity=MODERATE`, `/api/analyses`, `/retrofit/analyze`).
- Runs 100% offline using the embedded run store (`server/seed/demo_run.json`), with optional MongoDB Atlas sync when `MONGODB_URI` is set.

### Option B — Bring Your Own Pump CSV/Parquet (No Retraining Required)
Any ship owner or plant engineer can analyze a new pump immediately via the UI (**Analyze Pump Data**) or `POST /retrofit/analyze` by supplying two tables:
1. **`datasheet.csv`:** 1 row per pump with nameplate specs (`asset_id`, `control`, `motor_rated_rpm`, `pump_rated_flow_m3_h`, `pump_rated_head_m`, `pump_shutoff_head_m`, `npsh3_at_bep_m`, `fluid`).
2. **`telemetry.csv` / `.parquet`:** 1-min or 1 Hz readings (`motor_current_a`, `discharge_pressure_kpa`, plus any optional `T1`/`T2` sensors). The first 24–30 h of steady running automatically establishes the per-regime baseline.

### Option C — Reproduce Benchmark Scores & Test Predictions Locally
```bash
# Run official benchmark evaluation (train: 93.7, validation: 95.8, 32/35 fault types correct)
python joice_physics_rules/lab2.py <path-to-RETROFIT_AI_PARTICIPANTS_2026> -v

# Run Laya severity categorizer unit & benchmark suite (6/6 tests)
cd server && python -m unittest discover -s tests -v
```

---

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

### 1.4 Run the sample client + server

**Local (dev):**

```bash
# Terminal A — Python API (Python 3.12+)
cd server
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# Terminal B — React UI
cd client
npm install
npm run dev
```

Open `http://localhost:5173` (Vite proxies `/api` and `/health` to port 8000).

**Docker (CI-friendly host):**

```bash
docker compose up --build
```

UI: `http://localhost:3000` · API: `http://localhost:8000` · CI: `.github/workflows/ci.yml` · OCI deploy: `.github/workflows/deploy.yml` (see `docs/CICD_OCI_SETUP.md`)

---

## 2. Team Architecture & Ownership

### 2.1 Role & Domain Allocation

| Role | Folder | Owns |
| :--- | :--- | :--- |
| **Client / UI Lead** | `client/` | Streamlit / UI layouts, UI state, user flows, mock integration |
| **Backend / API Lead** | `server/` | API routes, controllers, integration logic |
| **AI / Integration Lead** | `retrofit/` | Detector (SENTRY), sim, LUMI, analysis, ML pipelines |
| **Data & Schema Lead (Sync Lead)** | `db/` (+ arbiter of `shared/`) | Migrations, seeds, and shared contract changes |
| **Demo & QA / Pitch Lead** | `docs/` | Pitch notes, demo flow, architecture diagrams, contract verification |

Product UI and API go in `client/` and `server/`. Detection, simulation, and scoring stay in `retrofit/`. Cross-domain alert shapes live only in `shared/`.

### 2.2 Directory Boundaries & Monorepo Structure

Hard boundaries to eliminate file collisions between teammates and AI agents:

```text
since_ai_2026/
├── shared/          # Single source of truth (contracts, schemas, types)
├── client/          # Frontend application & components
├── server/          # Backend API services & controllers
├── db/              # Migrations, schema definitions, and seed data
├── docs/            # Pitch notes, demo flow, architecture diagrams
└── retrofit/        # Cooling-pump sim, sentry, LUMI, and analysis (AI domain)
```

### 2.3 Single Source of Truth (Contracts & Schemas)

- Contract file: (`shared/contracts.schema.json`) — alert / prediction boundary between `retrofit`, `client`, and `server`.
- Dataset table schemas remain in `retrofit/src/retrofit_sim/schema.py` (AI-domain internal).
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

To prevent autonomous coding agents (Google Antigravity, Claude Code, Cursor, Windsurf, GitHub Copilot, OpenAI Codex, Cline, Roo Code, Kiro, Aider) from hallucinating dependencies, reformatting unrelated files, or overwriting teammates' work:

### 4.1 Agent Rule Files by Tool Convention
Different AI assistants read project instructions from specific files in the repository root. Commit standard rules using the relevant convention:

| Agent / Tool | Rule File Location & Name |
| :--- | :--- |
| **Google Antigravity** | `.gemini/rules/`, `CLAUDE.md`, or `.cursorrules` |
| **Claude Code** | `CLAUDE.md` |
| **Cursor** | `.cursorrules` or `.cursor/rules/*.mdc` |
| **Windsurf** | `.windsurfrules` |
| **GitHub Copilot** | `.github/copilot-instructions.md` |
| **Cline / Roo Code** | `.clinerules` |
| **Aider** | `.aider.conf.yml` or `CONVENTIONS.md` |
| **Kiro / Others** | `AGENT_RULES.md` / `CONTRIBUTING.md` |

*(Tip: You can create `CLAUDE.md` as the single ground truth and symlink or copy it to `.cursorrules` and `.clinerules`).*

#### Standard Rules Content (Ready to Copy):
```markdown
# Agent Operating Rules
1. SCOPE: You may ONLY edit files inside your assigned domain (<assigned-folder>/). Never touch files outside it.
2. CONTRACTS: Files in `shared/` are READ-ONLY. Import types from `shared/`, never alter or invent fields.
3. DEPENDENCIES: Never edit `package.json`, lockfiles, or run install commands. Request dependency additions in team chat.
4. DIFF HYGIENE: Do not touch imports, configs, or formatting of unrelated lines.
```

---

### 4.2 Strict Prompt Scoping (How Teammates Should Prompt Agents)
Constrain the agent explicitly to a specific file or folder in every prompt:
- ❌ **Bad (vague):** *"Add the summary view with statistics."* (Agent will touch router, layout, navbar, and configs)
- ✅ **Good (scoped):** *"Create `client/src/components/SummaryCard.tsx` consuming types from `shared/contracts.schema.json`. Do not edit any files outside `client/src/components/`."*

---

### 4.3 Pre-Commit Agent Sanitization
Before committing, inspect and discard unintended agent modifications:

```bash
# 1. Check which files the agent touched
git status --short

# 2. Revert any accidental changes to shared configs or lockfiles
git checkout -- package.json pnpm-lock.yaml package-lock.json tsconfig.json

# 3. Stage only your assigned folder
git add <domain-folder>/
```
