import numpy as np
from numpy.typing import NDArray

def roc_auc_score(y_true: NDArray[np.int_], y_score: NDArray[np.float64]) -> float: ...
