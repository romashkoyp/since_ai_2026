# Step-by-step: Oracle Cloud (OCI) + MongoDB Atlas

Fresh setup for **2 VMs** (Frontend + Backend) and **MongoDB Atlas**.
No prior Oracle experience required.

---

## How SSH fits in (read this first)

| Question | Answer |
| --- | --- |
| What is SSH for? | **Your Mac → your OCI Linux VM** (terminal access). |
| Do I need SSH for MongoDB Atlas? | **No.** Atlas uses a connection string (`mongodb+srv://...`), not SSH. |
| Do I need SSH for the website users? | **No.** Users only open `http://FE_IP` in a browser. |
| One key or two? | **One key pair on your Mac** is enough. Paste the **same public key** when you create **both** VMs. |
| Old Oracle account keys? | **Do not reuse** keys from another Oracle tenancy (e.g. `nzm-oracle.key`). Use a key created for **this** project. |

**Correct order (do not skip):**

1. New OCI account + pick home region  
2. Create SSH key **on your Mac** (or download key if OCI generates it — see below)  
3. Create VCN + open ports **22, 80, 8000**  
4. Create **one** VM → paste public key → prove `ssh` works  
5. Create second VM (same key, same VCN)  
6. Install Docker + deploy BE, then FE  
7. MongoDB Atlas in parallel or after BE works  

If you created a VM **before** pasting the public key, SSH will **never** work with a new key unless you recreate the instance or use OCI’s serial console (advanced). **Easiest fix: terminate and create again** with the correct public key.

**What you will end up with**

| Piece | Role |
| --- | --- |
| OCI VM `since-ai-be` | Python FastAPI (Docker) on port **8000** |
| OCI VM `since-ai-fe` | React build served by nginx on port **80** |
| MongoDB Atlas | Managed database (no Mongo install on the VMs) |

---

## 0. Before you start (checklist)

Have ready:

- [ ] Credit card (OCI free tier signup may still ask for one; Always Free resources exist)
- [ ] GitHub access to `https://github.com/romashkoyp/since_ai_2026`
- [ ] Your laptop with SSH (`ssh` command works in Terminal)
- [ ] ~60–90 minutes for first-time setup

Write these down as you create them (use a notes app, not chat):

```text
FE_PUBLIC_IP =
BE_PUBLIC_IP =
SSH_KEY_PATH = ~/.ssh/since_ai_oci
ATLAS_URI = mongodb+srv://...
```

---

## 1. Create an Oracle Cloud account

1. Open **https://cloud.oracle.com**
2. Click **Sign Up** / **Start for free**
3. Choose **Home Region** carefully (you cannot change it later). Pick one close to you (e.g. `eu-frankfurt-1`, `eu-amsterdam-1`, `us-ashburn-1`).
4. Complete email verification and account creation.
5. Sign in to the **OCI Console**.

You should see the main dashboard with **Create a VM instance**, **Networking**, etc.

---

## 2. Create an SSH key on your laptop

### Option A (recommended): key on your Mac

