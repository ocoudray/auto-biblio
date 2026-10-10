from typing import Self

import numpy as np
from numpy.typing import NDArray

class LogisticRegression:
    coef_: NDArray[np.float64]
    intercept_: NDArray[np.float64]
    def __init__(self, *, C: float = 1.0, max_iter: int = 100) -> None: ...
    def fit(
        self,
        X: NDArray[np.float64],
        y: NDArray[np.int_],
        sample_weight: NDArray[np.float64] | None = None,
    ) -> Self: ...
    def predict_proba(self, X: NDArray[np.float64]) -> NDArray[np.float64]: ...
