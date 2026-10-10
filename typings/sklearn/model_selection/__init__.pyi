from collections.abc import Iterator, Sequence

import numpy as np
from numpy.typing import NDArray

class GroupKFold:
    def __init__(self, n_splits: int = 5) -> None: ...
    def split(
        self,
        X: NDArray[np.float64],
        y: NDArray[np.int_] | None = None,
        groups: Sequence[str] | None = None,
    ) -> Iterator[tuple[NDArray[np.int_], NDArray[np.int_]]]: ...
