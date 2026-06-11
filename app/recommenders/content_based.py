import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Set
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session
from app.models import Product, Event, EVENT_WEIGHTS
from app.cache import cache
from app.config import settings


class ContentBasedRecommender:
    def __init__(self, db: Session):
        self.db = db
        cached = cache.get("cb_model")
        if cached is not None:
            self.product_idx_map = cached.product_idx_map
            self.idx_product_map = cached.idx_product_map
            self.product_data = cached.product_data
            self.tfidf_matrix = cached.tfidf_matrix
            self.vectorizer = cached.vectorizer
        else:
            self.product_idx_map: Dict[int, int] = {}
            self.idx_product_map: Dict[int, int] = {}
            self.product_data: Optional[pd.DataFrame] = None
            self.tfidf_matrix: Optional[np.ndarray] = None
            self.vectorizer: Optional[TfidfVectorizer] = None
            self._build_features()
            cache.set("cb_model", self, settings.CACHE_TTL_SECONDS)

    def _tokenize_tags(self, tags: Optional[str]) -> str:
        if not tags:
            return ""
        return tags.replace(",", " ").replace("|", " ").replace("，", " ")

    def _build_features(self):
        products = self.db.query(Product).all()
        if not products:
            return

        data = []
        for p in products:
            feature_parts = []
            if p.category:
                feature_parts.append(p.category)
            if p.brand:
                feature_parts.append(p.brand)
            feature_parts.append(self._tokenize_tags(p.tags))
            if p.name:
                feature_parts.append(p.name)
            combined = " ".join(feature_parts)
            data.append({
                "product_id": p.id,
                "features": combined,
                "category": p.category or "",
                "brand": p.brand or ""
            })

        self.product_data = pd.DataFrame(data)
        product_ids = self.product_data["product_id"].tolist()
        self.product_idx_map = {pid: idx for idx, pid in enumerate(product_ids)}
        self.idx_product_map = {idx: pid for idx, pid in enumerate(product_ids)}

        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            max_features=5000
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(self.product_data["features"])

    def is_product_available(self, product_id: int) -> bool:
        return product_id in self.product_idx_map

    def _get_user_profile(self, user_id: int) -> Optional[np.ndarray]:
        events = (
            self.db.query(Event)
            .filter(Event.user_id == user_id)
            .all()
        )
        if not events or self.tfidf_matrix is None:
            return None

        profile_vec = np.zeros((1, self.tfidf_matrix.shape[1]))
        total_weight = 0.0
        has_product = False

        for e in events:
            if e.product_id not in self.product_idx_map:
                continue
            weight = EVENT_WEIGHTS.get(e.event_type, 1.0)
            product_idx = self.product_idx_map[e.product_id]
            product_vec = self.tfidf_matrix.getrow(product_idx).toarray()
            profile_vec += weight * product_vec
            total_weight += weight
            has_product = True

        if not has_product or total_weight == 0:
            return None

        return profile_vec / total_weight

    def recommend_for_user(self, user_id: int, top_n: int = 50) -> List[Tuple[int, float]]:
        if self.tfidf_matrix is None:
            return []

        profile = self._get_user_profile(user_id)
        if profile is None:
            return []

        scores = cosine_similarity(profile, self.tfidf_matrix)[0]

        interacted_ids = set()
        events = self.db.query(Event).filter(Event.user_id == user_id).all()
        for e in events:
            interacted_ids.add(e.product_id)

        candidates = [
            (int(self.idx_product_map[i]), float(scores[i]))
            for i in range(len(scores))
            if int(self.idx_product_map[i]) not in interacted_ids
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_n]

    def get_similar_products(self, product_id: int, top_n: int = 50) -> List[Tuple[int, float]]:
        if product_id not in self.product_idx_map or self.tfidf_matrix is None:
            return []

        product_idx = self.product_idx_map[product_id]
        product_vec = self.tfidf_matrix.getrow(product_idx)
        scores = cosine_similarity(product_vec, self.tfidf_matrix)[0]

        candidates = [
            (int(self.idx_product_map[i]), float(scores[i]))
            for i in range(len(scores))
            if int(self.idx_product_map[i]) != product_id
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_n]

    def get_user_interacted_categories(self, user_id: int) -> Set[str]:
        events = (
            self.db.query(Event, Product.category)
            .join(Product, Event.product_id == Product.id)
            .filter(Event.user_id == user_id)
            .all()
        )
        categories = set()
        for e, cat in events:
            if cat:
                categories.add(cat)
        return categories
        categories = set()
        for e, cat in events:
            if cat:
                categories.add(cat)
        return categories
