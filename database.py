from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Use a SQLite database file in the corporate directory
DB_PATH = os.path.join(BASE_DIR, "visionai_corp_v2.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False, "timeout": 15})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ScrapedKnowledge(Base):
    __tablename__ = "scraped_knowledge"
    
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, index=True) # "institucional", "produtos", etc
    content = Column(Text)
    url = Column(String)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class BrandDNA(Base):
    __tablename__ = "brand_dna"
    
    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, default="VisionAI")
    website_url = Column(String, default="https://visionai.com.br")
    industry = Column(String, default="Inteligência Artificial & Computação de Borda")
    target_audience = Column(String, default="C-Levels, Diretores de TI, Heads de Operações e Gestores Industriais")
    tone_of_voice = Column(String, default="Visionário, Técnico, Pragmático e Orientado a ROI")
    core_services = Column(Text)
    differentials = Column(Text)
    content_pillars = Column(Text)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class PostDraft(Base):
    __tablename__ = "post_drafts"
    
    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String)
    format_type = Column(String)
    tone = Column(String)
    post_text = Column(Text)
    image_prompt = Column(Text)
    image_base64 = Column(Text)
    media_type = Column(String, default="image") # "image", "video", "custom"
    media_mime = Column(String, default="image/jpeg")
    model = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"
    
    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String)
    post_text = Column(Text)
    image_base64 = Column(Text)
    image_mime = Column(String, default="image/jpeg")
    media_type = Column(String, default="image") # "image", "video", "carousel"
    scheduled_at = Column(DateTime, index=True)
    status = Column(String, default="pending") # "pending", "published", "failed"
    published_urn = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class WebTrendItem(Base):
    __tablename__ = "web_trend_items"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    category = Column(String)
    summary = Column(Text)
    impact_b2b = Column(Text)
    suggested_topic = Column(String)
    source_url = Column(String, nullable=True)
    used = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Warning: init_db encounter: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
