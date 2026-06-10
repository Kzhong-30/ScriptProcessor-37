from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Enum, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class EventType(str, enum.Enum):
    VIEW = "view"
    CLICK = "click"
    ADD_TO_CART = "add_to_cart"
    PURCHASE = "purchase"
    FAVORITE = "favorite"


EVENT_WEIGHTS = {
    EventType.VIEW: 1.0,
    EventType.CLICK: 2.0,
    EventType.ADD_TO_CART: 5.0,
    EventType.PURCHASE: 10.0,
    EventType.FAVORITE: 8.0,
}


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(200), unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False, index=True)
    description = Column(Text)
    price = Column(Float, nullable=False)
    category = Column(String(100), index=True)
    brand = Column(String(100), index=True)
    tags = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    events = relationship("Event", back_populates="product", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(Enum(EventType), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    session_id = Column(String(100))

    user = relationship("User", back_populates="events")
    product = relationship("Product", back_populates="events")

    __table_args__ = (
        Index("ix_events_user_product", "user_id", "product_id"),
    )
