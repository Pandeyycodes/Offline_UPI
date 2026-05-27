from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from models.db import init_db, SessionLocal
from services.demo_service import seed_accounts
from crypto.key_holder import ServerKeyHolder
from routers.api import router
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    db = SessionLocal()
    try:
        seed_accounts(db)
    finally:
        db.close()
    ServerKeyHolder.get()  # generate keypair
    print("UPI Offline Mesh started — http://localhost:8000")
    yield
    # Shutdown (nothing needed)

app = FastAPI(
    title="UPI Offline Mesh",
    description="Offline UPI payments via Bluetooth mesh — demo backend",
    version="1.0.0",
    lifespan=lifespan,
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(router)
from fastapi.responses import RedirectResponse

@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
