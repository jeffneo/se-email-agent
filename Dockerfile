# --- STAGE 1: Build Frontend (Node) ---
FROM node:20-alpine AS frontend_builder

WORKDIR /app/frontend

# Copy package files and install
COPY frontend/package*.json ./
RUN npm install

# Copy source and build
COPY frontend/ ./
RUN npm run build

# --- STAGE 2: Build Backend (Python) ---
FROM python:3.12-slim

WORKDIR /app

# Install Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy FastAPI code
COPY backend/ .

# Copy the BUILT frontend from Stage 1
# We copy from 'dist' to 'static'
COPY --from=frontend_builder /app/frontend/dist ./static

# Run it
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}