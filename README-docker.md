# Docker Deployment for Your Voice Agent

This setup runs **two containers** from a single image:
- `app` → runs `python ./main.py` (WebSocket server on port **5000**)
- `http` → runs `python -m http.server 8000` (static/callback server on port **8000**)

## 1) Put these files in your project root
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

Your `main.py` and (optionally) `requirements.txt` should also be in the project root.

## 2) Build & run
From the project folder (same place as these files):

```powershell
# Windows PowerShell
docker compose up -d --build
```

This will:
- build a Python image with your code
- start **app** on `localhost:5000`
- start **http** on `localhost:8000`

Logs:
```powershell
docker compose logs -f app
docker compose logs -f http
```

Stop:
```powershell
docker compose down
```

## 3) Environment variables
Add your secrets via a local `.env` file (next to `docker-compose.yml`) or inline under `services.app.environment`:
```
DEEPGRAM_API_KEY=your_key_here
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
```

Docker Compose will auto-load `.env` if present.

## 4) Live code edits (dev mode)
- The compose file mounts your current folder into the containers:
  - `app`: `./:/app:rw` — app can read & write (for logs, temp files)
  - `http`: `./:/app:ro` — read-only
- When you edit local files, containers see changes immediately (restart `app` if your code doesn't hot-reload).

## 5) Optional: public URLs via ngrok
If you need `https://` and `wss://` endpoints for Twilio:
1. Get an ngrok authtoken.
2. Uncomment the `ngrok` service in `docker-compose.yml` and set `NGROK_AUTHTOKEN` in `.env`.
3. Start:
   ```powershell
   docker compose up -d ngrok
   ```
4. Check ngrok URLs:
   ```powershell
   docker logs -f voice-agent-ngrok-1
   ```
   You’ll see two public URLs:
   - one for **http:8000**
   - one for **app:5000** (use this as `wss://...` in Twilio; ngrok’s HTTPS tunnel proxies WebSocket correctly).

## 6) Troubleshooting
- If `requirements.txt` is missing, the image skips pip install. Add it if your code needs dependencies.
- If port conflicts occur, change the left side of port mappings in `docker-compose.yml`:
  ```yaml
  ports:
    - "15000:5000"  # host 15000 → container 5000
    - "18000:8000"  # host 18000 → container 8000
  ```
- Verify `main.py` binds to **0.0.0.0** inside the container, not 127.0.0.1.

## 7) One-container alternative (supervisor)
If you *must* run both processes in a single container, use a supervisor like `supervisord`. Compose is cleaner and easier to manage.

---

Happy shipping! 🚀
