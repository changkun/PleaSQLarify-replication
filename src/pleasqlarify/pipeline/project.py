"""2-D projection of the action space for the Action Space view (spec 12).

The paper uses UMAP on the query distance matrix ``1 - S`` (p. 9). UMAP is an
optional extra; the offline default is classical MDS (deterministic, numpy-only),
which is adequate for the small candidate sets (N <= 50) and keeps the interface
runnable without heavy dependencies (spec 12, A17).
"""

from __future__ import annotations

import numpy as np


def classical_mds(dist: np.ndarray, dim: int = 2) -> np.ndarray:
    """Deterministic classical multidimensional scaling."""
    n = dist.shape[0]
    if n == 0:
        return np.zeros((0, dim))
    if n == 1:
        return np.zeros((1, dim))
    d2 = dist**2
    j = np.eye(n) - np.ones((n, n)) / n
    b = -0.5 * j @ d2 @ j
    b = (b + b.T) / 2.0  # symmetrize
    vals, vecs = np.linalg.eigh(b)
    order = np.argsort(vals)[::-1]
    vals = vals[order]
    vecs = vecs[:, order]
    coords = np.zeros((n, dim))
    for k in range(min(dim, n)):
        lam = max(vals[k], 0.0)
        coords[:, k] = vecs[:, k] * np.sqrt(lam)
    return coords


def umap_project(dist: np.ndarray, dim: int = 2, random_state: int = 42) -> np.ndarray:  # pragma: no cover - optional
    """UMAP on a precomputed distance matrix (the paper's projection, spec 12)."""
    import umap

    n = dist.shape[0]
    if n <= dim + 1:
        return classical_mds(dist, dim)
    reducer = umap.UMAP(
        n_components=dim,
        metric="precomputed",
        random_state=random_state,
        n_neighbors=min(15, n - 1),
    )
    return reducer.fit_transform(dist)


def project_2d(sim: np.ndarray, use_umap: bool = False) -> np.ndarray:
    """Project candidates to 2-D from the output-similarity matrix S."""
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)
    dist = np.clip(dist, 0.0, None)
    if use_umap:
        return umap_project(dist)
    return classical_mds(dist)


__all__ = ["classical_mds", "umap_project", "project_2d"]
