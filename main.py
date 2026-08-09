"""
VisionAI Corporate LinkedIn Manager — Backend API
FastAPI + Gemini 3.5-flash + LinkedIn API Corporativa
"""

import os
import json
import threading
from datetime import datetime
from functools import wraps

from fastapi import FastAPI, Request, Depends, HTTPException, Body, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
from dotenv import load_dotenv

from linkedin_corp import LinkedInCorporate
from gemini_studio import GeminiStudio
from database import init_db, SessionLocal, PostDraft, BrandDNA

init_db()

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECRET_KEY = os.getenv("SESSION_SECRET", "corp-visionai-2026-ultra")
ADMIN_USER = os.getenv("ADMIN_USER", "hugo")
ADMIN_PASS = os.getenv("ADMIN_PASS", "VisionAI2026!")
API_KEY    = os.getenv("CORP_API_KEY", "corp_visionai_2026")

from fastapi.middleware.cors import CORSMiddleware

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="VisionAI Corporate LinkedIn Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://corp.visionai.com.br", "http://localhost:8000", "http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    same_site="lax",
    https_only=False,
    max_age=86400,
)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

RATE_LIMIT_CACHE = {}

@app.middleware("http")
async def add_security_headers_and_rate_limit(request: Request, call_next):
    # 1. Basic Rate Limiting Check by IP (Max 120 reqs/min per IP)
    import time
    client_ip = request.client.host if request.client else "unknown"
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
        
    now_ts = int(time.time())
    ip_history = RATE_LIMIT_CACHE.setdefault(client_ip, [])
    ip_history = [ts for ts in ip_history if now_ts - ts < 60]
    
    if len(ip_history) > 120:
        return JSONResponse(
            {"detail": "Muitas requisições enviadas. Limite de segurança excedido. Tente novamente em 1 minuto."},
            status_code=429
        )
        
    ip_history.append(now_ts)
    RATE_LIMIT_CACHE[client_ip] = ip_history

    # 2. Proceed with Request
    response = await call_next(request)

    # 3. Add Hardened Security Headers
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        
    return response

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
    image_base64: Optional[str] = None
    image_mime: Optional[str] = "image/jpeg"
    media_type: Optional[str] = "image" # "image" or "video"

class RegenerateMediaPayload(BaseModel):
    revised_text: str
    media_type: Optional[str] = "image"

class BrandDNAPayload(BaseModel):
    company_name: Optional[str] = "VisionAI"
    website_url: Optional[str] = "https://visionai.com.br"
    industry: Optional[str] = "Inteligência Artificial & Computação de Borda"
    target_audience: Optional[str] = "C-Levels, Diretores de TI, Heads de Operações"
    tone_of_voice: Optional[str] = "Visionário, Técnico, Pragmático"
    core_services: Optional[str] = None
    differentials: Optional[str] = None
    content_pillars: Optional[str] = None

class DeletePostPayload(BaseModel):
    post_urn: str

class GeneratePostPayload(BaseModel):
    topic: str
    format_type: str = "standard"
    tone: str = "visionario"
    media_type: Optional[str] = "image"
    voice_mode: Optional[str] = "corporate"
    content_objective: Optional[str] = "corporativo_sales"
    web_research: Optional[bool] = False
    overlay_style: Optional[str] = "photo_pure"
    art_style: Optional[str] = "auto"
    source_url: Optional[str] = ""

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

class MarkTrendUsedPayload(BaseModel):
    trend_id: Optional[int] = None
    topic: Optional[str] = None

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
        if payload.image_base64:
            is_video = payload.media_type == "video" or (payload.image_mime and "video" in payload.image_mime)
            if is_video:
                result = li.create_org_post_with_video(
                    text=payload.text,
                    video_b64=payload.image_base64,
                    video_mime=payload.image_mime or "video/mp4",
                    visibility=payload.visibility
                )
            else:
                result = li.create_org_post_with_image(
                    text=payload.text,
                    image_b64=payload.image_base64,
                    image_mime=payload.image_mime or "image/jpeg",
                    visibility=payload.visibility
                )
        else:
            result = li.create_org_post(payload.text, payload.visibility)
    return result

