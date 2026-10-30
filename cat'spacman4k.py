#!/usr/bin/env python3
"""
AC KONDO'S PACMAN — Python arcade port 1.x$infdev
Zero-shot full engine: levels 1-256, arcade graphics/audio (procedural, files=off).

Main menu: Play Game · Help · About · Exit
© AC Kondo 1999-2026. Inspired by Namco Pac-Man (1980) arcade.

Run:  python3 'utrapacbykondov1.x$infdev.py'
Requires: pygame-ce (import pygame)
"""

from __future__ import annotations

import array
import math
import random
import sys
from enum import Enum, auto

import pygame

VERSION = "1.x$infdev"
TITLE = "AC KONDO'S PACMAN"
SUBTITLE = f"Python arcade port {VERSION}"
COPYRIGHT = "© AC Kondo 1999-2026 — All rights reserved"
MAX_LEVEL = 256

TILE = 8
COLS, ROWS = 28, 31
HUD_TILES = 3
LOGICAL_W = COLS * TILE
LOGICAL_H = (ROWS + HUD_TILES + 2) * TILE
SCALE = 3
FPS = 60

TUNNEL_ROW = 14

# A tile is 8px. No actor may move more than MAX_STEP per substep, or it can
# step clean over a centre and never register it.
MAX_STEP = TILE / 4.0
# Cornering: a perpendicular turn may be committed this many pixels before a
# junction centre, which is what makes the turn read as instant. Reversals are
# always immediate, at any position.
CORNER_WINDOW = TILE / 2.0
# How fast an actor slides back onto the corridor line after a pre-turn.
DRIFT_RATE = 220.0

BLACK = (0, 0, 0)
WALL_BLUE = (33, 33, 255)
DOOR_PINK = (255, 184, 255)
DOT = (255, 183, 174)
PAC = (255, 255, 0)
BLINKY = (255, 0, 0)
PINKY = (255, 184, 255)
INKY = (0, 255, 255)
CLYDE = (255, 184, 82)
FRIGHT = (24, 24, 150)
WHITE = (255, 255, 255)
YELLOW = (255, 255, 0)
RED_TXT = (255, 0, 0)
GREEN = (0, 255, 0)

MAZE = [
    "############################",
    "#............##............#",
    "#.####.#####.##.#####.####.#",
    "#o####.#####.##.#####.####o#",
    "#.####.#####.##.#####.####.#",
    "#..........................#",
    "#.####.##.########.##.####.#",
    "#.####.##.########.##.####.#",
    "#......##....##....##......#",
    "######.##### ## #####.######",
    "     #.##### ## #####.#     ",
    "     #.##          ##.#     ",
    "     #.## ###--### ##.#     ",
    "######.## #      # ##.######",
    "      .   #      #   .      ",
    "######.## #      # ##.######",
    "     #.## ######## ##.#     ",
    "     #.##          ##.#     ",
    "     #.## ######## ##.#     ",
    "######.## ######## ##.######",
    "#............##............#",
    "#.####.#####.##.#####.####.#",
    "#.####.#####.##.#####.####.#",
    "#o..##................##..o#",
    "###.##.##.########.##.##.###",
    "###.##.##.########.##.##.###",
    "#......##....##....##......#",
    "#.##########.##.##########.#",
    "#.##########.##.##########.#",
    "#..........................#",
    "############################",
]

UP, DOWN, LEFT, RIGHT = "U", "D", "L", "R"
DIRV = {UP: (0, -1), DOWN: (0, 1), LEFT: (-1, 0), RIGHT: (1, 0)}
AXIS = {UP: 1, DOWN: 1, LEFT: 0, RIGHT: 0}  # 0 = horizontal travel
OPPOSITE = {UP: DOWN, DOWN: UP, LEFT: RIGHT, RIGHT: LEFT}
TURNS = (UP, DOWN, LEFT, RIGHT)


# ---------------------------------------------------------------------------
# Level table
# ---------------------------------------------------------------------------
FRUIT_BY_LEVEL = [100, 300, 500, 700, 1000, 2000, 3000, 5000]
FRUIT_COLOR = [(255, 0, 0), (255, 184, 82), (255, 184, 255), (0, 255, 255)]


