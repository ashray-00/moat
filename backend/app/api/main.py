from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import ask

app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(ask.router)

@app.get("/health")
async def health():
    return {"ok": True}