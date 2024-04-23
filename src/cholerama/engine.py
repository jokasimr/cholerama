# SPDX-License-Identifier: BSD-3-Clause

import time
from typing import Any, Dict, Optional

import numpy as np
import matplotlib.colors as mcolors


from . import config
from .player import Player
from .plot import plot


class Engine:
    def __init__(
        self,
        bots: list,
        iterations: int = 100,
        safe: bool = False,
        test: bool = True,
        seed: Optional[int] = None,
        plot_results: bool = False,
        # fps: Optional[int] = 10,
    ):
        if seed is not None:
            np.random.seed(seed)

        self.iterations = iterations
        self._test = test
        self.safe = safe
        self.plot_results = plot_results
        self.token_interval = iterations // config.tokens_per_game
        print("self.token_interval", self.token_interval)
        # self.fps = fps

        self.board = np.zeros((config.ny, config.nx), dtype=int)

        self.bots = {bot.name: bot for bot in bots}
        starting_positions = self.make_starting_positions()
        self.players = {}
        self.player_histories = np.zeros((len(self.bots), self.iterations))
        for i, (bot, pos) in enumerate(zip(self.bots.values(), starting_positions)):
            player = Player(
                name=bot.name,
                number=i + 1,
                pattern=bot.pattern,
                color=bot.color if bot.color is not None else mcolors.to_hex(f"C{i}"),
            )
            p = player.pattern
            self.board[pos[1] : pos[1] + p.shape[0], pos[0] : pos[0] + p.shape[1]] = (
                p * (i + 1)
            )
            self.players[bot.name] = player
            self.player_histories[i, 0] = player.ncells

        # self.player_histories = np.zeros((len(self.players), config.iterations))

        self.xoff = [-1, 0, 1, -1, 1, -1, 0, 1]
        self.yoff = [-1, -1, -1, 0, 0, 1, 1, 1]
        self.xinds = np.empty((8,) + self.board.shape, dtype=int)
        self.yinds = np.empty_like(self.xinds)

        for i, (xo, yo) in enumerate(zip(self.xoff, self.yoff)):
            g = np.meshgrid(
                (np.arange(config.nx) + xo) % config.nx,
                (np.arange(config.ny) + yo) % config.ny,
                indexing="xy",
            )
            self.xinds[i, ...] = g[0]
            self.yinds[i, ...] = g[1]

    def make_starting_positions(self) -> list:
        bound = max(config.pattern_size)
        x = np.random.randint(bound, config.nx - bound, size=len(self.bots))
        y = np.random.randint(bound, config.ny - bound, size=len(self.bots))
        return list(zip(x, y))

    # def execute_player_bot(self, player, t: float, dt: float):
    #     instructions = None
    #     args = {
    #         "iteration": t,
    #         "dt": dt,
    #         "longitude": player.longitude,
    #         "latitude": player.latitude,
    #         "heading": player.heading,
    #         "speed": player.speed,
    #         "vector": player.get_vector(),
    #         "forecast": self.forecast,
    #         "map": self.map_proxy,
    #     }
    #     if self.safe:
    #         try:
    #             instructions = self.bots[player.team].run(**args)
    #         except:  # noqa
    #             pass
    #     else:
    #         instructions = self.bots[player.team].run(**args)
    #     return instructions

    def call_player_bots(self, it: int):
        # TODO: Roll the order of players for each round
        for name, player in ((n, p) for n, p in self.players.items() if p.ncells > 0):
            self.board.setflags(write=False)
            new_cells = None
            args = {
                "iteration": int(it),
                "board": self.board,
                "tokens": int(player.tokens),
            }
            if self.safe:
                try:
                    new_cells = self.bots[name].run(**args)
                except:  # noqa
                    pass
            else:
                new_cells = self.bots[name].run(**args)
            self.board.setflags(write=True)
            if new_cells:
                x, y = new_cells
                ntok = len(x)
                if ntok != len(y):
                    raise ValueError("x and y must have the same length.")
                if ntok > player.tokens:
                    raise ValueError(
                        f"Player {name} does not have enough tokens. "
                        f"Requested {ntok}, but has {player.tokens}."
                    )
                self.board[np.asarray(y), np.asarray(x)] = player.number
                player.tokens -= ntok

    def evolve_board(self):
        neighbors = self.board[self.yinds, self.xinds]
        neighbor_count = np.clip(neighbors, 0, 1).sum(axis=0)
        # self.board = np.where(neighbor_count > 0, 1, self.board)

        # birth_values = np.nan_to_num(
        #     np.nanmedian(np.where(neighbors == 0, np.nan, neighbors), axis=0),
        #     copy=False,
        # ).astype(int)

        #

        alive_mask = self.board > 0
        alive_neighbor_count = np.where(alive_mask, neighbor_count, 0)
        # Apply rules
        new = np.where(
            (alive_neighbor_count == 2) | (alive_neighbor_count == 3), self.board, 0
        )

        birth_mask = ~alive_mask & (neighbor_count == 3)
        # Birth happens always when we have 3 neighbors. When sorted, the most common
        # value will always be in position 7 (=-2).
        birth_values = np.sort(neighbors, axis=0)[-2]
        self.board = np.where(birth_mask, birth_values, new)

    def show_results(self, fname: str):
        if self.plot_results:
            fig, _ = plot(self.board, self.player_histories)
            fig.savefig(fname.replace(".npz", ".pdf"))

    def shutdown(self):
        fname = "results-" + time.strftime("%Y%m%d-%H%M%S") + ".npz"
        np.savez(fname, board=self.board, history=self.player_histories)
        self.show_results(fname)
        # if self.plot_results:
        #     fig, _ = plot(self.board, self.player_histories)
        #     fig.savefig(fname.replace(".npz", ".pdf"))

    def update(self, it: int):
        if it % self.token_interval == 0:
            for player in self.players.values():
                player.tokens += 1
        self.call_player_bots(it)
        self.evolve_board()
        for i, player in enumerate(self.players.values()):
            player.update(self.board)
            self.player_histories[i, it] = player.ncells
            # player.ncells = np.sum(self.board == player.number)

    def run(self):
        # self.initialize_time(start_time)
        for it in range(1, self.iterations + 1):
            # print(it)
            self.update(it)
        print(f"Reached {it} iterations.")
        self.shutdown()
