from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import init_db
from routers.readings import router as readings_router
from routers.relay import router as relay_router
from services.sync_worker import SyncWorker

sync_worker = SyncWorker()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Database
    print("[Lifespan] Initializing SQLite database...")
    init_db()
    
    # Startup: Start Sync Worker
    print("[Lifespan] Starting background sync worker...")
    sync_worker.start()
    
    yield
    
    # Shutdown: Stop Sync Worker
    print("[Lifespan] Stopping background sync worker...")
    sync_worker.stop()

app = FastAPI(
    title="ElectroLink Edge API",
    description="Local Edge Gateway proxy for ElectroLink ESP32 IoT devices.",
    version="1.0.0",
    lifespan=lifespan
)

# Register routers
app.include_router(readings_router)
app.include_router(relay_router)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "ElectroLink Edge API",
        "documentation": "/docs"
    }

if __name__ == "__main__":
    import uvicorn
    import config
    print(f"Starting ElectroLink Edge API on {config.HOST}:{config.PORT}...")
    uvicorn.run(app, host=config.HOST, port=config.PORT)
