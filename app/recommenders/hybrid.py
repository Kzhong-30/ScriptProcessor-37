from typing import List, Tuple, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, case
from datetime import datetime, timedelta
from app.models import Event, Product, EVENT_WEIGHTS, EventType
from app.recommenders.collaborative_filtering import CollaborativeFiltering
from app.recommenders.content_based import ContentBasedRecommender
from app.config import settings


class HybridRecommender:
    def __init__(self, db: Session):
        self.db = db
        self.cf = CollaborativeFiltering(db)
        self.cb = ContentBasedRecommender(db)

    def _normalize_scores(
        self, scores: List[Tuple[int, float]]
    ) -> Dict[int, float]:
        if not scores:
            return {}
        vals = [s for _, s in scores]
        min_v, max_v = min(vals), max(vals)
        if max_v - min_v < 1e-8:
            return {pid: 1.0 for pid, _ in scores}
        return {pid: (s - min_v) / (max_v - min_v) for pid, s in scores}

    def recommend_for_user(
        self, user_id: int, top_n: int = 50
    ) -> List[Tuple[int, float, List[str]]]:
        cf_weight = settings.CF_WEIGHT
        cb_weight = settings.CONTENT_WEIGHT

        cf_scores_raw = self.cf.recommend_for_user(user_id, top_n=top_n * 2)
        cb_scores_raw = self.cb.recommend_for_user(user_id, top_n=top_n * 2)

        cf_scores = self._normalize_scores(cf_scores_raw)
        cb_scores = self._normalize_scores(cb_scores_raw)

        all_product_ids = set(cf_scores.keys()) | set(cb_scores.keys())
        combined: Dict[int, Tuple[float, List[str]]] = {}

        for pid in all_product_ids:
            score = 0.0
            sources = []
            if pid in cf_scores:
                score += cf_weight * cf_scores[pid]
                sources.append("collaborative_filtering")
            if pid in cb_scores:
                score += cb_weight * cb_scores[pid]
                sources.append("content_based")
            combined[pid] = (score, sources)

        results = [
            (pid, score, sources)
            for pid, (score, sources) in combined.items()
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]

    def recommend_cold_start_user(
        self, top_n: int = 50
    ) -> List[Tuple[int, float, List[str]]]:
        trending = self.get_trending_products(top_n=top_n * 2)
        results = [
            (pid, score, ["trending"])
            for pid, score in trending
        ]
        return results[:top_n]

    def recommend_cold_start_product(
        self, product_id: int, top_n: int = 50
    ) -> List[Tuple[int, float, List[str]]]:
        similar = self.cb.get_similar_products(product_id, top_n=top_n)
        return [
            (pid, score, ["content_based"])
            for pid, score in similar
        ]

    def get_similar_products(
        self, product_id: int, top_n: int = 50
    ) -> List[Tuple[int, float, List[str]]]:
        cf_similar = self.cf.get_similar_products(product_id, top_n=top_n * 2)
        cb_similar = self.cb.get_similar_products(product_id, top_n=top_n * 2)

        if not cf_similar and not cb_similar:
            return []

        cf_norm = self._normalize_scores(cf_similar)
        cb_norm = self._normalize_scores(cb_similar)

        cf_w = 0.5
        cb_w = 0.5

        all_ids = set(cf_norm.keys()) | set(cb_norm.keys())
        combined: Dict[int, Tuple[float, List[str]]] = {}

        for pid in all_ids:
            score = 0.0
            sources = []
            if pid in cf_norm:
                score += cf_w * cf_norm[pid]
                sources.append("collaborative_filtering")
            if pid in cb_norm:
                score += cb_w * cb_norm[pid]
                sources.append("content_based")
            combined[pid] = (score, sources)

        results = [
            (pid, score, sources)
            for pid, (score, sources) in combined.items()
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]

    def get_trending_products(
        self, top_n: int = 50
    ) -> List[Tuple[int, float]]:
        since = datetime.now() - timedelta(days=settings.TRENDING_WINDOW_DAYS)

        results = (
            self.db.query(
                Event.product_id,
                func.sum(
                    case(
                        (Event.event_type == EventType.VIEW, EVENT_WEIGHTS[EventType.VIEW]),
                        (Event.event_type == EventType.CLICK, EVENT_WEIGHTS[EventType.CLICK]),
                        (Event.event_type == EventType.ADD_TO_CART, EVENT_WEIGHTS[EventType.ADD_TO_CART]),
                        (Event.event_type == EventType.PURCHASE, EVENT_WEIGHTS[EventType.PURCHASE]),
                        (Event.event_type == EventType.FAVORITE, EVENT_WEIGHTS[EventType.FAVORITE]),
                        else_=0.0
                    )
                ).label("score")
            )
            .filter(Event.timestamp >= since)
            .group_by(Event.product_id)
            .order_by(desc("score"))
            .limit(top_n)
            .all()
        )

        scored = [(pid, float(score)) for pid, score in results if score > 0]

        if len(scored) < top_n:
            all_products = (
                self.db.query(Product.id)
                .order_by(desc(Product.created_at))
                .limit(top_n)
                .all()
            )
            existing = {pid for pid, _ in scored}
            for (pid,) in all_products:
                if pid not in existing:
                    scored.append((pid, 0.0))
                    existing.add(pid)
                    if len(scored) >= top_n:
                        break

        return scored[:top_n]

    def get_new_products(self, top_n: int = 50) -> List[Tuple[int, float]]:
        since = datetime.now() - timedelta(days=settings.NEW_PRODUCT_WINDOW_DAYS)
        products = (
            self.db.query(Product)
            .filter(Product.created_at >= since)
            .order_by(desc(Product.created_at))
            .limit(top_n)
            .all()
        )

        if len(products) < top_n:
            additional = (
                self.db.query(Product)
                .filter(Product.created_at < since)
                .order_by(desc(Product.created_at))
                .limit(top_n - len(products))
                .all()
            )
            products.extend(additional)

        results = []
        for p in products:
            age_days = max(0.0, (datetime.now() - p.created_at.replace(tzinfo=None)).total_seconds() / 86400)
            recency_score = 1.0 / (1.0 + age_days / settings.NEW_PRODUCT_WINDOW_DAYS)
            results.append((p.id, recency_score))

        return results

    def is_user_cold_start(self, user_id: int) -> bool:
        return self.cf.is_user_cold_start(user_id)
