from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from app.config import settings
from app.database import get_db, Base, engine
from app.models import Event, Product, User, EventType
from app.schemas import (
    EventCreate, EventResponse,
    ProductResponse,
    RecommendedProduct, RecommendationResponse,
    SimilarProductResponse,
    TrendingProduct, TrendingResponse
)
from app.recommenders.hybrid import HybridRecommender
from app.cache import cache

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
# 电商商品推荐系统 API

基于 FastAPI + PostgreSQL + scikit-learn 构建的商品推荐引擎，包含：

- **用户行为收集**: POST /events 接收浏览/点击/加购/购买/收藏事件
- **协同过滤推荐**: 基于用户-商品交互矩阵，使用 SVD 矩阵分解
- **内容推荐**: 基于商品属性（类别/品牌/标签）计算 TF-IDF 余弦相似度
- **混合推荐**: 综合协同过滤(60%) + 内容推荐(40%) 得分排序
- **冷启动处理**: 新用户返回热门商品，新商品基于内容相似度推荐

## 事件权重
- 浏览(view): 1.0
- 点击(click): 2.0
- 加购(add_to_cart): 5.0
- 购买(purchase): 10.0
- 收藏(favorite): 8.0
    """,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_recommender(db: Session) -> HybridRecommender:
    return HybridRecommender(db)


def _paginate(items: list, page: int, page_size: int):
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return total, items[start:end]


def _build_product_response(db: Session, product_id: int) -> Optional[Product]:
    return db.query(Product).filter(Product.id == product_id).first()


@app.get("/", tags=["系统"], summary="健康检查")
def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "status": "running"
    }


@app.post(
    "/events",
    response_model=EventResponse,
    tags=["行为收集"],
    summary="收集用户行为事件",
    description="""
记录用户与商品的交互行为：
- **view**: 浏览商品
- **click**: 点击商品
- **add_to_cart**: 加入购物车
- **purchase**: 购买商品
- **favorite**: 收藏商品
    """
)
def create_event(event: EventCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.id == event.user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail=f"用户ID {event.user_id} 不存在")
    db_product = db.query(Product).filter(Product.id == event.product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail=f"商品ID {event.product_id} 不存在")

    db_event = Event(
        user_id=event.user_id,
        product_id=event.product_id,
        event_type=EventType(event.event_type.value),
        session_id=event.session_id
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    cache.invalidate_all()
    return db_event


@app.get(
    "/recommendations/similar/{product_id}",
    response_model=SimilarProductResponse,
    tags=["推荐"],
    summary="获取相似商品推荐",
    description="""
基于指定商品获取相似商品：

**相似度计算：**
1. **协同过滤相似度**: 基于 SVD 分解后的商品隐向量余弦相似度
2. **内容相似度**: 基于商品类别/品牌/标签的 TF-IDF 余弦相似度
3. 两者等权重(50%/50%)融合排序

**新商品冷启动**: 若无交互数据，仅使用内容相似度。
    """
)
def get_similar_products(
    product_id: int,
    limit: int = Query(20, ge=1, le=200, description="返回数量")
):
    with next(get_db()) as db:
        db_product = db.query(Product).filter(Product.id == product_id).first()
        if not db_product:
            raise HTTPException(status_code=404, detail=f"商品ID {product_id} 不存在")

        recommender = _get_recommender(db)
        is_cold = recommender.cf.is_product_cold_start(product_id)

        if is_cold:
            raw = recommender.recommend_cold_start_product(product_id, top_n=limit)
        else:
            raw = recommender.get_similar_products(product_id, top_n=limit)

        items: List[RecommendedProduct] = []
        for pid, score, sources in raw:
            p = _build_product_response(db, pid)
            if p:
                label_map = {
                    "collaborative_filtering": "协同过滤",
                    "content_based": "内容推荐"
                }
                sources_display = [label_map.get(s, s) for s in sources]
                items.append(RecommendedProduct(
                    product=ProductResponse.model_validate(p),
                    score=round(score, 6),
                    sources=sources_display
                ))

        return SimilarProductResponse(
            product_id=product_id,
            total=len(items),
            items=items
        )


@app.get(
    "/recommendations/trending",
    response_model=TrendingResponse,
    tags=["推荐"],
    summary="获取热门商品排行榜",
    description="""
获取最近 N 天（默认7天）内的热门商品排行榜。

热度计算公式：
> Σ (事件次数 × 事件权重)

