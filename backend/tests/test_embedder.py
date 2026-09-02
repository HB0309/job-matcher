from app.workers.embedder import cosine_similarity, rerank_by_similarity


def test_cosine_similarity_identical_vectors():
    v = [1.0, 2.0, 3.0]
    assert cosine_similarity(v, v) == 1.0


def test_cosine_similarity_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_no_division_error():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_rerank_by_similarity_orders_by_score():
    profile = [1.0, 0.0]
    candidates = [
        ("far", [0.0, 1.0]),
        ("close", [1.0, 0.1]),
        ("mid", [1.0, 1.0]),
    ]
    ranked = rerank_by_similarity(profile, candidates, top_k=3)
    assert ranked[0] == "close"
    assert ranked[-1] == "far"


def test_rerank_by_similarity_missing_embeddings_sort_last_not_dropped():
    profile = [1.0, 0.0]
    candidates = [
        ("no_embedding", None),
        ("has_embedding", [1.0, 0.0]),
    ]
    ranked = rerank_by_similarity(profile, candidates, top_k=2)
    assert ranked == ["has_embedding", "no_embedding"]


def test_rerank_by_similarity_respects_top_k():
    profile = [1.0, 0.0]
    candidates = [(str(i), [1.0, 0.0]) for i in range(10)]
    assert len(rerank_by_similarity(profile, candidates, top_k=3)) == 3
