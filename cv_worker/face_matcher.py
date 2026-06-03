from collections import defaultdict
from statistics import mean
from typing import Dict, List, Optional, Tuple

import numpy as np


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(1.0 - np.dot(a, b))


def match_face(
    query_embedding: np.ndarray,
    embeddings: Dict[str, List[np.ndarray]],
    threshold: float = 0.65,
    skip_ids: set | None = None,
) -> Tuple[Optional[str], Optional[float], str]:
    if skip_ids is None:
        skip_ids = set()

    votes = defaultdict(list)
    for student_id, student_embs in embeddings.items():
        if student_id in skip_ids:
            continue
        for emb in student_embs:
            dist = cosine_distance(query_embedding, emb)
            if dist < threshold:
                votes[student_id].append(dist)

    if not votes:
        return None, None, "UNKNOWN"

    winner = max(votes, key=lambda sid: (len(votes[sid]), -mean(votes[sid])))
    avg_dist = mean(votes[winner])
    status = "MATCHED" if len(votes[winner]) >= 2 else "LOW_CONFIDENCE"
    return winner, avg_dist, status
