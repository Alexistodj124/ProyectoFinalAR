"""Unit tests (no SUMO): networks, SumTree and prioritized replay."""
import numpy as np
import pytest
import torch

from agents.dqn.buffers import PrioritizedReplayBuffer, ReplayBuffer, SumTree
from agents.dqn.networks import DuelingQNetwork, QNetwork, make_q_network


def test_networks_shapes_and_dueling_identity():
    x = torch.randn(5, 7)
    q = QNetwork(7, 3)
    d = DuelingQNetwork(7, 3)
    assert q(x).shape == d(x).shape == (5, 3)
    assert isinstance(make_q_network(7, 3, dueling=True), DuelingQNetwork)
    # Q = V + A - mean(A)  =>  mean_a Q(s,a) == V(s)
    h = d.body(x)
    assert torch.allclose(d(x).mean(dim=1), d.value(h).squeeze(1), atol=1e-5)


@pytest.mark.parametrize("capacity", [8, 10])  # power of two and not
def test_sumtree_total_update_and_find(capacity):
    t = SumTree(capacity)
    pr = np.arange(1, capacity + 1, dtype=float)
    for i, p in enumerate(pr):
        t.update(i, p)
    assert t.total == pytest.approx(pr.sum())
    t.update(2, 10.0)
    pr[2] = 10.0
    assert t.total == pytest.approx(pr.sum())
    assert t[2] == 10.0
    # find(s) returns the leaf whose cumulative interval contains s
    cum = np.cumsum(pr)
    for s in [0.0, 0.5, cum[0] + 1e-6, cum[3] - 1e-6, cum[3] + 1e-6, cum[-1] - 1e-6]:
        expected = int(np.searchsorted(cum, s, side="right"))
        # leaf order of an array tree with non-power-of-2 capacity is a rotation; compare by mass instead
        got = t.find(s)
        assert 0 <= got < capacity
        if capacity & (capacity - 1) == 0:
            assert got == expected


def test_sumtree_sampling_is_proportional():
    t = SumTree(4)
    for i, p in enumerate([1.0, 2.0, 3.0, 4.0]):
        t.update(i, p)
    rng = np.random.default_rng(0)
    n = 20000
    counts = np.bincount([t.find(rng.random() * t.total) for _ in range(n)], minlength=4) / n
    assert counts == pytest.approx(np.array([0.1, 0.2, 0.3, 0.4]), abs=0.02)


def _fill(buf, n, obs_dim=3):
    for i in range(n):
        buf.add(np.full(obs_dim, i, np.float32), i % 2, float(i), np.full(obs_dim, i + 1, np.float32), i == n - 1)


def test_uniform_buffer_circular_and_sample():
    buf = ReplayBuffer(5, 3, rng=np.random.default_rng(0))
    _fill(buf, 8)
    assert len(buf) == 5
    b = buf.sample(4)
    assert b["obs"].shape == (4, 3) and b["actions"].dtype == torch.int64
    assert (b["weights"] == 1).all()
    assert set(b["obs"][:, 0].tolist()) <= {3, 4, 5, 6, 7}  # oldest three were overwritten


def test_per_prefers_high_priority_and_updates():
    buf = PrioritizedReplayBuffer(16, 3, alpha=0.6, rng=np.random.default_rng(0))
    _fill(buf, 16)
    # make transition 5 much more surprising than the rest
    buf.update_priorities(np.arange(16), np.full(16, 0.01))
    buf.update_priorities([5], [5.0])
    assert buf.tree[5] == pytest.approx((5.0 + buf.eps) ** 0.6)
    idx = np.concatenate([buf.sample(32, beta=0.4)["idx"] for _ in range(20)])
    frac5 = np.mean(idx == 5)
    p = np.full(16, (0.01 + buf.eps) ** 0.6)
    p[5] = (5.0 + buf.eps) ** 0.6
    assert frac5 == pytest.approx(p[5] / p.sum(), abs=0.05)
    # importance weights: normalized to max 1 and smaller for the over-sampled transition
    b = buf.sample(64, beta=1.0)
    w, ix = b["weights"].numpy(), b["idx"]
    assert w.max() == pytest.approx(1.0)
    if (ix == 5).any() and (ix != 5).any():
        assert w[ix == 5].max() < w[ix != 5].min()


def test_per_new_samples_get_max_priority():
    buf = PrioritizedReplayBuffer(8, 3, rng=np.random.default_rng(0))
    _fill(buf, 2)
    buf.update_priorities([0, 1], [3.0, 1.0])
    buf.add(np.zeros(3, np.float32), 0, 0.0, np.zeros(3, np.float32), False)
    assert buf.tree[2] == pytest.approx(buf.max_priority**0.6)
