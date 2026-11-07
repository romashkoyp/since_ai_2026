# CI/CD setup for Oracle VMs (GitHub Actions)

## How it works

```text
git push → main
   │
   ▼
CI workflow (.github/workflows/ci.yml)
  - Python import check
  - React build
  - Docker image build (smoke)
   │
   ▼ (only if CI succeeds)
Deploy OCI (.github/workflows/deploy.yml)
  - SSH → FE VM → git pull + docker rebuild client
  - SSH → BE VM → git pull + docker rebuild server
```

You can also run **Actions → Deploy OCI → Run workflow** manually.

---

## Prerequisites on each VM (do once)

### Frontend VM (`since-ai-fe`, e.g. `79.76.32.240`)

```bash
ssh -i ~/Downloads/ssh-key-2026-11-07.key ubuntu@79.76.32.240

# Docker (if not done)
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
# SSH again, then:
docker version
```

### Backend VM (`since-ai-be`) — after you create it

Same Docker + git install. Note its **public IP**.

Use the **same** SSH private key for both VMs (paste the same `.pub` when creating BE).

---

## GitHub repository secrets

1. Open: `https://github.com/romashkoyp/since_ai_2026`
2. **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

Add these:

| Secret name | Example / value |
| --- | --- |
| `OCI_FE_HOST` | `79.76.32.240` |
| `OCI_BE_HOST` | `158.179.204.167` |
| `OCI_SSH_USER` | `ubuntu` |
| `OCI_FE_SSH_PRIVATE_KEY` | Full contents of `ssh-fe/ssh-key-2026-11-07.key` |
| `OCI_BE_SSH_PRIVATE_KEY` | Full contents of `ssh-be/ssh-key-2026-11-07.key` |
| `VITE_API_BASE_URL` | `http://158.179.204.167:8000` |
| `CORS_ORIGINS` | `http://79.76.32.240` |
| `MONGODB_URI` | Atlas URI (or leave empty until Atlas is ready) |

### Paste private keys correctly

```bash
# Frontend key
cat /Users/sandunnishan/Desktop/Developer/Projects/since_ai/ssh-fe/ssh-key-2026-11-07.key

# Backend key
cat /Users/sandunnishan/Desktop/Developer/Projects/since_ai/ssh-be/ssh-key-2026-11-07.key
```

Copy **everything**, including:

```text
-----BEGIN OPENSSH PRIVATE KEY-----
...
-----END OPENSSH PRIVATE KEY-----
```

(or `BEGIN RSA PRIVATE KEY` depending on the file)

Use **Secrets** (not plain Variables) for keys, hosts can be Variables if you prefer — keys must be Secrets.

---

## First-time code path

CI/CD deploys from **`main`**. Until your feature branch is merged:

1. Commit + push `feat/client-server-scaffold`
2. Open PR → merge to `main`
3. CI runs → Deploy runs (if secrets are set)

Or test deploy early:

**Actions → Deploy OCI → Run workflow** → choose `frontend` or `both`

---

## Manual first deploy (optional, before CI)

### On FE

```bash
ssh -i ~/Downloads/ssh-key-2026-11-07.key ubuntu@79.76.32.240
cd ~
git clone https://github.com/romashkoyp/since_ai_2026.git
cd since_ai_2026
git checkout main   # or feat/client-server-scaffold until merged
cd client
docker build --build-arg VITE_API_BASE_URL="http://BE_IP:8000" -t since-ai-client:latest .
docker run -d --name since-ai-client --restart unless-stopped -p 80:80 since-ai-client:latest
```

### On BE (when VM exists)

```bash
cd ~/since_ai_2026/server
docker build -t since-ai-server:latest .
docker run -d --name since-ai-server --restart unless-stopped -p 8000:8000 \
  -e CORS_ORIGINS="http://79.76.32.240" \
  -e MONGODB_URI="YOUR_ATLAS_URI" \
  since-ai-server:latest
```

---

## Verify

- Browser: `http://79.76.32.240`
- API: `http://BE_IP:8000/health`
- GitHub → **Actions** → green CI + Deploy

---

## Troubleshooting

| Issue | Fix |
| --- | --- |
| Deploy: Permission denied (publickey) | Secret key must match VM key; user `ubuntu` |
| Deploy: timeout | Security list TCP 22 from GitHub? Prefer allow `0.0.0.0/0` on 22 for demo, or use runner IP ranges |
| FE builds but API offline | Set `VITE_API_BASE_URL` to real BE URL; rebuild FE |
| CI never triggers deploy | Merge to `main`; check Deploy workflow_run condition |
| Docker permission denied on VM | `sudo usermod -aG docker ubuntu` then re-login |

---

## Security notes

- Never commit private keys or Atlas passwords
- After hackathon, lock SSH to your IP only
- Prefer HTTPS + domain later
