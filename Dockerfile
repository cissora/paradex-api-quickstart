FROM python:3.11-slim


# Needed for some pip packages that compile native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the script (and optionally README/.env.example if you want)
COPY scan_ws.py 

# Devcontainer: keep container alive for VS Code; run scripts manually in terminal
CMD ["sleep", "infinity"]