On your Mac (Terminal):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/since_ai_oci -C "since-ai-2026-oci" -N ""
chmod 400 ~/.ssh/since_ai_oci
```

Show the **public** key (one single line — paste into OCI):

```bash
cat ~/.ssh/since_ai_oci.pub
```

Connect later with:

```bash
ssh -i ~/.ssh/since_ai_oci ubuntu@PUBLIC_IP
```

Keep the **private** file (`~/.ssh/since_ai_oci`) only on your Mac. Never upload it to GitHub or paste it into OCI.

### Option B: let OCI generate the key at instance create

In **Add SSH keys** → **Generate a key pair for me**:

1. **Download both** private and public key files immediately.
2. Store the private key somewhere safe (e.g. `~/Downloads/since-ai-ssh-key.key`).
3. `chmod 400` on the private key file.

Connect with:

```bash
chmod 400 /path/to/downloaded-private-key
ssh -i /path/to/downloaded-private-key ubuntu@PUBLIC_IP
```

If you lose the downloaded private key, Oracle **cannot** recover it — you must create a new instance.

---

## 3. Create networking (VCN) — first time only

OCI needs a Virtual Cloud Network so VMs can reach the internet.

### 3.1 Create VCN with wizard

1. In the Console top search, type **VCN** → open **Virtual Cloud Networks**.
2. Confirm you are in the correct **Compartment** (usually your root / tenancy name).
3. Click **Start VCN Wizard** → **Create VCN with Internet Connectivity**.
4. Fill in:
   - **VCN Name:** `since-ai-vcn`
   - Leave defaults for CIDR (e.g. `10.0.0.0/16`)
5. Click **Next** → **Create**.
6. Wait until it finishes → **View VCN**.

You now have:

- VCN
- Public subnet
- Internet Gateway
- Route table
- Default security list

### 3.2 Open firewall ports (Security List)

1. Inside the VCN → **Security Lists** → open **Default Security List for since-ai-vcn** (name may vary).
2. **Ingress Rules** → **Add Ingress Rules**.

Add these rules (one at a time):

| Source CIDR | IP Protocol | Destination Port | Description |
| --- | --- | --- | --- |
| `0.0.0.0/0` | TCP | **22** | SSH (later you can lock to your home IP) |
| `0.0.0.0/0` | TCP | **80** | Frontend HTTP |
| `0.0.0.0/0` | TCP | **443** | Frontend HTTPS (optional for later) |
| `0.0.0.0/0` | TCP | **8000** | Backend API (demo) |

For a safer SSH rule later: replace `0.0.0.0/0` on port 22 with your public IP + `/32` (search “what is my ip”).

Click **Add Ingress Rules**.

### 3.3 Verify networking (common mistakes)

Before creating VMs, confirm in the VCN:

| Check | Where to look | Must be |
| --- | --- | --- |
| Internet route | VCN → Route Tables → public route | `0.0.0.0/0` → **Internet Gateway** |
| Subnet type | Subnets → your subnet | **Public Subnet** = Yes |
| SSH open | Security List ingress | TCP **22** from your IP or `0.0.0.0/0` |

When creating each instance, under **Primary VNIC**:

- Subnet = **public** subnet (not private)
- **Assign a public IPv4 address** = **Yes**

If **Public IPv4** is empty after create, the VM is not reachable from the internet.

---

## 4. Create Backend VM (`since-ai-be`)

1. Console search → **Instances** → **Create instance**.
2. **Name:** `since-ai-be`
3. **Placement:** leave default AD.
4. **Image:** Canonical Ubuntu **22.04** (or 24.04).
5. **Shape:** click **Change shape**
   - Prefer **Ampere** (Arm) **VM.Standard.A1.Flex** — Always Free eligible if available  
     - OCPUs: `1` · Memory: `6` GB  
   - If Ampere capacity is full in your region, use **VM.Standard.E2.1.Micro** (AMD Always Free) instead.
6. **Networking**
   - VCN: `since-ai-vcn`
   - Subnet: **public** subnet
   - **Assign a public IPv4 address:** Yes
7. **Add SSH keys** (critical)
   - Choose **Paste SSH keys** (or upload `.pub` file)
   - Paste **exactly one line** from `cat ~/.ssh/since_ai_oci.pub` (no line breaks in the middle)
   - Do **not** paste the private key
8. Click **Create**.
9. Wait until state is **Running**.
10. Copy the **Public IP address** → save as `BE_PUBLIC_IP`.

### 4.1 SSH into the Backend VM

```bash
ssh -i ~/.ssh/since_ai_oci ubuntu@BE_PUBLIC_IP
```

**Login username**

| Image | SSH user |
| --- | --- |
| Ubuntu (Canonical) | `ubuntu` |
| Oracle Linux | `opc` |

First time: type `yes` to trust the host.

Success looks like: `ubuntu@since-ai-be:~$`

### 4.2 If SSH fails — read the error

| Error | Meaning | Fix |
| --- | --- | --- |
| `Operation timed out` | Network/firewall | Security list port 22; VM must have **Public IPv4**; public subnet + Internet Gateway |
| `Permission denied (publickey)` | Wrong or missing key on VM | Terminate VM; create new one; paste **this** account’s public key |
| `Connection refused` | SSH not up yet | Wait 2–3 min; state must be **Running** |

Verbose debug (run on Mac):

```bash
ssh -v -i ~/.ssh/since_ai_oci ubuntu@BE_PUBLIC_IP
```

---

## 5. Install Docker on the Backend VM

Still SSH’d into `since-ai-be`:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
```

