"""Principal component analysis of the covariance / correlation matrix."""

import numpy as np

#
# The portfolio variance decomposes exactly over the eigenbasis of the covariance
# matrix. With Sigma = V L V' (L diagonal, V orthonormal) and y = V'w:
#
#     sigma_p^2 = w' Sigma w = y' L y = sum_i lambda_i * y_i^2
#
# Each term is non-negative, so `lambda_i * y_i^2` is *the* contribution of
# principal component i to the portfolio variance. A large eigenvalue only hurts
# if the portfolio is actually exposed to that direction (y_i != 0) — which is
# exactly what this endpoint separates.
#
# In "correlation" mode the matrix diagonalized is R (= D^-1 Sigma D^-1). Since
# Sigma = D R D, using vol-scaled weights w~ = D w keeps the identity exact:
#     sigma_p^2 = w~' R w~ = sum_i lambda_i * (v_i' w~)^2


def pc_sign_normalized(vec: np.ndarray) -> np.ndarray:
    """Eigenvectors are sign-arbitrary. Orient so the dominant direction is positive,
    which makes 'all loadings same sign' readable as a common market move."""
    s = float(np.sum(vec))
    if abs(s) > 1e-9:
        return vec if s > 0 else -vec
    # Balanced spread: anchor on the largest absolute loading instead.
    k = int(np.argmax(np.abs(vec)))
    return vec if vec[k] >= 0 else -vec


def pc_interpretation(
    vec: np.ndarray,
    explained_ratio: float,
    contribution_pct: float,
    top_pos: list[str],
    top_neg: list[str],
    index: int,
) -> str:
    n_pos = int(np.sum(vec > 1e-6))
    n_neg = int(np.sum(vec < -1e-6))
    dominant = top_pos or top_neg

    if n_pos == 0 or n_neg == 0:
        if index == 1:
            base = ("Common market direction — every holding moves together. "
                    "This is your undiversifiable core risk.")
        elif dominant:
            base = "Broad co-movement of " + ", ".join(dominant) + "."
        else:
            base = "Broad co-movement across the holdings."
    else:
        base = ("Spread: " + ", ".join(top_pos) + " up against " + ", ".join(top_neg) + " down. "
                "A relative-value / rotation factor.")

    if contribution_pct >= 0.5:
        tail = f" Drives {contribution_pct * 100:.0f}% of your portfolio variance."
    elif contribution_pct >= 0.15:
        tail = f" Contributes {contribution_pct * 100:.0f}% of your portfolio variance."
    elif explained_ratio >= 0.10 and contribution_pct < 0.05:
        tail = (f" Present in the market ({explained_ratio * 100:.0f}% of matrix variance) but your "
                f"weights barely touch it ({contribution_pct * 100:.1f}% of your variance) — "
                f"a risk you are already netting out.")
    else:
        tail = f" Minor: {contribution_pct * 100:.1f}% of your portfolio variance."

    return base + tail