@app.delete("/api/posts")
async def delete_post(payload: DeletePostPayload, _: bool = Depends(require_auth)):
    result = li.delete_org_post(payload.post_urn)
    return result

# ── Brand DNA & Intelligence ───────────────────────────────────────────────
@app.get("/api/brand/dna")
async def get_brand_dna(_: bool = Depends(require_auth)):
    db = SessionLocal()
    try:
        dna = db.query(BrandDNA).first()
        if not dna:
            dna = BrandDNA(
                company_name="VisionAI",
                website_url="https://visionai.com.br",
                industry="Inteligência Artificial & Computação de Borda",
                target_audience="C-Levels, Diretores de TI, Heads de Operações e Gestores Industriais",
                tone_of_voice="Visionário, Técnico, Pragmático e Orientado a ROI",
                core_services="Visão Computacional na Borda, IA Multimodal, Realidade Mista em Meta Quest 3, Visão Agro-Industrial, Geração de Conteúdo AI, Governança",
                differentials="Edge AI sem dependência de nuvem, câmeras já instaladas, 95% precisão em atendimento, +15% produtividade agro",
                content_pillars="Casos de ROI, Liderança de Pensamento, Desmistificação Técnica, Automação Operacional"
            )
            db.add(dna)
            db.commit()
            db.refresh(dna)
        return {
            "ok": True,
            "dna": {
                "company_name": dna.company_name,
                "website_url": dna.website_url,
                "industry": dna.industry,
                "target_audience": dna.target_audience,
                "tone_of_voice": dna.tone_of_voice,
                "core_services": dna.core_services,
                "differentials": dna.differentials,
                "content_pillars": dna.content_pillars,
            }
        }
    finally:
        db.close()

@app.get("/api/brand/dna")
@app.get("/api/brand-dna")
async def get_brand_dna(_: bool = Depends(require_auth)):
    db = SessionLocal()
    try:
        dna = db.query(BrandDNA).first()
        if not dna:
            dna = BrandDNA()
            db.add(dna)
            db.commit()
            db.refresh(dna)
        return {
            "ok": True,
            "company_name": dna.company_name or "VisionAI",
            "website_url": dna.website_url or "https://visionai.com.br",
            "industry": dna.industry or "Inteligência Artificial & Computação de Borda",
            "target_audience": dna.target_audience or "C-Levels, Diretores de TI, Heads de Operações",
            "tone_of_voice": dna.tone_of_voice or "Visionário, Técnico, Pragmático e Orientado a ROI",
            "core_services": dna.core_services or "",
            "differentials": dna.differentials or "",
            "content_pillars": dna.content_pillars or ""
        }
    finally:
        db.close()

@app.post("/api/brand/dna")
@app.post("/api/brand-dna")
async def update_brand_dna(payload: BrandDNAPayload, _: bool = Depends(require_auth)):
    db = SessionLocal()
    try:
        dna = db.query(BrandDNA).first()
        if not dna:
            dna = BrandDNA()
            db.add(dna)
        if payload.company_name is not None: dna.company_name = payload.company_name
        if payload.website_url is not None: dna.website_url = payload.website_url
        if payload.industry is not None: dna.industry = payload.industry
        if payload.target_audience is not None: dna.target_audience = payload.target_audience
        if payload.tone_of_voice is not None: dna.tone_of_voice = payload.tone_of_voice
        if payload.core_services is not None: dna.core_services = payload.core_services
        if payload.differentials is not None: dna.differentials = payload.differentials
        if payload.content_pillars is not None: dna.content_pillars = payload.content_pillars
        db.commit()
        return {"ok": True, "message": "Brand DNA atualizado e persistido com sucesso no banco de dados"}
    finally:
        db.close()

@app.post("/api/gemini/regenerate-media")
async def regenerate_media(payload: RegenerateMediaPayload, _: bool = Depends(require_auth)):
    result = ai.regenerate_media_from_revised_text(payload.revised_text, payload.media_type or "image")
    return {"ok": True, **result}

