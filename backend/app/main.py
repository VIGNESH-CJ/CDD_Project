from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.config import settings
from app.database import create_db_and_tables, engine
from app.models.enums import UserRole
from app.models.restaurant import Restaurant
from app.models.user import User
from app.services.auth_service import decode_access_token
from app.websocket.manager import manager
from app.routers.delivery import delivery_tracking_websocket

# Import routers
from app.routers import (
    auth,
    restaurants,
    menu,
    cart,
    orders,
    admin,
    kitchen,
    delivery,
    superadmin,
    ai,
    payments,
    smart,
)

def on_startup():
    create_db_and_tables()
    # Check if seed is needed
    try:
        from sqlmodel import Session, select
        from app.models.user import User
        with Session(engine) as session:
            existing_user = session.exec(select(User)).first()
            if not existing_user:
                print("Database is empty. Populating demonstration seed data...")
                seed_script = Path(__file__).resolve().parent.parent.parent / "database" / "seed.py"
                if seed_script.exists():
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("seed_module", str(seed_script))
                    if spec is None or spec.loader is None:
                        raise RuntimeError(f"Could not load seed script at {seed_script}")
                    seed_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(seed_module)
                    run_seed = getattr(seed_module, "run_seed", None)
                    if not callable(run_seed):
                        raise RuntimeError(f"Seed script at {seed_script} does not define run_seed()")
                    run_seed()
    except Exception as e:
        print(f"Startup check notice: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    on_startup()
    yield

app = FastAPI(
    title=settings.APP_NAME,
    description=settings.APP_DESCRIPTION,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(auth.router)
app.include_router(restaurants.router)
app.include_router(menu.router)
app.include_router(cart.router)
app.include_router(orders.router)
app.include_router(admin.router)
app.include_router(kitchen.router)
app.include_router(delivery.router)
app.include_router(superadmin.router)
app.include_router(ai.router)
app.include_router(payments.router)
app.include_router(smart.router)

# WebSocket Endpoint for Live Real-Time Events
@app.websocket("/ws/orders")
async def websocket_orders_endpoint(websocket: WebSocket, token: str):
    payload = decode_access_token(token)
    email = payload.get("sub") if payload else None
    if not isinstance(email, str):
        await websocket.close(code=4401)
        return

    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        if not user or not user.is_active or user.id is None:
            await websocket.close(code=4403)
            return
        role = user.role.value
        user_id = user.id
        restaurant_ids = (
            session.exec(select(Restaurant.id).where(Restaurant.owner_id == user.id)).all()
            if user.role == UserRole.RESTAURANT_ADMIN
            else []
        )

    await manager.connect(
        websocket,
        role=role,
        user_id=user_id,
        restaurant_ids=restaurant_ids,
    )
    try:
        while True:
            data = await websocket.receive_text()
            if data.strip().lower() == "ping":
                await websocket.send_json({"type": "PONG", "message": "Connection active"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

@app.websocket("/ws/delivery/{order_id}")
async def delivery_tracking_endpoint(websocket: WebSocket, order_id: int, token: str):
    await delivery_tracking_websocket(websocket, order_id, token)


# Frontend static files mounting
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"

if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")
    
    @app.get("/", include_in_schema=False)
    def serve_home():
        index_file = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return {"message": "Welcome to AI Foodie API. Visit /docs for Swagger documentation."}

    # Helper routes to serve pages directly
    @app.get("/pages/{page_name}", include_in_schema=False)
    def serve_page(page_name: str):
        page_file = frontend_dir / "pages" / page_name
        if page_file.exists():
            return FileResponse(str(page_file))
        return FileResponse(str(frontend_dir / "index.html"))

    @app.get("/css/{file_name}", include_in_schema=False)
    def serve_css(file_name: str):
        css_file = frontend_dir / "css" / file_name
        if css_file.exists():
            return FileResponse(str(css_file), media_type="text/css")
        return {"error": "CSS not found"}

    @app.get("/js/{file_name}", include_in_schema=False)
    def serve_js(file_name: str):
        js_file = frontend_dir / "js" / file_name
        if js_file.exists():
            return FileResponse(str(js_file), media_type="application/javascript")
        return {"error": "JS not found"}
