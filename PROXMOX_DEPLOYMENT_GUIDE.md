# Proxmox VE Deployment Guide: Dell OptiPlex 3070 Setup for 24/7 Candlestick App

This guide outlines the step-by-step process for turning a **Dell OptiPlex 3070** into a 24/7 homelab server running **Proxmox VE**, and deploying the **Hammer Candlestick & Growth Stock App** as containerized background services.

---

## Architecture Overview

```mermaid
graph TD
    A[Internet / Home Network] --> B[Nginx Proxy Manager / Cloudflare Tunnel]
    B -->|WebSockets / HTTPS| C[Streamlit Web UI - App.py Container]
    
    subgraph Proxmox VE Host (Dell OptiPlex 3070)
        subgraph Docker LXC Container
            C[Streamlit Web UI (Port 8501)]
            D[24/7 Background Worker (growth_scanner.py)]
            E[(SQLite Database - sentinel.db)]
        end
    end
    
    D -->|Poll Market / AI Analysis| F[yFinance & Gemini API]
    D -->|Push Alerts| G[Telegram / Discord / Email]
    C <-->|Read / Write| E
    D <-->|Read / Write| E
```

---

## Phase 1: Dell OptiPlex 3070 BIOS Configuration

Before installing Proxmox, configure BIOS settings for maximum 24/7 uptime and hardware virtualization:

1. **Power On OptiPlex:** Press `F2` repeatedly at startup to enter **Dell System Setup (BIOS)**.
2. **Virtualization Support:**
   - Navigate to **Virtualization Support** $\rightarrow$ **Virtualization**.
   - Enable **Intel Virtualization Technology (VT-x)**.
   - Enable **VT for Direct I/O (VT-d)**.
3. **Automatic Power Recovery (Critical for Uptime):**
   - Navigate to **Power Management** $\rightarrow$ **AC Recovery**.
   - Select **Power On**. *(This ensures that if your house loses power, the server boots back up automatically when power is restored).*
4. **Storage Controller:**
   - Navigate to **System Configuration** $\rightarrow$ **SATA Operation**.
   - Select **AHCI** (Change from RAID On if necessary for native drive access).
5. **Fast Boot & Secure Boot:**
   - **Secure Boot:** Disable (to prevent driver signing issues with Linux kernels).
   - **Boot Mode:** Ensure **UEFI** mode is selected.
6. **Save & Exit:** Save changes and reboot.

---

## Phase 2: Installing Proxmox VE 8.x

1. **Create Bootable USB Drive:**
   - Download the latest **Proxmox VE ISO** from [proxmox.com](https://www.proxmox.com/en/downloads).
   - Flash the ISO to a USB flash drive using [Rufus](https://rufus.ie/) (DD mode) or [BalenaEtcher](https://etcher.balena.io/).
2. **Install Proxmox:**
   - Insert USB into OptiPlex 3070 and press `F12` at boot to open the Boot Menu.
   - Select your USB drive and launch **Install Proxmox VE (Graphical)**.
   - Target Harddisk: Select your primary SSD (NVMe or SATA).
   - Country / Timezone / Keyboard layout: Configure as applicable.
   - Management Network Configuration:
     - **Hostname:** `proxmox.local` (or desired hostname).
     - **IP Address:** Assign a static IP (e.g., `192.168.1.100/24`).
     - **Gateway & DNS:** Your router's IP address (e.g., `192.168.1.1`).
3. **Access Proxmox Web GUI:**
   - Once installation completes and system reboots, navigate to `https://192.168.1.100:8006` from any web browser on your home network.
   - Username: `root`
   - Password: Specified during installation.

---

## Phase 3: Setting Up Docker LXC in Proxmox

Rather than running Docker directly on the Proxmox hypervisor root, it is best practice to run Docker inside an **unprivileged LXC container**.

### Using Proxmox VE Helper-Scripts (Fast Track)
Open the Proxmox Shell (Host node $\rightarrow$ `Shell`) and run the official community helper script:

```bash
bash -c "$(wget -qLO - https://github.com/tteck/Proxmox/raw/main/ct/docker.sh)"
```

**Script Prompts:**
- **Container Name:** `docker-apps`
- **CPU Cores:** 2 to 4 cores
- **RAM:** 4096 MB (4 GB)
- **Disk Size:** 20 GB - 40 GB
- **Enable Docker Compose:** Yes
- **Enable Portainer (Optional UI):** Yes

---

## Phase 4: Containerizing the Application

Once your Docker LXC is running, SSH into it (or open its console in Proxmox).

### 1. Clone the Codebase
```bash
git clone https://github.com/your-username/hammer_candlestick_app.git
cd hammer_candlestick_app
```

### 2. Configure Environment Variables
Create a `.env` file in the project root:
```bash
cp .env.example .env
nano .env
```
Fill in your production keys:
```ini
GEMINI_API_KEY=your_gemini_key_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id
DATABASE_PATH=/app/sentinel.db
```

### 3. Dockerization Blueprint

#### `Dockerfile`
Create a `Dockerfile` in the repository root:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose Streamlit default port
EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

#### `docker-compose.yml`
Create a `docker-compose.yml` file to separate the Web UI from the 24/7 Scanner Worker:
```yaml
version: '3.8'

services:
  streamlit-ui:
    build: .
    container_name: candlestick_app_ui
    command: streamlit run app.py --server.port=8501 --server.address=0.0.0.0
    ports:
      - "8501:8501"
    volumes:
      - ./sentinel.db:/app/sentinel.db
      - ./.env:/app/.env
    restart: unless-stopped

  scanner-worker:
    build: .
    container_name: candlestick_app_worker
    command: python -m scanners.growth_scanner
    volumes:
      - ./sentinel.db:/app/sentinel.db
      - ./.env:/app/.env
    restart: unless-stopped
```

### 4. Build and Start Stack
```bash
docker compose up -d --build
```
Verify running containers:
```bash
docker compose ps
```

---

## Phase 5: Reverse Proxy & WebSockets (Nginx Proxy Manager)

To securely access the Streamlit UI via a friendly local domain or SSL HTTPS URL:

1. **Spin up Nginx Proxy Manager LXC:**
   ```bash
   bash -c "$(wget -qLO - https://github.com/tteck/Proxmox/raw/main/ct/nginxproxymanager.sh)"
   ```
2. **Add Proxy Host:**
   - **Forward Hostname/IP:** IP of your Docker LXC.
   - **Forward Port:** `8501`
   - **Websockets Support:** **ENABLED** *(Crucial for Streamlit live 1s updates).*
   - **Block Common Exploits:** Enabled.
   - **SSL:** Request a new Let's Encrypt certificate.

---

## Phase 6: Maintenance, Backup & Auto-Start

1. **Automatic Container Restarts:**
   The `restart: unless-stopped` directive in `docker-compose.yml` guarantees that if the application crashes or the OptiPlex reboots, Docker will immediately restart both the UI and 24/7 background worker.
2. **Proxmox Backups (VZDump):**
   In Proxmox Web GUI, go to **Datacenter** $\rightarrow$ **Backup**.
   Set up a weekly schedule to back up your `docker-apps` LXC container to local storage or an external drive/NAS.

---

## Checklist Summary

- [ ] Configure OptiPlex BIOS (VT-x, AC Power Recovery = Power On, AHCI)
- [ ] Install Proxmox VE 8.x via USB
- [ ] Deploy Docker LXC via tteck helper script
- [ ] Clone repo & configure production `.env`
- [ ] Run `docker compose up -d`
- [ ] Connect Nginx Proxy Manager with WebSockets enabled
- [ ] Schedule Proxmox automated LXC backups
