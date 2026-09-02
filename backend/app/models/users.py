from sqlalchemy import Column, String, Integer, Text, DateTime, func
from app.database import Base

class SQLUser(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), nullable=True)
    password_hash = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