def level_params(lv: int) -> dict:
    lv = max(1, min(lv, MAX_LEVEL))
    pac = min(96.0, 72.0 + lv * 1.6)
    ghost = min(104.0, 68.0 + lv * 1.9)
    return {
        "pac_speed": pac,
        "ghost_speed": ghost,
        "fright_speed": max(40.0, ghost * 0.55),
        "tunnel_speed": ghost * 0.45,
        "fright_time": max(1.0, 7.0 - lv * 0.5),
        "flash": 2.0,
        "elroy1": max(5, 20 - lv),
        "elroy2": max(2, 10 - lv),
        "fruit": FRUIT_BY_LEVEL[min(len(FRUIT_BY_LEVEL) - 1, (lv - 1) // 4)],
        "fruit_score": FRUIT_BY_LEVEL[min(len(FRUIT_BY_LEVEL) - 1, (lv - 1) // 4)],
        "scatter_chase": _scatter_chase(lv),
    }


def _scatter_chase(lv: int):
    if lv == 1:
        return [7, 20, 7, 20, 5, 20, 5, 9999]
    if lv < 5:
        return [7, 20, 7, 20, 5, 1033, 0.01, 9999]
    return [5, 20, 5, 20, 5, 1037, 0.01, 9999]


# ---------------------------------------------------------------------------
# Maze helpers
# ---------------------------------------------------------------------------
def center_of(tx: int, ty: int):
    return tx * TILE + TILE / 2.0, (ty + HUD_TILES) * TILE + TILE / 2.0


def tile_of(x: float, y: float):
    return (
        int(round((x - TILE / 2.0) / TILE)),
        int(round((y - HUD_TILES * TILE - TILE / 2.0) / TILE)),
    )


def tile_at(maze, tx: int, ty: int) -> str:
    if ty == TUNNEL_ROW:
        tx %= COLS
    if ty < 0 or ty >= ROWS or tx < 0 or tx >= COLS:
        return "#"
    return maze[ty][tx]


def passable(maze, tx: int, ty: int, allow_gate: bool = False) -> bool:
    if ty == TUNNEL_ROW and (tx < 0 or tx >= COLS):
        return True
    c = tile_at(maze, tx, ty)
    if c == "#":
        return False
    if c == "-" and not allow_gate:
        return False
    return True


# ---------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------
class Actor:
    """Actors live on exact tile centres and travel one axis at a time.

    A perpendicular turn is *committed* up to CORNER_WINDOW pixels early, and
    DRIFT slides the actor back onto the corridor line, so the turn reads as
    instant without teleporting.
    """

    def __init__(self, tx: int, ty: int, dir: str = LEFT):
        self.x, self.y = center_of(tx, ty)
        self.dir = dir
        self.pending_turn = None
        self.spawn = (tx, ty)

    @property
    def tile(self):
        return tile_of(self.x, self.y)

    @property
    def rect(self):
        return pygame.Rect(int(self.x) - 4, int(self.y) - 4, 8, 8)

    def at_center(self, tol: float) -> bool:
        tx, ty = self.tile
        cx, cy = center_of(tx, ty)
        return abs(self.x - cx) <= tol and abs(self.y - cy) <= tol

    def snap(self):
        tx, ty = self.tile
        self.x, self.y = center_of(tx, ty)
        return tx, ty

    def approach_center(self, tol: float):
        """Forward distance to the next centre, or None if already past it."""
        tx, ty = self.tile
        cx, cy = center_of(tx, ty)
        d = (cx - self.x) if AXIS[self.dir] == 0 else (cy - self.y)
        if AXIS[self.dir] == 0:
            d *= DIRV[self.dir][0]
        else:
            d *= DIRV[self.dir][1]
        if d < -tol:
            return None
        return max(0.0, d)

    def drift(self, dt: float):
        """Pull back onto the corridor line after a pre-turn."""
        tx, ty = self.tile
        cx, cy = center_of(tx, ty)
        delta = (cy - self.y) if AXIS[self.dir] == 0 else (cx - self.x)
        if delta == 0:
            return
        move = DRIFT_RATE * dt
        if abs(delta) <= move:
            if AXIS[self.dir] == 0:
                self.y = cy
            else:
                self.x = cx
        else:
            step = move if delta > 0 else -move
            if AXIS[self.dir] == 0:
                self.y += step
            else:
                self.x += step

    def advance(self, distance: float):
        dx, dy = DIRV[self.dir]
        self.x += dx * distance
        self.y += dy * distance
        if self.y > (TUNNEL_ROW + HUD_TILES + 1) * TILE:
            return
        if self.x < -TILE / 2.0:
            self.x = LOGICAL_W + TILE / 2.0
        elif self.x > LOGICAL_W + TILE / 2.0:
            self.x = -TILE / 2.0

    def commit_turn(self, maze, allow_gate=False):
        nd = self.pending_turn
        if nd is None or nd == self.dir:
            return
        if nd == OPPOSITE[self.dir]:
            self.dir = nd
            self.pending_turn = None
            return
        if self.approach_center(CORNER_WINDOW) is None:
            return
        tx, ty = self.tile
        dx, dy = DIRV[nd]
        if passable(maze, tx + dx, ty + dy, allow_gate):
            self.dir = nd
            self.pending_turn = None


class Pacman(Actor):
    def __init__(self):
        super().__init__(13, 23, LEFT)
        self.mouth = 0.0
        self.alive = True

    def update(self, dt, game):
        self.commit_turn(game.maze)
        speed = game.params["pac_speed"]
        if self.tile[1] == TUNNEL_ROW and not passable(
            game.maze, self.tile[0] + DIRV[self.dir][0], self.tile[1]
        ):
            speed = min(speed, game.params["tunnel_speed"])
        step = speed * dt
        while step > 0:
            chunk = min(step, MAX_STEP)
            step -= chunk
            tol = max(1.2, chunk * 0.75)
            if self.at_center(tol):
                tx, ty = self.snap()
                if self.pending_turn and passable(
                    game.maze, tx + DIRV[self.pending_turn][0], ty + DIRV[self.pending_turn][1]
                ):
                    self.dir = self.pending_turn
                    self.pending_turn = None
                if not passable(game.maze, tx + DIRV[self.dir][0], ty + DIRV[self.dir][1]):
                    self.mouth = 0.0
                    return
                game.eat_at(tx, ty)
            self.advance(chunk)
            self.drift(dt)
        self.mouth = (self.mouth + dt * 12) % (math.pi * 2)


class GhostMode(Enum):
    HOUSE = auto()
    EXITING = auto()
    SCATTER = auto()
    CHASE = auto()
    FRIGHTENED = auto()
    EATEN = auto()


class Ghost(Actor):
    def __init__(self, name, color, home, scatter_tile, release_at):
        super().__init__(home[0], home[1], UP)
        self.name = name
        self.color = color
        self.scatter = scatter_tile
        self.release_at = release_at
        self.mode = GhostMode.HOUSE
        self.bob = 0.0
        self.dots_eaten = 0

    def reset(self):
        self.x, self.y = center_of(*self.spawn)
        self.dir = UP
        self.pending_turn = None
        self.mode = GhostMode.HOUSE
        self.bob = 0.0

    def update(self, dt, game):
        if self.mode is GhostMode.HOUSE:
            self.bob += dt * 4
            return
        if self.mode is GhostMode.EXITING:
            self._exit(dt, game)
            return

        self.commit_turn(game.maze, allow_gate=self.mode is GhostMode.EATEN)
        if self.mode is GhostMode.FRIGHTENED:
            speed = game.params["fright_speed"]
        elif self.mode is GhostMode.EATEN:
            speed = 150.0
        else:
            speed = game.params["ghost_speed"]
            if self.name == "blinky" and game.elroy:
                speed += 6.0 * game.elroy
        if self.tile[1] == TUNNEL_ROW:
            speed = min(speed, game.params["tunnel_speed"])
        speed = min(speed, TILE * FPS * 0.45)

        step = speed * dt
        while step > 0:
            chunk = min(step, MAX_STEP)
            step -= chunk
            tol = max(1.2, chunk * 0.75)
            if self.at_center(tol):
                tx, ty = self.snap()
                if self.mode is GhostMode.EATEN and (tx, ty) == (13, 14):
                    self.mode = GhostMode.EXITING
                    self.dir = UP
                    return
                if self.mode is GhostMode.EATEN and (tx, ty) == (13, 12):
                    self.mode = GhostMode.EXITING
                    self.dir = UP
                    return
                self._choose(game, tx, ty)
            self.advance(chunk)
            self.drift(dt)

    def _exit(self, dt, game):
        tx, ty = self.tile
        if ty <= 11:
            self.mode = game.mode_for_ghost()
            self.dir = random.choice((LEFT, RIGHT))
            return
        target_x, _ = center_of(13, ty)
        move = 60.0 * dt
        if abs(self.x - target_x) > 0.5:
            self.x += move if self.x < target_x else -move
            self.y = center_of(13, ty)[1]
            return
        self.x = target_x
        self.y -= 60.0 * dt

    def _choose(self, game, tx, ty):
        options = []
        for d in TURNS:
            if d == OPPOSITE[self.dir]:
                continue
            dx, dy = DIRV[d]
            if passable(game.maze, tx + dx, ty + dy, allow_gate=self.mode is GhostMode.EATEN):
                options.append(d)
        if not options:
            self.dir = OPPOSITE[self.dir]
            return
        if self.mode is GhostMode.FRIGHTENED:
            self.dir = random.choice(options)
            return
        gx, gy = game.target_for(self)
        self.dir = min(
            options,
            key=lambda d: abs(tx + DIRV[d][0] - gx) + abs(ty + DIRV[d][1] - gy),
        )


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
class Audio:
    def __init__(self):
        self.ok = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            if pygame.mixer.get_init()[2] != 1:
                pygame.mixer.quit()
                pygame.mixer.init(22050, -16, 1, 512)
            self.ok = True
        except pygame.error:
            return
        self.chomp = self._tone(520, 0.045, 0.25)
        self.power = self._tone(300, 0.22, 0.3, slide=760)
        self.death = self._tone(700, 0.6, 0.3, slide=90)
        self.eat_ghost = self._tone(880, 0.16, 0.3, slide=1400)
        self.fruit = self._tone(1000, 0.12, 0.25)

    def _tone(self, freq, dur, vol, slide=None):
        rate = 22050
        n = int(rate * dur)
        buf = array.array("h")
        phase = 0.0
        for i in range(n):
            f = freq if slide is None else freq + (slide - freq) * (i / n)
            phase += 2 * math.pi * f / rate
            env = 1.0 - i / n
            buf.append(int(math.sin(phase) * 32767 * vol * env))
        try:
            return pygame.mixer.Sound(buffer=buf.tobytes())
        except pygame.error:
            return None

    def play(self, name):
        if not self.ok:
            return
        snd = getattr(self, name, None)
        if snd is not None:
            snd.play()


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------
class State(Enum):
    MENU = auto()
    HELP = auto()
    ABOUT = auto()
    READY = auto()
    PLAY = auto()
    DYING = auto()
    LEVEL_CLEAR = auto()
    GAME_OVER = auto()
    PAUSED = auto()
    EXIT = auto()


class Game:
    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption(f"{TITLE} — {VERSION}")
        self.screen = pygame.display.set_mode((LOGICAL_W * SCALE, LOGICAL_H * SCALE))
        self.canvas = pygame.Surface((LOGICAL_W, LOGICAL_H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 12)
        self.big = pygame.font.Font(None, 24)
        self.audio = Audio()
        self.state = State.MENU
        self.menu_index = 0
        self.running = True
        self.high = 0
        self.score = 0
        self.lives = 3
        self.level = 1
        self.params = level_params(1)
        self.timer = 0.0
        self.phase_time = 0.0
        self.phase_index = 0
        self.maze = []
        self.dots_left = 0
        self.pac = None
        self.ghosts = []
        self.fruit = None
        self.fruit_timer = 0.0
        self.elroy = 0
        self.ghost_combo = 0
        self.msg = ""

    # -- lifecycle ---------------------------------------------------------
    def new_game(self):
        self.score = 0
        self.lives = 3
        self.level = 1
        self.start_level()

    def start_level(self):
        self.params = level_params(self.level)
        self.maze = [list(row) for row in MAZE]
        self.dots_left = sum(row.count(".") + row.count("o") for row in self.maze)
        self.pac = Pacman()
        self.ghosts = [
            Ghost("blinky", BLINKY, (13, 11), (25, -3), 0.0),
            Ghost("pinky", PINKY, (13, 14), (2, -3), 2.0),
            Ghost("inky", INKY, (11, 14), (27, 32), 5.0),
            Ghost("clyde", CLYDE, (16, 14), (0, 32), 9.0),
        ]
        self.ghosts[0].mode = GhostMode.CHASE
        self.fruit = None
        self.fruit_timer = 0.0
        self.elroy = 0
        self.phase_index = 0
        self.phase_time = 0.0
        self.timer = 2.0
        self.state = State.READY

    def advance_level(self):
        if self.level >= MAX_LEVEL:
            self.state = State.GAME_OVER
            return
        self.level += 1
        self.start_level()

    def lose_life(self):
        self.lives -= 1
        self.audio.play("death")
        self.state = State.DYING
        self.timer = 1.6

    # -- scoring -----------------------------------------------------------
    def eat_at(self, tx, ty):
        if ty < 0 or ty >= ROWS:
            return
        tx %= COLS
        c = self.maze[ty][tx]
        if c == ".":
            self.maze[ty][tx] = " "
            self.dots_left -= 1
            self.score += 10
            self.audio.play("chomp")
        elif c == "o":
            self.maze[ty][tx] = " "
            self.dots_left -= 1
            self.score += 50
            self.audio.play("power")
            for g in self.ghosts:
                if g.mode in (GhostMode.SCATTER, GhostMode.CHASE):
                    g.mode = GhostMode.FRIGHTENED
                    g.dir = OPPOSITE[g.dir]
            self.ghost_combo = 0
            self.phase_time = 0.0
        else:
            return
        if self.fruit and self.pac.rect.colliderect(self.fruit["rect"]):
            self.score += self.fruit["score"]
            self.audio.play("fruit")
            self.fruit = None
        if self.dots_left <= 0:
            self.state = State.LEVEL_CLEAR
            self.timer = 1.4
        if self.dots_left <= self.params["elroy1"]:
            self.elroy = 1
        if self.dots_left <= self.params["elroy2"]:
            self.elroy = 2

    def mode_for_ghost(self):
        if self.phase_index % 2 == 0:
            return GhostMode.SCATTER
        return GhostMode.CHASE

    def target_for(self, ghost):
        px, py = self.pac.tile
        if ghost.mode is GhostMode.EATEN:
            return 13, 14
        if ghost.mode is GhostMode.SCATTER:
            return ghost.scatter
        if ghost.name == "blinky":
            return px, py
        if ghost.name == "pinky":
            dx, dy = DIRV[self.pac.dir]
            return px + dx * 4, py + dy * 4
        if ghost.name == "inky":
            dx, dy = DIRV[self.pac.dir]
            ax, ay = px + dx * 2, py + dy * 2
            bx, by = self.ghosts[0].tile
            return ax + (ax - bx), ay + (ay - by)
        dist = abs(ghost.tile[0] - px) + abs(ghost.tile[1] - py)
        return (px, py) if dist > 8 else ghost.scatter

    # -- update ------------------------------------------------------------
    def update(self, dt):
        if self.state is State.READY:
            self.timer -= dt
            if self.timer <= 0:
                self.state = State.PLAY
            return
        if self.state is State.DYING:
            self.timer -= dt
            if self.timer <= 0:
                if self.lives <= 0:
                    self.state = State.GAME_OVER
                    self.high = max(self.high, self.score)
                else:
                    for g in self.ghosts:
                        g.reset()
                    self.ghosts[0].mode = GhostMode.CHASE
                    self.pac = Pacman()
                    self.timer = 1.2
                    self.state = State.READY
            return
        if self.state is State.LEVEL_CLEAR:
            self.timer -= dt
            if self.timer <= 0:
                self.advance_level()
            return
        if self.state is not State.PLAY:
            return

        # scatter/chase phase machine
        pattern = self.params["scatter_chase"]
        if self.phase_index < len(pattern) - 1:
            self.phase_time += dt
            if self.phase_time >= pattern[self.phase_index]:
                self.phase_time = 0.0
                self.phase_index += 1
                mode = self.mode_for_ghost()
                for g in self.ghosts:
                    if g.mode in (GhostMode.SCATTER, GhostMode.CHASE):
                        g.mode = mode
                        g.dir = OPPOSITE[g.dir]

        frightened = any(g.mode is GhostMode.FRIGHTENED for g in self.ghosts)
        if frightened:
            self.phase_time = 0.0

        # ghost release
        self.timer += dt
        for g in self.ghosts:
            if g.mode is GhostMode.HOUSE and self.timer >= g.release_at:
                g.mode = GhostMode.EXITING

        # frightened expiry
        for g in self.ghosts:
            if g.mode is GhostMode.FRIGHTENED:
                g.fright = getattr(g, "fright", self.params["fright_time"]) - dt
                if g.fright <= 0:
                    g.fright = self.params["fright_time"]
                    g.mode = self.mode_for_ghost()

        # fruit
        if self.fruit is None and self.dots_left and self.dots_left <= 70 and self.fruit_timer <= 0:
            self.spawn_fruit()
        if self.fruit:
            self.fruit["life"] -= dt
            if self.fruit["life"] <= 0:
                self.fruit = None
            elif self.pac.rect.colliderect(self.fruit["rect"]):
                self.score += self.fruit["score"]
                self.audio.play("fruit")
                self.fruit = None
                self.fruit_timer = 1.0
        elif self.fruit_timer > 0:
            self.fruit_timer -= dt

        self.pac.update(dt, self)
        for g in self.ghosts:
            g.update(dt, self)

        # collisions
        for g in self.ghosts:
            if g.mode in (GhostMode.SCATTER, GhostMode.CHASE, GhostMode.FRIGHTENED):
                if self.pac.rect.colliderect(g.rect):
                    if g.mode is GhostMode.FRIGHTENED:
                        g.mode = GhostMode.EATEN
                        self.ghost_combo += 1
                        self.score += 200 * (2 ** (self.ghost_combo - 1))
                        self.audio.play("eat_ghost")
                    else:
                        self.lose_life()
                        return

    def spawn_fruit(self):
        cx, cy = center_of(13, 17)
        self.fruit = {
            "rect": pygame.Rect(int(cx) - 4, int(cy) - 4, 8, 8),
            "score": self.params["fruit_score"],
            "life": 9.0,
            "color": FRUIT_COLOR[(self.level - 1) % len(FRUIT_COLOR)],
        }

    # -- drawing -----------------------------------------------------------
    def draw(self):
        self.canvas.fill(BLACK)
        if self.state is State.MENU:
            self.draw_menu()
        elif self.state is State.HELP:
            self.draw_text_screen("HELP", [
                "Arrows or WASD to move.",
                "Eat all dots to clear the maze.",
                "Big dots make ghosts edible.",
                "P pauses, ESC returns to menu.",
                "SPACE or ENTER selects.",
            ])
        elif self.state is State.ABOUT:
            self.draw_text_screen("ABOUT", [
                TITLE,
                SUBTITLE,
                f"build {VERSION}",
                COPYRIGHT,
                "Procedural art and audio.",
            ])
        elif self.state is State.EXIT:
            self.draw_text_screen("THANKS FOR PLAYING", ["Close the window."])
        elif self.state is State.GAME_OVER:
            self.draw_maze()
            self.draw_hud()
            self.draw_text_screen("GAME OVER", [f"Score {self.score}", "SPACE to retry"])
        else:
            self.draw_maze()
            self.draw_hud()
            if self.state is State.PLAY:
                self.draw_actors()
            elif self.state is State.READY:
                self.draw_actors()
                self.draw_center("READY!", YELLOW)
            elif self.state is State.DYING:
                self.draw_death()
            elif self.state is State.LEVEL_CLEAR:
                self.draw_center("BOARD CLEARED", YELLOW)
            elif self.state is State.PAUSED:
                self.draw_actors()
                self.draw_center("PAUSED", WHITE)

        pygame.transform.scale(self.canvas, self.screen.get_size(), self.screen)
        pygame.display.flip()

    def draw_maze(self):
        for ty, row in enumerate(self.maze):
            for tx, c in enumerate(row):
                x = tx * TILE
                y = (ty + HUD_TILES) * TILE
                if c == "#":
                    pygame.draw.rect(self.canvas, WALL_BLUE, (x, y, TILE, TILE), 1)
                elif c == "-":
                    pygame.draw.line(self.canvas, DOOR_PINK, (x, y + 4), (x + TILE, y + 4), 2)
                elif c == ".":
                    pygame.draw.rect(self.canvas, DOT, (x + 3, y + 3, 2, 2))
                elif c == "o":
                    pygame.draw.circle(self.canvas, DOT, (x + 4, y + 4), 3)
        if self.fruit:
            pygame.draw.circle(self.canvas, self.fruit["color"], self.fruit["rect"].center, 4)

    def draw_hud(self):
        self.canvas.blit(self.font.render(f"1UP {self.score:>6}", True, WHITE), (8, 4))
        self.canvas.blit(self.font.render(f"HIGH {self.high:>6}", True, WHITE), (96, 4))
        self.canvas.blit(self.font.render(f"LV {self.level}", True, YELLOW), (180, 4))
        for i in range(min(self.lives, 5)):
            pygame.draw.circle(self.canvas, PAC, (10 + i * 10, 20), 4)

    def draw_actors(self):
        p = self.pac
        r = 4
        a = 0.25 + abs(math.sin(p.mouth)) * 0.45
        pygame.draw.circle(self.canvas, PAC, (int(p.x), int(p.y)), r)
        if p.alive:
            facing = {RIGHT: 0, DOWN: math.pi / 2, LEFT: math.pi, UP: -math.pi / 2}[p.dir]
            pts = [(p.x, p.y)]
            for s in range(9):
                ang = facing - a + (2 * a) * s / 8
                pts.append((p.x + math.cos(ang) * r, p.y + math.sin(ang) * r))
            pygame.draw.polygon(self.canvas, BLACK, pts)

        for g in self.ghosts:
            y = g.y + (math.sin(g.bob) * 2 if g.mode is GhostMode.HOUSE else 0)
            if g.mode is GhostMode.FRIGHTENED:
                flash = getattr(g, "fright", 0) < self.params["flash"]
                col = WHITE if flash and int(pygame.time.get_ticks() / 150) % 2 else FRIGHT
                pygame.draw.circle(self.canvas, col, (int(g.x), int(y)), 4)
                pygame.draw.rect(self.canvas, col, (int(g.x) - 4, int(y), 8, 4))
                return_eyes = True
            elif g.mode is GhostMode.EATEN:
                pygame.draw.circle(self.canvas, WHITE, (int(g.x), int(y)), 4)
                return_eyes = True
            else:
                pygame.draw.circle(self.canvas, g.color, (int(g.x), int(y)), 4)
                pygame.draw.rect(self.canvas, g.color, (int(g.x) - 4, int(y), 8, 4))
                return_eyes = False
            ex = DIRV[g.dir][0]
            ey = DIRV[g.dir][1]
            for off in (-2, 2):
                pygame.draw.circle(self.canvas, WHITE if not return_eyes else WHITE,
                                   (int(g.x) + off, int(y) - 1), 2)
                pygame.draw.circle(self.canvas, BLACK if not return_eyes else BLACK,
                                   (int(g.x) + off + ex, int(y) - 1 + ey), 1)

    def draw_death(self):
        p = self.pac
        t = 1.0 - max(0.0, self.timer / 1.6)
        r = max(0, int(4 * (1.0 - t * 1.3)))
        if r:
            pygame.draw.circle(self.canvas, PAC, (int(p.x), int(p.y)), r)
        else:
            pygame.draw.circle(self.canvas, PAC, (int(p.x), int(p.y)), 4, 1)

    def draw_center(self, text, color):
        surf = self.big.render(text, True, color)
        self.canvas.blit(surf, surf.get_rect(center=(LOGICAL_W // 2, (17 + HUD_TILES) * TILE)))

    def draw_text_screen(self, title, lines):
        surf = self.big.render(title, True, YELLOW)
        self.canvas.blit(surf, surf.get_rect(center=(LOGICAL_W // 2, 50)))
        for i, line in enumerate(lines):
            s = self.font.render(line, True, WHITE)
            self.canvas.blit(s, s.get_rect(center=(LOGICAL_W // 2, 80 + i * 14)))

    def draw_menu(self):
        surf = self.big.render(TITLE, True, YELLOW)
        self.canvas.blit(surf, surf.get_rect(center=(LOGICAL_W // 2, 40)))
        s = self.font.render(SUBTITLE, True, WHITE)
        self.canvas.blit(s, s.get_rect(center=(LOGICAL_W // 2, 60)))
        items = ["PLAY GAME", "HELP", "ABOUT", "EXIT"]
        for i, item in enumerate(items):
            col = YELLOW if i == self.menu_index else WHITE
            s = self.font.render(item, True, col)
            self.canvas.blit(s, s.get_rect(center=(LOGICAL_W // 2, 100 + i * 16)))
        s = self.font.render(VERSION, True, GREEN)
        self.canvas.blit(s, s.get_rect(center=(LOGICAL_W // 2, LOGICAL_H - 16)))

    # -- input -------------------------------------------------------------
    def handle_key(self, key):
        if self.state is State.MENU:
            if key in (pygame.K_UP, pygame.K_w):
                self.menu_index = (self.menu_index - 1) % 4
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_index = (self.menu_index + 1) % 4
            elif key in (pygame.K_SPACE, pygame.K_RETURN):
                choice = ["play", "help", "about", "exit"][self.menu_index]
                if choice == "play":
                    self.new_game()
                elif choice == "help":
                    self.state = State.HELP
                elif choice == "about":
                    self.state = State.ABOUT
                else:
                    self.state = State.EXIT
            return

        if self.state in (State.HELP, State.ABOUT, State.EXIT):
            if key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_ESCAPE):
                self.state = State.MENU
            return

        if self.state is State.GAME_OVER:
            if key in (pygame.K_SPACE, pygame.K_RETURN):
                self.new_game()
            elif key == pygame.K_ESCAPE:
                self.state = State.MENU
            return

        if key == pygame.K_ESCAPE:
            self.state = State.MENU
            return
        if key == pygame.K_p:
            if self.state is State.PLAY:
                self.state = State.PAUSED
            elif self.state is State.PAUSED:
                self.state = State.PLAY
            return

        if self.state not in (State.PLAY, State.PAUSED):
            return
        mapping = {
            pygame.K_UP: UP, pygame.K_w: UP,
            pygame.K_DOWN: DOWN, pygame.K_s: DOWN,
            pygame.K_LEFT: LEFT, pygame.K_a: LEFT,
            pygame.K_RIGHT: RIGHT, pygame.K_d: RIGHT,
        }
        if key in mapping:
            self.pac.pending_turn = mapping[key]

    def run(self):
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event.key)
            self.update(dt)
            self.draw()
        pygame.quit()


def main():
    random.seed()
    game = Game()
    game.run()


if __name__ == "__main__":
    main()
