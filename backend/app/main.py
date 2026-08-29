from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import webhook, events, approvals, metrics

app = FastAPI(title="Recovery Copilot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://recovery-copilot.vercel.app",
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(webhook.router)
app.include_router(events.router)
app.include_router(approvals.router)
app.include_router(metrics.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "recovery-copilot"}