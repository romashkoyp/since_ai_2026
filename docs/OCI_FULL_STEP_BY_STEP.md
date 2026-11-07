# Oracle Cloud — full step-by-step (new account)

Use this as a **single path from zero to running FE + BE**.  
Companion: [OCI_DEPLOY_STEP_BY_STEP.md](./OCI_DEPLOY_STEP_BY_STEP.md) (deploy commands).

Keep a note file:

```text
VCN_NAME = since-ai-vcn
SUBNET_NAME = since-ai-public-subnet
BE_PUBLIC_IP =
FE_PUBLIC_IP =
SSH_PRIVATE = ~/.ssh/since_ai_oci
ATLAS_URI =
```

---

## Part A — Account and SSH key (Mac)

### Step 1 — Log in to Oracle

1. Open https://cloud.oracle.com  
2. Sign in to your **new** account (e.g. compartment `lucasskarp`).  
3. Confirm **Home region** (top menu). You cannot change it later.

### Step 2 — Create SSH key on your Mac

Terminal:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/since_ai_oci -C "since-ai-2026-oci" -N ""
chmod 400 ~/.ssh/since_ai_oci
cat ~/.ssh/since_ai_oci.pub
```

Copy the **entire one line** starting with `ssh-ed25519`. You will paste it when creating VMs.

**Do not** use keys from an old Oracle account.

---

## Part B — Network (VCN, security list, subnet)

### Step 3 — Create the VCN (if you do not have one yet)

**Option A — Wizard (easiest)**

1. Search **VCN** → **Start VCN Wizard**  
2. **VCN with Internet Connectivity**  
3. Name: `since-ai-vcn`  
4. **IPv4 CIDR:** `10.0.0.0/16`  
5. Subnet CIDR (wizard): `10.0.0.0/24` if asked  
6. **Create** → **View VCN**

**Option B — You already created `since-ai-vcn`**

Skip to Step 4. Your VCN CIDR must be something like `10.0.0.0/16`.

### Step 4 — Security list (firewall rules)

1. **VCN** → your VCN → **Security Lists**  
2. Either **edit Default Security List** OR **Create Security List**  
   - Name: `since-ai-security-list`  
3. **Ingress** — add rules (Source CIDR `0.0.0.0/0`, protocol TCP):

| Port | Purpose |
| --- | --- |
| 22 | SSH |
| 80 | Frontend web |
| 443 | HTTPS (optional) |
| 8000 | Backend API |

4. **Egress** — add **one** rule:

| Destination CIDR | Protocol |
| --- | --- |
| `0.0.0.0/0` | All protocols |

5. **Save**

### Step 5 — Create public subnet (your current screen)

1. **VCN** → **Subnets** → **Create Subnet**  
2. **Name:** `since-ai-public-subnet`  
3. **IPv4 CIDR block:** `10.0.0.0/24` (must be inside VCN, e.g. `10.0.0.0/16`)  
4. **Subnet access:** **Public Subnet** (not Private)  
5. **Route table:** `Default Route Table for since-ai-vcn`  
6. **Security list:** `since-ai-security-list` (or default, if rules from Step 4 are on it)  
7. **Create**

### Step 6 — Verify internet route

1. VCN → **Route Tables** → `Default Route Table for since-ai-vcn`  
2. Must have: **Destination** `0.0.0.0/0` → **Target** Internet Gateway  
3. If missing: **Add Route Rule** → `0.0.0.0/0` → Internet Gateway

---

## Part C — Backend VM (prove SSH first)

### Step 7 — Create instance `since-ai-be`

1. Search **Instances** → **Create instance**  
2. **Name:** `since-ai-be`  
3. **Compartment:** `lucasskarp (root)`  
4. **Image:** **Ubuntu** → Canonical **22.04** (or 24.04)  
5. **Shape:** **Change shape**  
   - Try **VM.Standard.A1.Flex** (Arm): 1 OCPU, 6 GB (Always Free)  
   - If “out of capacity”: **VM.Standard.E2.1.Micro**  
6. **Networking:**  
   - VCN: `since-ai-vcn`  
   - Subnet: `since-ai-public-subnet`  
   - **Assign a public IPv4 address:** **Yes**  
7. **Add SSH keys** → **Paste SSH keys** → paste `since_ai_oci.pub` (one line)  
8. **Create**  
9. Wait until **Running**  
10. Copy **Public IPv4** → save as `BE_PUBLIC_IP`

### Step 8 — SSH from Mac

```bash
ssh -i ~/.ssh/since_ai_oci ubuntu@BE_PUBLIC_IP
```

- User is **`ubuntu`** for Ubuntu images.  
- If it works, you see `ubuntu@...:~$` — continue.  
- If **Permission denied** → terminate VM and redo Step 7 with the correct public key.  
- If **timeout** → check Step 4 port 22 and Step 7 public IP.

### Step 9 — Install Docker on backend VM

On the VM (SSH session):

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

SSH in again:

```bash
ssh -i ~/.ssh/since_ai_oci ubuntu@BE_PUBLIC_IP
docker version
```

---

## Part D — Frontend VM

### Step 10 — Create instance `since-ai-fe`

Same as Step 7, but:

- **Name:** `since-ai-fe`  
- **Same** VCN, subnet, shape, SSH public key  
- **Create** → copy **FE_PUBLIC_IP**

### Step 11 — SSH to frontend

```bash
ssh -i ~/.ssh/since_ai_oci ubuntu@FE_PUBLIC_IP
```

Install Docker (same commands as Step 9).

---

## Part E — MongoDB Atlas (browser, no SSH)

### Step 12 — Atlas cluster

1. https://cloud.mongodb.com → sign up / sign in  
2. **Build Database** → **M0 FREE**  
3. Region near your OCI home region → **Create**

### Step 13 — Database user

1. **Database Access** → **Add New Database User**  
2. Username/password → save password  
3. Role: read/write (or Atlas admin for demo)

### Step 14 — Network access

1. **Network Access** → **Add IP Address**  
2. Add **`BE_PUBLIC_IP/32`** (best) or temporarily `0.0.0.0/0` (demo only)

### Step 15 — Connection string

**Connect** → Drivers → copy URI, set database name:

```text
mongodb+srv://USER:PASS@cluster0.xxxxx.mongodb.net/since_ai?retryWrites=true&w=majority
```

Save as `ATLAS_URI`. Never commit to git.

---

## Part F — Deploy application

### Step 16 — Deploy backend (on `since-ai-be`)

```bash
ssh -i ~/.ssh/since_ai_oci ubuntu@BE_PUBLIC_IP

