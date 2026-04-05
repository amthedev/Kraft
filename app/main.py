from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.database import engine
from app.models import *  # noqa: F401, F403 — importa todos os modelos para o Alembic os ver
from app.routers import assets, auth, builds, chat, marketplace, projects


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Garante diretório de trabalho dos projetos
    Path(settings.projects_workdir).mkdir(parents=True, exist_ok=True)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_title,
    description="Game Creation OS — crie jogos com IA",
    version="0.1.0",
    lifespan=lifespan,
)

# Static files
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Uploads locais (fallback quando S3 não está configurado)
uploads_dir = Path(settings.projects_workdir) / "_uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# API routers
app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(chat.router)
app.include_router(builds.router)
app.include_router(assets.router)
app.include_router(marketplace.router)


# ─── Frontend routes ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_page(request: Request, project_id: int):
    return templates.TemplateResponse(request, "project.html", {"project_id": project_id})


@app.get("/projects/{project_id}/preview", response_class=HTMLResponse)
async def preview_page(request: Request, project_id: int):
    return templates.TemplateResponse(request, "preview.html", {"project_id": project_id})


@app.get("/marketplace", response_class=HTMLResponse)
async def marketplace_page(request: Request):
    return templates.TemplateResponse(request, "marketplace.html")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "auth.html", {"tab": "login"})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "auth.html", {"tab": "register"})


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.app_title}
