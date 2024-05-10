# SPDX-License-Identifier: BSD-3-Clause

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Config:
    nx: int = 1024
    ny: int = 1024
    npatches: Tuple[int] = (4, 4)
    max_name_length: int = 30
    initial_tokens: int = 100
    additional_tokens: int = 200

    @property
    def stepx(self):
        return self.nx // self.npatches[1]

    @property
    def stepy(self):
        return self.ny // self.npatches[0]


config = Config()