cd ~
git clone https://github.com/romashkoyp/since_ai_2026.git
cd since_ai_2026
git checkout feat/client-server-scaffold

cd server
docker build -t since-ai-server .

docker run -d --name since-ai-server --restart unless-stopped \
  -p 8000:8000 \
  -e CORS_ORIGINS="http://FE_PUBLIC_IP" \
  -e MONGODB_URI="PASTE_ATLAS_URI" \
  since-ai-server
```

Test on VM and from Mac:

```bash
curl http://127.0.0.1:8000/health
```

From Mac:

```bash
curl http://BE_PUBLIC_IP:8000/health
```

### Step 17 — Deploy frontend (on `since-ai-fe`)

```bash
ssh -i ~/.ssh/since_ai_oci ubuntu@FE_PUBLIC_IP

cd ~
git clone https://github.com/romashkoyp/since_ai_2026.git
cd since_ai_2026
git checkout feat/client-server-scaffold

cd client
docker build --build-arg VITE_API_BASE_URL="http://BE_PUBLIC_IP:8000" -t since-ai-client .

docker run -d --name since-ai-client --restart unless-stopped -p 80:80 since-ai-client
```

### Step 18 — Test in browser

1. Open `http://FE_PUBLIC_IP`  
2. Should see **Operator Cockpit**  
3. **API connected** in the corner  
4. Fleet + alerts load

If API offline:

- Rebuild FE with correct `BE_PUBLIC_IP`  
- Backend `CORS_ORIGINS` must include `http://FE_PUBLIC_IP` (no trailing slash)  
- Security list allows **8000** and **80**

---

## Part G — Done checklist

- [ ] VCN `10.0.0.0/16`  
- [ ] Public subnet `10.0.0.0/24`  
- [ ] Security list: 22, 80, 8000 ingress + egress all  
- [ ] Route `0.0.0.0/0` → Internet Gateway  
- [ ] `since-ai-be` + `since-ai-fe` with public IPs  
- [ ] SSH works with `~/.ssh/since_ai_oci`  
- [ ] Atlas URI saved  
- [ ] `http://FE_PUBLIC_IP` works  

---

## Quick troubleshooting

| Problem | Fix |
| --- | --- |
| Subnet CIDR error | Subnet must fit inside VCN (e.g. `10.0.0.0/24` in `10.0.0.0/16`) |
| No public IP on VM | Public subnet + “Assign public IPv4 = Yes” |
| SSH timeout | Ingress TCP 22 + IGW route |
| SSH permission denied | New VM + paste correct `.pub` key |
| Site loads, API offline | `VITE_API_BASE_URL` and CORS |
