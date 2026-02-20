# Paradex WebSocket via Subkey (Python SDK) — Quickstart

This repo is a minimal, working example to connect to Paradex **Prod** WebSocket price feeds using the official Paradex Python SDK (`paradex-py`), authenticated via a **Trading Key (Subkey)**.

Goal: get from zero → streaming WS (perp-ticker) data in ~30–45 minutes, without digging through a large SDK repo structure.

Official SDK (reference / full functionality):
- https://github.com/tradeparadex/paradex-py

Related official docs:
- https://docs.paradex.trade/docs/trading/api-authentication#subkeys
- https://docs.paradex.trade/ws/general-information

---

## What this repo does

- Authenticates to Paradex **Prod** WS using your **L2 Address + Trading Key (Subkey)**
- Subscribes to:
  - `markets_summary` (ALL markets): mark + funding (often)
  - `bbo` (per market): best bid/ask
- Prints a clean periodic terminal snapshot

This is intended to be foundational plumbing you can build on:
- scanners
- execution
- REST calls
- risk dashboards
- hedging logic

---

## Known-good Python version

Python 3.11 is the baseline that is known to work here.  
Newer Python versions might work, but are not guaranteed (dependency + async/websocket stacks can break on bleeding edge).

If you want “it just works,” use 3.11 (this repo’s Docker image uses Python 3.11).

---

## You MUST use a Trading Key (Subkey)

Paradex has different “keys”. For this setup you want a **Trading Key / Subkey** from the Paradex app.

### Create a Trading Key (Subkey) in the Paradex UI

1. Go to: https://app.paradex.trade  
2. Connect your wallet  
3. Navigate to:
   - Settings
   - Key Management
4. You’ll typically see:
   - Read-only keys
   - Trading keys
5. Under Trading Keys, create / add a new key.

Important notes:
- This “Trading Key” may also be labeled as a “private key” in some UIs/exports.
- In practice, this is the safer key to use for automation than exposing a more sensitive primary key.
- Treat it like a secret anyway: do not paste it into videos, do not commit it, do not share it.

You’ll need:
- `L2_ADDRESS` (your Paradex L2 address)
- `L2_SUBKEY` (the trading key/subkey you generated)

---

## Quickstart (VS Code Dev Containers) (Optional)

This is the easiest path if you want a consistent environment and fewer OS issues.

### 1) Install prerequisites

Recommended:
- Docker Desktop (must be installed and running)
- VS Code
- VS Code extension: Dev Containers

Optional:
- Git (or download the repo ZIP manually)

### 2) Open the repo in VS Code

- File → Open Folder…
- Select the repo folder (the one containing `Dockerfile` + `scan_ws.py`)

### 3) Start the dev container

- Press `Shift+Ctrl+P` (Command Palette)
- Run: `Dev Containers: Reopen in Container`

If you changed `requirements.txt` or the Dockerfile:
- `Shift+Ctrl+P` → `Dev Containers: Rebuild Container`

### 4) Confirm you are inside the container

You should see BOTH:
- Bottom-left VS Code status bar shows something like: **Dev Container: ...**
- Terminal prompt typically looks like:
  `root@<container_id>:/workspaces/<repo>#`

If you do not see those, you are not inside the container yet.

### 5) Verify dependencies inside the container

```bash
python --version
python -c "import importlib.metadata as m; print('termcolor', m.version('termcolor'))"
python -c "import importlib.metadata as m; print('paradex-py', m.version('paradex-py'))"
```

### 6) Create your `.env`

Create `.env` in the repo root (same directory as `scan_ws.py`):

```env
L2_ADDRESS=0x...
L2_SUBKEY=0x...

ENV=PROD
PARADEX_CHAIN_ID=PRIVATE_SN_PARACLEAR_MAINNET
````

### 7) Run the WebSocket scanner

```bash
python scan_ws.py
```

---

## Quickstart (Docker CLI)

Use this if you prefer the terminal instead of VS Code Dev Containers.

### 1) Build the image (from repo root)

```bash
docker build -t paradex-ws-quickstart .
```

### 2) Run the container (interactive)

This mounts your repo into the container so it can read `.env` and run `scan_ws.py` from the repo root:

```bash
docker run --rm -it \
  -v "$PWD:/repo" \
  -w /repo \
  paradex-ws-quickstart bash
```

### 3) Verify dependencies inside the container

```bash
python --version
python -c "import importlib.metadata as m; print('termcolor', m.version('termcolor'))"
python -c "import importlib.metadata as m; print('paradex-py', m.version('paradex-py'))"
```

### 4) Run the WebSocket scanner

```bash
python scan_ws.py
```

```
