# Stage 1: build the web UI
FROM node:22-alpine AS ui
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: the API, the agent and the built UI in one container
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=8000
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/src backend/src
# editable install keeps the package next to rulebook/, data/ and samples/ (paths resolve from the repo root)
RUN pip install --no-cache-dir -e ./backend
COPY rulebook rulebook
COPY data data
COPY samples samples
COPY --from=ui /app/frontend/dist frontend/dist
# runtime data (case records, uploads, page images); mount a persistent disk here
RUN mkdir -p storage
EXPOSE 8000
# NVIDIA_API_KEY and the MODEL_* settings come from the host's environment, never from the image
CMD ["sh", "-c", "uvicorn ap_agent.api.app:app --host 0.0.0.0 --port ${PORT}"]