@app.post("/api/media/upload")
async def upload_custom_media(file: UploadFile = File(...), _: bool = Depends(require_auth)):
    import base64
    contents = await file.read()
    b64 = base64.b64encode(contents).decode("utf-8")
    mime = file.content_type or "image/jpeg"
    is_video = "video" in mime
    return {
        "ok": True,
        "filename": file.filename,
        "media_b64": b64,
        "media_mime": mime,
        "media_type": "video" if is_video else "image",
        "size_bytes": len(contents)
    }

# ── Gemini — Geração de Posts ───────────────────────────────────────────────
@app.get("/api/gemini/auto-topics")
async def gemini_auto_topics(category: Optional[str] = None, refresh: bool = False, _: bool = Depends(require_auth)):
    """Retorna sugestões de tópicos baseados no site da VisionAI (https://visionai.com.br/#servicos)."""
    topics = ai.get_auto_topics(category=category, force_refresh=refresh)
    return {"topics": topics, "model": ai.model, "category": category}

@app.get("/api/posts/drafts")
async def get_post_drafts(_: bool = Depends(require_auth)):
    """Retorna os rascunhos de posts salvos no banco de dados."""
    db = SessionLocal()
    try:
        drafts = db.query(PostDraft).order_by(PostDraft.created_at.desc()).limit(20).all()
        return [
            {
                "id": d.id,
                "topic": d.topic,
                "format_type": d.format_type,
                "tone": d.tone,
                "post_text": d.post_text,
                "image_prompt": d.image_prompt,
                "image_base64": d.image_base64,
                "model": d.model,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in drafts
        ]
    finally:
        db.close()

@app.delete("/api/posts/drafts/{draft_id}")
async def delete_post_draft(draft_id: int, _: bool = Depends(require_auth)):
    """Remove um rascunho de post do banco."""
    db = SessionLocal()
    try:
        draft = db.query(PostDraft).filter_by(id=draft_id).first()
        if not draft:
            raise HTTPException(status_code=404, detail="Rascunho não encontrado")
        db.delete(draft)
        db.commit()
        return {"ok": True, "message": "Rascunho excluído com sucesso"}
    finally:
        db.close()

@app.post("/api/gemini/generate-post")
async def gemini_generate_post(payload: GeneratePostPayload, _: bool = Depends(require_auth)):
    result = ai.generate_post(
        payload.topic,
        payload.format_type,
        payload.tone,
        media_type=payload.media_type or "image",
        voice_mode=payload.voice_mode or "corporate",
        content_objective=payload.content_objective or "corporativo_sales",
        web_research=payload.web_research if payload.web_research is not None else True,
        overlay_style=payload.overlay_style or "photo_pure",
        art_style=payload.art_style or "auto",
        source_url=payload.source_url or ""
    )
    
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
        result["draft_id"] = draft.id
        
        # Marca a tendência correspondente como usada no banco de dados SQLite
        ai.mark_trend_used(topic=payload.topic)
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

# ── Novas Pydantic Models ───────────────────────────────────────────────────
class GenerateCarouselPayload(BaseModel):
    topic: str
    slides_count: Optional[int] = 5
    tone: Optional[str] = "provocativo"
    content_objective: Optional[str] = "lideranca_pensamento"
    art_style: Optional[str] = "tech_modern"
    overlay_style: Optional[str] = "cyberpunk_neon"
    target_audience: Optional[str] = ""
    web_research: Optional[bool] = False
    source_url: Optional[str] = ""

class PublishCarouselPayload(BaseModel):
    pdf_base64: str
    title: Optional[str] = "Carrossel Corporate"
    text: Optional[str] = ""

class SchedulePostPayload(BaseModel):
    topic: Optional[str] = ""
    text: str
    scheduled_at: str # YYYY-MM-DDTHH:MM:SS ou YYYY-MM-DD HH:MM
    image_base64: Optional[str] = None
    image_mime: Optional[str] = "image/jpeg"
    media_type: Optional[str] = "image"

# ── Background Scheduler Loop ────────────────────────────────────────────────
def scheduled_posts_worker():
    import time
    from database import ScheduledPost
    while True:
        try:
            db = SessionLocal()
            now = datetime.utcnow()
            pending = db.query(ScheduledPost).filter(
                ScheduledPost.status == "pending",
                ScheduledPost.scheduled_at <= now
            ).all()
            for post in pending:
                print(f"Executando publicação agendada ID {post.id} ({post.topic})...")
                try:
                    if post.image_base64:
                        if post.media_type == "carousel" or (post.image_mime and "pdf" in post.image_mime):
                            res = li.publish_pdf_carousel(post.post_text, post.image_base64, title=post.topic or "Carrossel Corporate")
                        elif post.media_type == "video" or (post.image_mime and "video" in post.image_mime):
                            res = li.create_org_post_with_video(post.post_text, post.image_base64, post.image_mime)
                        else:
                            res = li.create_org_post_with_image(post.post_text, post.image_base64, post.image_mime)
                    else:
                        res = li.create_org_post(post.post_text)
                    
                    if res.get("ok"):
                        post.status = "published"
                        post.published_urn = str(res.get("id", ""))
                        print(f"Post agendado {post.id} publicado com sucesso!")
                    else:
                        post.status = "failed"
                        post.error_message = str(res.get("error", "Erro na publicação"))
                        print(f"Falha ao publicar post agendado {post.id}: {post.error_message}")
                    db.commit()
                except Exception as ex:
                    post.status = "failed"
                    post.error_message = str(ex)
                    db.commit()
            db.close()
        except Exception as e:
            print("Erro no worker de agendamento:", e)
        time.sleep(30)

threading.Thread(target=scheduled_posts_worker, daemon=True).start()

# ── Gemini — Web Trends, Trending Papers, Carousel & Document Parsing ────────────────────────
@app.get("/api/gemini/web-trends")
async def gemini_web_trends(query: Optional[str] = None, refresh: bool = False, _: bool = Depends(require_auth)):
    """Retorna tendências e notícias em tempo real sobre o setor salvas no banco SQLite."""
    trends = ai.fetch_web_trends(query, force_refresh=refresh)
    return {"ok": True, **trends, "model": ai.model}

@app.get("/api/gemini/trending-papers")
async def gemini_trending_papers(query: Optional[str] = None, _: bool = Depends(require_auth)):
    """Busca pesquisas acadêmicas e papers em alta no HuggingFace Papers / ArXiv."""
    papers = ai.fetch_huggingface_trending_papers(query=query)
    return papers

@app.post("/api/gemini/web-trends/mark-used")
async def gemini_mark_trend_used(payload: MarkTrendUsedPayload, _: bool = Depends(require_auth)):
    """Marca uma tendência como usada no banco SQLite para ocultá-la das listagens."""
    marked = ai.mark_trend_used(payload.trend_id, payload.topic)
    return {"ok": True, "marked": marked}

@app.post("/api/gemini/generate-carousel")
async def gemini_generate_carousel(payload: GenerateCarouselPayload, _: bool = Depends(require_auth)):
    """Gera um carrossel em PDF multi-slide corporativo para o LinkedIn respeitando todas as regras de tom, estilo e marca."""
    try:
        res = ai.generate_carousel_pdf(
            topic=payload.topic,
            slide_count=payload.slides_count or 5,
            tone=payload.tone or "provocativo",
            content_objective=payload.content_objective or "lideranca_pensamento",
            art_style=payload.art_style or "tech_modern",
            overlay_style=payload.overlay_style or "cyberpunk_neon",
            target_audience=payload.target_audience or "",
            web_research=payload.web_research or False,
            source_url=payload.source_url or ""
        )
        return {"ok": True, **res, "model": ai.model}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"ok": False, "detail": f"Erro ao gerar carrossel em PDF: {str(e)}"}, status_code=500)

