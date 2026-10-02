import numpy as np

from ai_core.rag.chunker import semantic_chunks
from ai_core.rag.embeddings import HashingEmbedder
from ai_core.vision.federated import FederatedCoordinator, clip_delta, fedavg, pack, unpack


def test_fedavg_weighted():
    a = {"w": np.array([1.0, 1.0], dtype="float32")}
    b = {"w": np.array([4.0, 4.0], dtype="float32")}
    out = fedavg([(a, 1), (b, 3)])
    assert np.allclose(out["w"], [3.25, 3.25])


def test_clip_and_roundtrip_and_round():
    d = {"w": np.full((10,), 10.0, dtype="float32")}
    assert np.linalg.norm(clip_delta(d, 1.0)["w"]) <= 1.0001
    assert np.allclose(unpack(pack(d))["w"], d["w"])
    coord = FederatedCoordinator({"w": np.zeros(3, dtype="float32")}, min_clients=2, clip_norm=100)
    assert coord.submit("a", {"w": np.ones(3, dtype="float32")}, 10) is None
    summary = coord.submit("b", {"w": np.ones(3, dtype="float32") * 3}, 10)
    assert summary == {"version": 1, "clients": 2} and np.allclose(coord.global_weights["w"], 2.0)


def test_semantic_chunking_respects_size():
    text = " ".join(f"Sentence number {i} talks about thermal throttling limits." for i in range(60))
    chunks = semantic_chunks(text, HashingEmbedder(), max_chars=400)
    assert len(chunks) > 1 and all(len(c) <= 460 for c in chunks)
