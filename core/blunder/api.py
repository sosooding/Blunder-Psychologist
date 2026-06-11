from fastapi import FastAPI
from pydantic import BaseModel

from .db import SessionLocal
from .queue import enqueue

app = FastAPI(title="Blunder Psychologist API", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class HelloRequest(BaseModel):
    name: str = "world"


@app.post("/jobs/hello")
def enqueue_hello(req: HelloRequest) -> dict[str, object]:
    with SessionLocal() as session:
        job_id = enqueue(session, "hello", {"name": req.name}, priority=0)
    return {"job_id": job_id, "status": "queued"}