@app.post("/api/posts/publish-carousel")
async def publish_carousel_now(payload: PublishCarouselPayload, _: bool = Depends(require_auth)):
    """Publica o PDF do carrossel imediatamente no LinkedIn."""
    if not payload.pdf_base64:
        raise HTTPException(status_code=400, detail="O código base64 do PDF do carrossel é obrigatório")
    title = payload.title or "Carrossel Corporate LinkedIn"
    text = payload.text if (payload.text and "Confira o carrossel completo em PDF" not in payload.text) else f"✦ {title}\n\nEstratégia executiva B2B e síntese prática de {title}.\n\nAnalisamos a fundo os pilares fundamentais de inovação, ganho operacional e ROI medido. Confira a análise detalhada no carrossel abaixo e compartilhe como sua empresa aborda esta transformação!"
    result = li.publish_pdf_carousel(text, payload.pdf_base64, title=title)
    if result.get("ok"):
        return {"ok": True, "urn": result.get("id"), "message": "Carrossel publicado no LinkedIn com sucesso!"}
    else:
        return JSONResponse({"ok": False, "detail": result.get("error", "Falha ao publicar carrossel")}, status_code=500)

@app.post("/api/brand/upload-document")
async def upload_document(file: UploadFile = File(...), _: bool = Depends(require_auth)):
    """Lê um PDF/Documento corporativo e desmembra em 3 a 5 posts B2B."""
    contents = await file.read()
    doc_text = ""
    if file.filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(contents))
            for page in reader.pages:
                doc_text += page.extract_text() + "\n"
        except Exception as e:
            print(f"Erro ao extrair PDF via pypdf: {e}")
            doc_text = contents.decode("utf-8", errors="ignore")
    else:
        doc_text = contents.decode("utf-8", errors="ignore")

    res = ai.parse_document_to_posts(doc_text)
    return {"ok": True, "filename": file.filename, **res}