事件权重：购买(10) > 收藏(8) > 加购(5) > 点击(2) > 浏览(1)

若近期事件不足，按新品时间补充。
    """
)
def get_trending(
    limit: int = Query(20, ge=1, le=200, description="返回数量")
):
    with next(get_db()) as db:
        recommender = _get_recommender(db)
        raw = recommender.get_trending_products(top_n=limit)

        items: List[TrendingProduct] = []
        for rank, (pid, score) in enumerate(raw, start=1):
            p = _build_product_response(db, pid)
            if p:
                items.append(TrendingProduct(
                    product=ProductResponse.model_validate(p),
                    rank=rank,
                    popularity_score=round(score, 4)
                ))

        return TrendingResponse(total=len(items), items=items)


@app.get(
    "/recommendations/new",
    response_model=RecommendationResponse,
    tags=["推荐"],
    summary="获取新品推荐",
    description="""
获取近期新上架商品推荐。

新品判定：最近 N 天（默认30天）内上架的商品。

推荐分：1 / (1 + 上架天数/30)，越新分越高。
不足则补充历史商品。
    """
)
def get_new_products(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量")
):
    with next(get_db()) as db:
        recommender = _get_recommender(db)
        raw = recommender.get_new_products(top_n=200)

        total, paged = _paginate(raw, page, page_size)

        items: List[RecommendedProduct] = []
        for pid, score in paged:
            p = _build_product_response(db, pid)
            if p:
                items.append(RecommendedProduct(
                    product=ProductResponse.model_validate(p),
                    score=round(score, 6),
                    sources=["新品推荐"]
                ))

        return RecommendationResponse(
            user_id=None,
            total=total,
            page=page,
            page_size=page_size,
            items=items
        )


@app.get(
    "/recommendations/debug/user-profile/{user_id}",
    tags=["调试"],
    summary="调试：查看用户行为画像",
    include_in_schema=False
)
def debug_user_profile(user_id: int):
    with next(get_db()) as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        events = db.query(Event).filter(Event.user_id == user_id).all()
        type_counts: Dict[str, int] = {}
        product_ids = set()
        for e in events:
            key = e.event_type.value
            type_counts[key] = type_counts.get(key, 0) + 1
            product_ids.add(e.product_id)

        recommender = _get_recommender(db)
        sim_users = recommender.cf.get_similar_users(user_id, top_n=5)

        return {
            "user_id": user_id,
            "username": user.username,
            "is_cold_start": recommender.is_user_cold_start(user_id),
            "total_events": len(events),
            "unique_products": len(product_ids),
            "event_type_counts": type_counts,
            "top_similar_users": [
                {"user_id": uid, "similarity": round(s, 4)}
                for uid, s in sim_users
            ]
        }


@app.get(
    "/recommendations/{user_id}",
    response_model=RecommendationResponse,
    tags=["推荐"],
    summary="获取用户个性化推荐",
    description="""
为指定用户生成个性化推荐列表：

**推荐策略：**
1. 若用户行为事件数 < 阈值（冷启动用户）→ 返回热门商品
2. 否则 → 混合推荐（协同过滤 60% + 内容推荐 40%）

支持分页和数量限制。
    """
)
def get_user_recommendations(
    user_id: int,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量")
):
    with next(get_db()) as db:
        db_user = db.query(User).filter(User.id == user_id).first()
        if not db_user:
            raise HTTPException(status_code=404, detail=f"用户ID {user_id} 不存在")

        recommender = _get_recommender(db)
        is_cold = recommender.is_user_cold_start(user_id)

        if is_cold:
            raw = recommender.recommend_cold_start_user(top_n=200)
        else:
            raw = recommender.recommend_for_user(user_id, top_n=200)

        total, paged = _paginate(raw, page, page_size)

        items: List[RecommendedProduct] = []
        for pid, score, sources in paged:
            product = _build_product_response(db, pid)
            if product:
                if is_cold and "trending" in sources:
                    sources_display = ["冷启动(热门商品)"]
                else:
                    label_map = {
                        "collaborative_filtering": "协同过滤",
                        "content_based": "内容推荐",
                        "trending": "热门推荐"
                    }
                    sources_display = [label_map.get(s, s) for s in sources]
                items.append(RecommendedProduct(
                    product=ProductResponse.model_validate(product),
                    score=round(score, 6),
                    sources=sources_display
                ))

        return RecommendationResponse(
            user_id=user_id,
            total=total,
            page=page,
            page_size=page_size,
            items=items
        )
