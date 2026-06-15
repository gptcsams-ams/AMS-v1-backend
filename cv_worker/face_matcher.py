from typing import Optional, Tuple

import numpy as np


def match_face(
    query_embedding: np.ndarray,   # shape (512,), L2-normalized
    embeddings:      np.ndarray,   # shape (N, 512), L2-normalized
    student_ids:     list,         # length N, same order as embeddings rows
    threshold:       float = 0.65,
) -> Tuple[Optional[str], float, str]:
    """
    Vectorized cosine similarity — single numpy matrix multiply.
    O(N) not O(N*K). ~0.1ms for 1000 students on CPU.

    Returns (student_id, similarity_score, status).
    status: MATCHED | LOW_CONFIDENCE | UNKNOWN
    """
    if len(student_ids) == 0 or embeddings.shape[0] == 0:
        return None, 0.0, "UNKNOWN"

    norm = np.linalg.norm(query_embedding)
    if norm > 0:
        query_embedding = query_embedding / norm

    # Single BLAS call — cosine similarity for every student at once
    similarities = embeddings @ query_embedding  # shape (N,)

    best_idx   = int(np.argmax(similarities))
    best_score = float(similarities[best_idx])
    best_id    = student_ids[best_idx]

    if best_score >= threshold:
        return best_id, best_score, "MATCHED"
    elif best_score >= threshold - 0.10:
        return best_id, best_score, "LOW_CONFIDENCE"
    else:
        return None, best_score, "UNKNOWN"