# ── Agendamento de Posts ────────────────────────────────────────────────────
@app.get("/api/posts/scheduled")
async def get_scheduled_posts(_: bool = Depends(require_auth)):
    from database import ScheduledPost
    db = SessionLocal()
    try:
        posts = db.query(ScheduledPost).order_by(ScheduledPost.scheduled_at.asc()).all()
        return [
            {
                "id": p.id,
                "topic": p.topic,
                "post_text": p.post_text,
                "image_base64": p.image_base64,
                "image_mime": p.image_mime,
                "media_type": p.media_type,
                "scheduled_at": p.scheduled_at.isoformat(),
                "status": p.status,
                "published_urn": p.published_urn,
                "error_message": p.error_message,
                "created_at": p.created_at.isoformat() if p.created_at else None
            }
            for p in posts
        ]
    finally:
        db.close()

@app.post("/api/posts/schedule")
async def schedule_post(payload: SchedulePostPayload, _: bool = Depends(require_auth)):
    from database import ScheduledPost
    db = SessionLocal()
    try:
        clean_date_str = payload.scheduled_at.replace("Z", "").split(".")[0]
        dt = datetime.fromisoformat(clean_date_str)
        sp = ScheduledPost(
            topic=payload.topic or "Post Agendado",
            post_text=payload.text,
            image_base64=payload.image_base64,
            image_mime=payload.image_mime or "image/jpeg",
            media_type=payload.media_type or "image",
            scheduled_at=dt,
            status="pending"
        )
        db.add(sp)
        db.commit()
        db.refresh(sp)
        return {"ok": True, "id": sp.id, "scheduled_at": sp.scheduled_at.isoformat()}
    finally:
        db.close()

@app.delete("/api/posts/scheduled/{post_id}")
async def cancel_scheduled_post(post_id: int, _: bool = Depends(require_auth)):
    from database import ScheduledPost
    db = SessionLocal()
    try:
        sp = db.query(ScheduledPost).filter_by(id=post_id).first()
        if not sp:
            raise HTTPException(status_code=404, detail="Agendamento não encontrado")
        db.delete(sp)
        db.commit()
        return {"ok": True, "message": "Agendamento cancelado com sucesso"}
    finally:
        db.close()

# ── Frontend SPA ────────────────────────────────────────────────────────────
@app.get("/")
@app.get("/dashboard")
@app.get("/posts")
@app.get("/analytics")
@app.get("/followers")
@app.get("/org")
@app.get("/studio")
@app.get("/calendar")
@app.get("/profile")
def serve_spa():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

# ── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