Log out and back in so Docker group applies:

```bash
exit
ssh -i ~/.ssh/since_ai_oci ubuntu@BE_PUBLIC_IP
docker version
```

You should see Client and Server versions.

---

## 6. Create MongoDB Atlas (database)

Do this in the browser (not on the VM).

1. Open **https://cloud.mongodb.com** → Sign up / Sign in.
2. Create an organization/project if prompted (e.g. `Since AI`).
3. **Build a Database** → **M0 Free** → pick a cloud region close to your OCI home region → **Create**.
4. **Security → Database Access** → **Add New Database User**
   - Authentication: Password
   - Username: `since_ai_app`
   - Password: generate a strong one → save it
   - Role: **Atlas admin** is fine for hackathon; or **Read and write to any database**
5. **Security → Network Access** → **Add IP Address**
   - For first test: **Allow Access from Anywhere** (`0.0.0.0/0`) — quick but open  
   - Better: add only `BE_PUBLIC_IP` `/32`
6. **Database** → **Connect** → **Drivers** → copy the URI:

```text
mongodb+srv://since_ai_app:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
```

Replace `<password>` with the real password. Add a DB name:

```text
mongodb+srv://since_ai_app:YOUR_PASSWORD@cluster0.xxxxx.mongodb.net/since_ai?retryWrites=true&w=majority
```

Save as `ATLAS_URI`.  
**Never commit this to GitHub.**

> Note: the sample API currently still serves in-memory demo alerts. Atlas is ready for when Mongo is wired into FastAPI. Deploy FE/BE now either way.

---

## 7. Deploy the Backend on `since-ai-be`

Still on the BE VM:

```bash
cd ~
git clone https://github.com/romashkoyp/since_ai_2026.git
cd since_ai_2026
git checkout feat/client-server-scaffold
# after merge you can use: git checkout main && git pull
```

Build and run:

```bash
cd ~/since_ai_2026/server

docker build -t since-ai-server .

docker run -d \
  --name since-ai-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -e CORS_ORIGINS="http://FE_PUBLIC_IP" \
  -e MONGODB_URI="ATLAS_URI" \
  since-ai-server
```

Replace `FE_PUBLIC_IP` and `ATLAS_URI` with real values.  
If you do not have the FE IP yet, temporarily use:

```bash
-e CORS_ORIGINS="*"
```

(only for demo; tighten later)

### 7.1 Verify Backend

On the VM:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/alerts
```

From your laptop:

```bash
curl http://BE_PUBLIC_IP:8000/health
```

If laptop curl fails but VM curl works → fix **Security List port 8000**.

Useful Docker commands:

```bash
docker ps
docker logs since-ai-server --tail 100
docker restart since-ai-server
```

---

## 8. Create Frontend VM (`since-ai-fe`)

Repeat instance creation almost like BE:

1. **Instances** → **Create instance**
2. **Name:** `since-ai-fe`
3. Same image (Ubuntu) and shape preference as BE
4. Same VCN / public subnet / public IP
5. Paste the **same** SSH public key
6. Create → wait → copy **Public IP** → save as `FE_PUBLIC_IP`

SSH:

```bash
ssh -i ~/.ssh/since_ai_oci ubuntu@FE_PUBLIC_IP
```

Install Docker (same as section 5):

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
ssh -i ~/.ssh/since_ai_oci ubuntu@FE_PUBLIC_IP
```

---

## 9. Deploy the Frontend on `since-ai-fe`

Because FE and BE are **different machines**, the React app must know the BE URL at **build** time.

```bash
cd ~
git clone https://github.com/romashkoyp/since_ai_2026.git
cd since_ai_2026
git checkout feat/client-server-scaffold

cd client

docker build \
  --build-arg VITE_API_BASE_URL="http://BE_PUBLIC_IP:8000" \
  -t since-ai-client .

docker run -d \
  --name since-ai-client \
  --restart unless-stopped \
  -p 80:80 \
  since-ai-client
```

Replace `BE_PUBLIC_IP` with the real backend IP.

### 9.1 Update Backend CORS with the real FE IP

SSH back to BE and recreate the container with the correct origin:

