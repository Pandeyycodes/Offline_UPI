from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./upimesh.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    vpa = Column(String, unique=True, index=True)
    name = Column(String)
    balance = Column(Float, default=0.0)
    version = Column(Integer, default=0)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    packet_hash = Column(String, unique=True, index=True)
    sender_vpa = Column(String)
    receiver_vpa = Column(String)
    amount = Column(Float)
    settled_at = Column(DateTime, default=datetime.utcnow)
    bridge_node_id = Column(String, nullable=True)
    hop_count = Column(Integer, nullable=True)

    __table_args__ = (UniqueConstraint("packet_hash", name="uq_packet_hash"),)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
