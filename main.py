"""
VisionAI Corporate LinkedIn Manager — Backend API
FastAPI + Gemini 3.5-flash + LinkedIn API Corporativa
"""

import os
import json
import threading
from datetime import datetime
from functools import wraps

from fastapi import FastAPI, Request, Depends, HTTPException, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
from dotenv import load_dotenv

from linkedin_corp import LinkedInCorporate
from gemini_studio import GeminiStudio
from database import init_db, SessionLocal, PostDraft

init_db()

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = os.getenv("SESSION_SECRET", "corp-visionai-2026-ultra")
ADMIN_USER = os.getenv("ADMIN_USER", "hugo")
ADMIN_PASS = os.getenv("ADMIN_PASS", "VisionAI2026!")
API_KEY    = os.getenv("CORP_API_KEY", "corp_visionai_2026")

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="VisionAI Corporate LinkedIn Manager", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ── Clients (instanciados uma vez) ──────────────────────────────────────────
li = LinkedInCorporate()
ai = GeminiStudio()

# ── Auth helpers ────────────────────────────────────────────────────────────
def require_auth(request: Request):
    api_key = request.headers.get("X-API-KEY")
    if api_key == API_KEY:
        return True
    if request.session.get("authenticated"):
        return True
    raise HTTPException(status_code=401, detail="Não autorizado")

# ── Pydantic models ─────────────────────────────────────────────────────────
class LoginPayload(BaseModel):
    username: str
    password: str

class PostPayload(BaseModel):
    text: str
    visibility: str = "PUBLIC"
    draft: bool = False

class DeletePostPayload(BaseModel):
    post_urn: str

class GeneratePostPayload(BaseModel):
    topic: str
    format_type: str = "standard"
    tone: str = "visionario"

class ReviewPostPayload(BaseModel):
    draft: str

class AnalyticsAIPayload(BaseModel):
    analytics_data: dict

class ContentStrategyPayload(BaseModel):
    period_days: int = 30

class HashtagPayload(BaseModel):
    topic: str
    count: int = 8

class AnalyzeSinglePostPayload(BaseModel):
    content: str
    metrics: Optional[dict] = None

# ── Auth routes ─────────────────────────────────────────────────────────────
@app.post("/api/auth/login")
async def login(payload: LoginPayload, request: Request):
    if payload.username == ADMIN_USER and payload.password == ADMIN_PASS:
        request.session["authenticated"] = True
        return {"ok": True, "message": "Login efectuado com sucesso"}
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

@app.post("/api/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@app.get("/api/auth/status")
async def auth_status(request: Request):
    return {"authenticated": bool(request.session.get("authenticated"))}

# ── Health ──────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "VisionAI Corporate LinkedIn Manager",
        "org_id": li.org_id,
        "org_urn": li.org_urn,
        "gemini_model": ai.model,
        "timestamp": datetime.utcnow().isoformat(),
    }

# ── Dashboard ───────────────────────────────────────────────────────────────
@app.get("/api/dashboard")
async def dashboard(_: bool = Depends(require_auth)):
    summary = li.get_dashboard_summary()
    # Gemini gera insight executivo sobre os dados
    insight = ai.generate_dashboard_insight(summary)
    summary["ai_insight"] = insight
    return summary

# ── Organização ─────────────────────────────────────────────────────────────
@app.get("/api/org")
async def get_org(_: bool = Depends(require_auth)):
    org = li.get_org_info()
    admins = li.get_org_admins()
    return {"org": org, "admins": admins}

# ── Seguidores ──────────────────────────────────────────────────────────────
@app.get("/api/followers")
async def get_followers(_: bool = Depends(require_auth)):
    count = li.get_follower_count()
    stats = li.get_follower_statistics()
    # Gemini analisa o perfil dos seguidores
    ai_analysis = ""
    if stats.get("ok"):
        ai_analysis = ai.analyze_followers(stats.get("data", {}))
    return {
        "count": count.get("data", {}).get("firstDegreeSize", 0) if count.get("ok") else 0,
        "statistics": stats.get("data", {}) if stats.get("ok") else {},
        "ai_analysis": ai_analysis,
    }