```bash
ssh -i ~/.ssh/since_ai_oci ubuntu@BE_PUBLIC_IP

docker rm -f since-ai-server

cd ~/since_ai_2026/server
docker run -d \
  --name since-ai-server \
  --restart unless-stopped \
  -p 8000:8000 \
  -e CORS_ORIGINS="http://FE_PUBLIC_IP" \
  -e MONGODB_URI="ATLAS_URI" \
  since-ai-server
```

---

## 10. Open the app and test

1. Browser → `http://FE_PUBLIC_IP`
2. You should see **Since AI — Operator Cockpit**
3. Top-right pill should show **API connected**
4. Fleet tiles and alerts should load from the BE

If UI loads but API is offline:

- Check BE: `curl http://BE_PUBLIC_IP:8000/health`
- Check FE was built with the correct `VITE_API_BASE_URL`
- Check CORS includes `http://FE_PUBLIC_IP` (no trailing slash mismatch)
- Browser DevTools → Network → look for blocked CORS or failed `/api/alerts`

---

## 11. (Optional) Custom domain + HTTPS later

When you have a domain:

1. Create DNS A records:
   - `app.yourdomain.com` → `FE_PUBLIC_IP`
   - `api.yourdomain.com` → `BE_PUBLIC_IP`
2. On each VM install Certbot / use Caddy, or put **OCI Load Balancer** + certificates in front.
3. Rebuild FE with:

```bash
--build-arg VITE_API_BASE_URL="https://api.yourdomain.com"
```

4. Set BE:

```bash
-e CORS_ORIGINS="https://app.yourdomain.com"
```

---

## 12. Updating after code changes (simple CI/CD)

On each VM:

```bash
cd ~/since_ai_2026
git pull

# Backend
cd ~/since_ai_2026/server
docker build -t since-ai-server .
docker rm -f since-ai-server
docker run -d --name since-ai-server --restart unless-stopped \
  -p 8000:8000 \
  -e CORS_ORIGINS="http://FE_PUBLIC_IP" \
  -e MONGODB_URI="ATLAS_URI" \
  since-ai-server

# Frontend
cd ~/since_ai_2026/client
docker build --build-arg VITE_API_BASE_URL="http://BE_PUBLIC_IP:8000" -t since-ai-client .
docker rm -f since-ai-client
docker run -d --name since-ai-client --restart unless-stopped -p 80:80 since-ai-client
```

GitHub Actions (`.github/workflows/ci.yml`) already builds/checks images on push; SSH deploy above is enough for the hackathon.

---

## 13. Cost / Always Free tips

- Stick to **Always Free** shapes (A1.Flex or E2.1.Micro) when possible.
- Stop unused instances if you hit capacity or billing worries.
- Atlas **M0** is free; upgrade only if needed.
- Do not leave `0.0.0.0/0` on SSH forever — lock to your IP.

---

## 14. Troubleshooting quick sheet

| Problem | Fix |
| --- | --- |
| Cannot SSH | Security list port 22; correct key; use `ubuntu@` not `root@` |
| `docker: permission denied` | `sudo usermod -aG docker ubuntu` then re-login |
| BE health fails from laptop | Open ingress TCP 8000; confirm `docker ps` |
| FE shows API offline | Rebuild FE with correct `VITE_API_BASE_URL`; fix CORS |
| Atlas connection errors later | Atlas Network Access must allow BE IP; password URL-encoded if special chars |
| Out of host capacity (A1) | Retry later, other AD, or use E2.1.Micro |

---

## 15. Done checklist

- [ ] OCI account + home region chosen
- [ ] SSH key created
- [ ] VCN + security list ports 22/80/8000
- [ ] `since-ai-be` running, Docker installed, API on `:8000`
- [ ] Atlas cluster + user + network access + URI saved
- [ ] `since-ai-fe` running, Docker installed, site on `:80`
- [ ] Browser: cockpit loads and shows **API connected**
- [ ] IPs and secrets stored safely (not in git)

---

## Next code step (when you want)

Wire FastAPI to Atlas (`MONGODB_URI`) so `/api/alerts` and `/api/assets` read from Mongo collections instead of sample memory data. Ask in chat when ready and we can implement that in `server/`.
