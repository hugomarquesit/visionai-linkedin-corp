from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Use a SQLite database file in the corporate directory
DB_PATH = os.path.join(BASE_DIR, "visionai_corp.db")

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ScrapedKnowledge(Base):
    __tablename__ = "scraped_knowledge"
    
    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, index=True) # "institucional", "produtos", etc
    content = Column(Text)
    url = Column(String)
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
    model = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
