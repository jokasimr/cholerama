# SPDX-License-Identifier: BSD-3-Clause

import time
from multiprocessing import Process
from multiprocessing.managers import SharedMemoryManager


import numpy as np


from . import config
from .engine import Engine
from .graphics import Graphics

# from .map import MapData
from .player import Player
from .plot import plot
from .scores import read_round, finalize_scores
from .tools import array_from_shared_mem, make_starting_positions, make_color


# class Clock:
#     def __init__(self):
#         self._start_time = None

#     @property
#     def start_time(self):
#         if self._start_time is None:
#             self._start_time = time.time()
#         return self._start_time


# clock = Clock()


def spawn_graphics(*args):
    graphics = Graphics(*args)
    graphics.run()


def spawn_engine(*args):
    engine = Engine(*args)
    engine.run()


def play(
    bots, iterations, seed=None, fps=None, safe=False, test=True, show_results=False
):

    # self.iterations = iterations
    # self._test = test
    # self.safe = safe
    # show_results = show_results
    # self.token_interval = max(1, iterations // config.additional_tokens)
    # n_sub_processes = max(ncores - 1, 1)
    # rounds_played = 0 if test else read_round()

    board_old = np.zeros((config.ny, config.nx), dtype=int)
    board_new = board_old.copy()
    player_histories = np.zeros((len(bots), iterations + 1), dtype=int)

    # Divide the board into as many patches as there are players, and try to make the
    # patches as square as possible

    # # decompose number of players into prime numbers
    # nplayers = len(bots)
    # factors = []
    # for i in range(2, nplayers + 1):
    #     while nplayers % i == 0:
    #         factors.append(i)
    #         nplayers //= i
    # # now group the factors into 2 groups because the board is 2D. Try to make the
    # # groups as close to each other in size as possible, when multiplied together
    # group1 = []
    # group2 = []
    # for f in factors:
    #     if np.prod(group1) < np.prod(group2):
    #         group1.append(f)
    #     else:
    #         group2.append(f)

    starting_patches = make_starting_positions(len(bots))
    # starting_positions = np.full((len(bots), 2), 500, dtype=int)
    patch_size = (config.ny // config.npatches[0], config.nx // config.npatches[1])

    if isinstance(bots, dict):
        dict_of_bots = {
            name: bot.Bot(
                number=i + 1, name=name, patch_location=patch, patch_size=patch_size
            )
            for i, ((name, bot), patch) in enumerate(
                zip(bots.items(), starting_patches)
            )
        }
    else:
        dict_of_bots = {
            bot.AUTHOR: bot.Bot(number=i + 1, name=bot.AUTHOR, patch=patch)
            for i, (bot, patch) in enumerate(zip(bots, starting_patches))
        }

    # starting_positions = make_starting_positions(len(self.bots))
    players = {}
    # self.player_histories = np.zeros((len(self.bots), self.iterations + 1), dtype=int)
    stepx = config.nx // config.npatches[1]
    stepy = config.ny // config.npatches[0]
    for i, (bot, patch) in enumerate(zip(dict_of_bots.values(), starting_patches)):
        player = Player(
            name=bot.name,
            number=i + 1,
            pattern=bot.pattern,
            color=make_color(i if bot.color is None else bot.color),
            patch=patch,
        )
        p = player.pattern
        x, y = p.x, p.y
        # print(x, y)
        x = (np.asarray(x) + (patch[1] * stepx)) % config.nx
        y = (np.asarray(y) + (patch[0] * stepy)) % config.ny
        # print(x, y)
        board_old[y, x] = player.number

        # board_old[pos[1] : pos[1] + p.shape[0], pos[0] : pos[0] + p.shape[1]] = p * (
        #     i + 1
        # )
        players[bot.name] = player
        player_histories[i, 0] = player.ncells

    # # starting_positions = make_starting_positions(len(self.bots))

    # groups = np.array_split(list(bots.keys()), n_sub_processes)

    # # Split the board along the x dimension into n_sub_processes
    # board_ind_start = np.linspace(0, config.ny, n_sub_processes + 1, dtype=int)
    game_flow = np.zeros(2, dtype=bool)  # pause, exit_from_graphics

    # print("groups:", groups)
    # print("board_ind_start:", board_ind_start)

    buffer_mapping = {
        "board_old": board_old,
        "board_new": board_new,
        "player_histories": player_histories,
        # "cell_counts": cell_counts,
        "game_flow": game_flow,
    }

    results = {"board": board_old}
    results.update(
        {f"{name}_history": player_histories[i] for i, name in enumerate(players)}
    )
    results.update({f"{name}_color": player.color for name, player in players.items()})

    shared_arrays = {}

    with SharedMemoryManager() as smm:

        buffers = {}
        for key, arr in buffer_mapping.items():
            mem = smm.SharedMemory(size=arr.nbytes)
            shared_arrays[key] = array_from_shared_mem(mem, arr.dtype, arr.shape)
            shared_arrays[key][...] = arr
            buffers[key] = (mem, arr.dtype, arr.shape)

        graphics = Process(
            target=spawn_graphics,
            args=(
                players,
                fps,
                test,
                buffers,
            ),
        )

        # engines = []
        # # bot_index_begin = 0
        # for i, group in enumerate(groups):
        #     engines.append(
        engine = Process(
            target=spawn_engine,
            args=(
                # i,
                # board_ind_start[i],
                # board_ind_start[i + 1],
                bots,
                players,
                iterations,
                safe,
                test,
                seed,
                # show_results,
                buffers,
            ),
        )

        # bot_index_begin += len(group)

        graphics.start()
        # for engine in engines:
        engine.start()
        graphics.join()
        # for engine in engines:
        engine.join()

        # shutdown
        for i, player in enumerate(players.values()):
            player.peak = shared_arrays["player_histories"][i].max()
        finalize_scores(players, test=test)
        fname = "results-" + time.strftime("%Y%m%d-%H%M%S") + ".npz"
        results["board"][...] = shared_arrays["board_old"][...]
        for i, name in enumerate(players):
            results[f"{name}_history"][...] = shared_arrays["player_histories"][i][...]

    np.savez(fname, **results)
    plot(fname=fname.replace(".npz", ".pdf"), show=show_results, **results)
    return results
