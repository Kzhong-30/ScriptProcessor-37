import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics.pairwise import cosine_similarity
from scipy.sparse import csr_matrix
from sqlalchemy.orm import Session
from app.models import Event, Product, User, EVENT_WEIGHTS, EventType
from app.config import settings


class CollaborativeFiltering:
    def __init__(self, db: Session):
        self.db = db
        self.user_idx_map: Dict[int, int] = {}
        self.idx_user_map: Dict[int, int] = {}
        self.product_idx_map: Dict[int, int] = {}
        self.idx_product_map: Dict[int, int] = {}
        self.svd: Optional[TruncatedSVD] = None
        self.user_factors: Optional[np.ndarray] = None
        self.product_factors: Optional[np.ndarray] = None
        self.interaction_matrix: Optional[csr_matrix] = None
        self._build_matrix()

    def _build_matrix(self):
        events = self.db.query(Event).all()
        if not events:
            return

        data = []
        for e in events:
            weight = EVENT_WEIGHTS.get(e.event_type, 1.0)
            data.append({
                "user_id": e.user_id,
                "product_id": e.product_id,
                "weight": weight
            })

        df = pd.DataFrame(data)
        agg_df = df.groupby(["user_id", "product_id"])["weight"].sum().reset_index()

        user_ids = sorted(agg_df["user_id"].unique())
        product_ids = sorted(agg_df["product_id"].unique())

        self.user_idx_map = {uid: idx for idx, uid in enumerate(user_ids)}
        self.idx_user_map = {idx: uid for idx, uid in enumerate(user_ids)}
        self.product_idx_map = {pid: idx for idx, pid in enumerate(product_ids)}
        self.idx_product_map = {idx: pid for idx, pid in enumerate(product_ids)}

        rows = agg_df["user_id"].map(self.user_idx_map).values
        cols = agg_df["product_id"].map(self.product_idx_map).values
        values = agg_df["weight"].values.astype(np.float32)

        n_users = len(user_ids)
        n_products = len(product_ids)
        self.interaction_matrix = csr_matrix((values, (rows, cols)), shape=(n_users, n_products))

        n_components = min(settings.SVD_N_COMPONENTS, max(1, n_users - 1), max(1, n_products - 1))
        self.svd = TruncatedSVD(n_components=n_components, random_state=42)
        self.user_factors = self.svd.fit_transform(self.interaction_matrix)
        self.product_factors = self.svd.components_.T

    def is_user_cold_start(self, user_id: int) -> bool:
        if user_id not in self.user_idx_map:
            return True
        user_idx = self.user_idx_map[user_id]
        row = self.interaction_matrix.getrow(user_idx)
        return row.nnz < settings.COLD_START_EVENT_THRESHOLD

    def is_product_cold_start(self, product_id: int) -> bool:
        return product_id not in self.product_idx_map

    def recommend_for_user(self, user_id: int, top_n: int = 50) -> List[Tuple[int, float]]:
        if user_id not in self.user_idx_map or self.user_factors is None:
            return []

        user_idx = self.user_idx_map[user_id]
        user_vec = self.user_factors[user_idx].reshape(1, -1)
        scores = cosine_similarity(user_vec, self.product_factors)[0]

        interacted = set(self.interaction_matrix.getrow(user_idx).nonzero()[1])
        candidate_indices = [i for i in range(len(scores)) if i not in interacted]

        if not candidate_indices:
            return []

        candidate_scores = [(int(self.idx_product_map[i]), float(scores[i])) for i in candidate_indices]
        candidate_scores.sort(key=lambda x: x[1], reverse=True)
        return candidate_scores[:top_n]

    def get_similar_products(self, product_id: int, top_n: int = 50) -> List[Tuple[int, float]]:
        if product_id not in self.product_idx_map or self.product_factors is None:
            return []

        product_idx = self.product_idx_map[product_id]
        product_vec = self.product_factors[product_idx].reshape(1, -1)
        scores = cosine_similarity(product_vec, self.product_factors)[0]

        candidates = [
            (int(self.idx_product_map[i]), float(scores[i]))
            for i in range(len(scores))
            if self.idx_product_map[i] != product_id
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_n]

    def get_similar_users(self, user_id: int, top_n: int = 20) -> List[Tuple[int, float]]:
        if user_id not in self.user_idx_map or self.user_factors is None:
            return []

        user_idx = self.user_idx_map[user_id]
        user_vec = self.user_factors[user_idx].reshape(1, -1)
        scores = cosine_similarity(user_vec, self.user_factors)[0]

        candidates = [
            (int(self.idx_user_map[i]), float(scores[i]))
            for i in range(len(scores))
            if self.idx_user_map[i] != user_id
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:top_n]