# ── Analytics ───────────────────────────────────────────────────────────────
@app.get("/api/analytics")
async def get_analytics(_: bool = Depends(require_auth)):
    stats = li.get_share_statistics_last_12m()
    data = stats.get("data", {}) if stats.get("ok") else {}
    # Gemini gera insights sobre os analytics
    ai_insights = ai.analyze_analytics(data)
    return {
        "raw": data,
        "ai_insights": ai_insights,
    }

@app.get("/api/analytics/profile")
async def get_profile_analytics(_: bool = Depends(require_auth)):
    views = li.get_profile_views()
    post_analytics = li.get_member_post_analytics()
    network = li.get_network_size()
    return {
        "profile_views": views.get("data", {}) if views.get("ok") else {},
        "post_analytics": post_analytics.get("data", {}) if post_analytics.get("ok") else {},
        "network_size": network.get("data", {}).get("firstDegreeSize", 0) if network.get("ok") else 0,
    }

# ── Posts ───────────────────────────────────────────────────────────────────
@app.post("/api/posts")
async def create_post(payload: PostPayload, _: bool = Depends(require_auth)):
    if payload.draft:
        result = li.create_org_post_draft(payload.text)
    else:
        result = li.create_org_post(payload.text, payload.visibility)
    return result

@app.delete("/api/posts")
async def delete_post(payload: DeletePostPayload, _: bool = Depends(require_auth)):
    result = li.delete_org_post(payload.post_urn)
    return result

# ── Gemini — Geração de Posts ───────────────────────────────────────────────
@app.post("/api/gemini/generate-post")
async def gemini_generate_post(payload: GeneratePostPayload, _: bool = Depends(require_auth)):
    result = ai.generate_post(payload.topic, payload.format_type, payload.tone)
    
    # Save the generated post to the database
    db = SessionLocal()
    try:
        draft = PostDraft(
            topic=payload.topic,
            format_type=payload.format_type,
            tone=payload.tone,
            post_text=result.get("content", ""),
            image_prompt=result.get("image_prompt", ""),
            image_base64=result.get("image_base64", ""),
            model=result.get("model", "")
        )
        db.add(draft)
        db.commit()
    except Exception as e:
        print("Erro ao salvar post no banco:", e)
    finally:
        db.close()
        
    return result

@app.post("/api/gemini/review-post")
async def gemini_review_post(payload: ReviewPostPayload, _: bool = Depends(require_auth)):
    result = ai.review_post(payload.draft)
    return result

@app.post("/api/gemini/analyze-post")
async def gemini_analyze_post(payload: AnalyzeSinglePostPayload, _: bool = Depends(require_auth)):
    result = ai.analyze_single_post(payload.content, payload.metrics)
    return {"analysis": result, "model": ai.model}

# ── Gemini — Estratégia ─────────────────────────────────────────────────────
@app.post("/api/gemini/content-strategy")
async def gemini_content_strategy(payload: ContentStrategyPayload, _: bool = Depends(require_auth)):
    # Pega KPIs actuais para contexto
    summary = li.get_dashboard_summary()
    kpis = summary.get("kpis", {})
    result = ai.generate_content_strategy(kpis, payload.period_days)
    return result

# ── Gemini — Hashtags ───────────────────────────────────────────────────────
@app.post("/api/gemini/hashtags")
async def gemini_hashtags(payload: HashtagPayload, _: bool = Depends(require_auth)):
    hashtags = ai.generate_hashtags(payload.topic, payload.count)
    return {"hashtags": hashtags, "topic": payload.topic, "model": ai.model}

# ── Gemini — Analytics AI ───────────────────────────────────────────────────
@app.post("/api/gemini/analyze-analytics")
async def gemini_analyze_analytics(payload: AnalyticsAIPayload, _: bool = Depends(require_auth)):
    result = ai.analyze_analytics(payload.analytics_data)
    return {"insights": result, "model": ai.model}

# ── Gemini — Seguidores AI ──────────────────────────────────────────────────
@app.post("/api/gemini/analyze-followers")
async def gemini_analyze_followers(payload: AnalyticsAIPayload, _: bool = Depends(require_auth)):
    result = ai.analyze_followers(payload.analytics_data)
    return {"insights": result, "model": ai.model}

# ── Frontend SPA ────────────────────────────────────────────────────────────
@app.get("/")
@app.get("/dashboard")
@app.get("/posts")
@app.get("/analytics")
@app.get("/followers")
@app.get("/org")
@app.get("/studio")
@app.get("/profile")
def serve_spa():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
