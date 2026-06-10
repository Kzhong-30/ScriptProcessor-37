from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class EventTypeEnum(str, Enum):
    VIEW = "view"
    CLICK = "click"
    ADD_TO_CART = "add_to_cart"
    PURCHASE = "purchase"
    FAVORITE = "favorite"


class EventCreate(BaseModel):
    user_id: int = Field(..., gt=0, description="用户ID")
    product_id: int = Field(..., gt=0, description="商品ID")
    event_type: EventTypeEnum = Field(..., description="事件类型：浏览、点击、加购、购买、收藏")
    session_id: Optional[str] = Field(None, description="会话ID")


class EventResponse(BaseModel):
    id: int
    user_id: int
    product_id: int
    event_type: EventTypeEnum
    timestamp: datetime
    session_id: Optional[str]

    class Config:
        from_attributes = True


class ProductBase(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    category: Optional[str]
    brand: Optional[str]
    tags: Optional[str]
    created_at: datetime


class ProductResponse(ProductBase):
    class Config:
        from_attributes = True


class RecommendedProduct(BaseModel):
    product: ProductResponse
    score: float = Field(..., description="推荐得分")
    sources: List[str] = Field(default_factory=list, description="推荐来源：协同过滤/内容推荐等")


class RecommendationResponse(BaseModel):
    user_id: Optional[int] = None
    total: int = Field(..., description="推荐商品总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")
    items: List[RecommendedProduct] = Field(default_factory=list)


class SimilarProductResponse(BaseModel):
    product_id: int
    total: int
    items: List[RecommendedProduct]


class TrendingProduct(BaseModel):
    product: ProductResponse
    rank: int
    popularity_score: float


class TrendingResponse(BaseModel):
    total: int
    items: List[TrendingProduct]
