# AMS Backend — Getting Started

## What runs

| Process | What it does |
|---|---|
| **FastAPI** (`uvicorn`) | REST API for the dashboard, student management, auth, attendance overrides |
| **CV Worker** (`cv_worker`) | Connects to camera streams, detects faces, marks attendance automatically |

Both processes share the same PostgreSQL database and Redis instance. Run them in **separate terminals**.

---

## Prerequisites

- Python 3.11+
- PostgreSQL 15+ with the **pgvector** extension enabled
- Redis 7+
- `pip install -r requirements.txt`

> InsightFace downloads the `buffalo_s` model (~300 MB) on first run into `~/.insightface/models/`.
> Make sure you have an internet connection the first time.

---

## 1. Environment — create `.env`

Create `AMS-v1-backend/.env`:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/ams

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=

# Auth
SECRET_KEY=change-this-to-a-long-random-string
ALGORITHM=HS256

# App
ENVIRONMENT=development
SCHOOL_NAME=My School

# InsightFace — buffalo_s is CPU-friendly; use buffalo_l for better accuracy
INSIGHTFACE_MODEL=buffalo_s
INSIGHTFACE_CTX_ID=-1

# Storage — 'local' saves files to MEDIA_ROOT
STORAGE_BACKEND=local
MEDIA_ROOT=./media

# Optional: ImageKit (leave blank to use local storage)
IMAGEKIT_PUBLIC_KEY=
IMAGEKIT_PRIVATE_KEY=
IMAGEKIT_URL_ENDPOINT=
```

---

## 2. Enable pgvector

Run once in your PostgreSQL database:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## 3. Run database migrations

```bash
cd AMS-v1-backend
alembic upgrade head
```

---

## 4. Start FastAPI (Terminal 1)

```bash
cd AMS-v1-backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API is available at: `http://localhost:8000`
Swagger docs: `http://localhost:8000/docs`

---

## 5. Start CV Worker (Terminal 2)

```bash
cd AMS-v1-backend
python -m cv_worker.main
```

The CV worker:
- Polls every 30 seconds for active attendance windows
- When a window becomes active, spawns a background task per section
- Captures frames only during the **opening burst** and **closing burst** of each class period
- Matches detected faces against enrolled students using ArcFace (InsightFace)
- Writes attendance records automatically

---

## 6. Testing with a laptop webcam

When adding a camera in the system, set the **RTSP URL** to:

```
webcam:0
```

This tells the CV worker to use your laptop's built-in camera (device index 0).
Use `webcam:1`, `webcam:2` etc. for external USB cameras.

When you get a real CCTV camera, just update the RTSP URL to the actual stream (e.g. `rtsp://admin:pass@192.168.1.100:554/stream`) — no code changes needed.

---

## 7. Setting up an attendance window for testing

An attendance window controls **when** the CV worker captures frames.

| Field | Meaning | Suggested test value |
|---|---|---|
| `start_time` | Period start (e.g. 09:30) | 2 mins from now |
| `end_time` | Period end (e.g. 10:15) | 20 mins from now |
| `detection_start_offset_minutes` | Minutes after start to begin capture | `1` |
| `opening_capture_duration_minutes` | How long the first burst lasts | `5` |
| `closing_capture_duration_minutes` | How long the closing burst lasts | `3` |
| `days_of_week` | Python weekdays (0=Mon … 6=Sun) | Today's number |
| `confidence_threshold` | ArcFace cosine distance cutoff | `0.35` |
| `min_detections_required` | Frames a student must appear in to be marked present | `2` |

---

## 8. Adding student face images (enrollment)

`POST /api/v1/students/{student_id}/faces` with a form-data `image` field.

The endpoint:
1. Runs InsightFace on the uploaded image
2. Detects and validates a face is present
3. Generates a 512-d ArcFace embedding
4. Stores it in `student_faces` table
5. Invalidates the Redis embedding cache for that student's sections

Upload **2–5 photos per student** for best matching accuracy (different lighting, slight angle variations).

---

## Face matching — how it works

1. CV worker captures a frame during a burst
2. InsightFace detects all faces in the frame
3. Each detected face's 512-d ArcFace embedding is compared against all enrolled students' stored embeddings using **cosine distance**
4. Cosine distance < `confidence_threshold` (default `0.35`) → match
5. Matched student gets an upserted attendance record (`detection_count` increments each time)
6. At the end of the window, `finalize_window` runs: students with `detection_count >= min_detections_required` → **PRESENT**, others → **ABSENT**

---

## Troubleshooting

**InsightFace model not downloading**
Run `python -c "from app.core.insight_face import get_face_app; get_face_app()"` once manually to trigger the download.

**Zero vectors in student_faces**
Delete any rows with all-zero embeddings and re-upload the face images. The old histogram-based code has been replaced — new uploads will have correct ArcFace embeddings.

**CV worker not spawning for a window**
- Check `days_of_week` includes today's weekday (0=Monday)
- Check `is_active=True` on both the window and the camera
- Check `is_primary=True` on the camera
- Check the current academic year has `is_current=True`

**No face detected on upload**
Ensure the photo is well-lit, front-facing, and the face occupies a reasonable portion of the frame.
