import pygame
import math
import random
import sys
import json
import os
from dataclasses import dataclass, asdict

# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
W, H          = 900, 600
PAD_W, PAD_H  = 14, 90
BALL_R        = 10
FPS           = 60

BALL_SPEED_INIT   = 6.0
BALL_SPEED_MAX    = 14.0
BALL_SPEED_INC    = 0.35   # speed bump per paddle hit
BREAKOUT_LEVEL_SPEED_INC = 0.25
AI_SPEED          = 4.8
WIN_SCORE         = 7
TRAIL_LEN         = 8

CLR_BG      = (10,   10,   26)   # #0a0a1a
CLR_NET     = (30,   42,   80)   # #1e2a50
CLR_P1      = (0,   212,  255)   # #00d4ff
CLR_P2      = (255,  77,  109)   # #ff4d6d
CLR_BALL    = (255, 255,  255)   # #ffffff
CLR_TRAIL   = (136, 136,  255)   # #8888ff
CLR_TEXT    = (232, 234,  246)   # #e8eaf6
CLR_DIM     = (74,   85,  104)   # #4a5568
CLR_GOLD    = (255, 215,    0)   # #ffd700
CLR_GREEN   = (0,   230,  118)   # #00e676

# BREAKOUT MODE
BLOCK_W       = 60
BLOCK_H       = 20
BREAKOUT_PAD_W = 100
BREAKOUT_PAD_H = 16
BREAKOUT_LIVES = 3

STATS_FILE = "game_stats.json"


# ─────────────────────────────────────────────
#  PARTICLE SYSTEM & STATS
# ─────────────────────────────────────────────
@dataclass
class Particle:
    """Visual particle for effects."""
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    radius: float
    color: tuple

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.2  # gravity
        self.life -= 1

    def is_alive(self):
        return self.life > 0

    def get_alpha(self):
        """Return 0-1 alpha based on life remaining."""
        return max(0, self.life / self.max_life)


class StatsManager:
    """Manages high scores and game statistics."""
    
    def __init__(self, filename=STATS_FILE):
        self.filename = filename
        self.stats = {
            "1p_best": 0,
            "2p_best": 0,
            "breakout_best_level": 1,
            "total_games": 0,
            "p1_wins": 0,
            "p2_wins": 0,
        }
        self.load()

    def load(self):
        """Load stats from file."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    self.stats = json.load(f)
            except:
                pass

    def save(self):
        """Save stats to file."""
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.stats, f, indent=2)
        except:
            pass

    def update_win(self, mode, winner, score_p1, score_p2):
        """Update stats after a game ends."""
        self.stats["total_games"] += 1
        if winner == 1:
            self.stats["p1_wins"] += 1
        else:
            self.stats["p2_wins"] += 1

        # Update best scores
        if mode == "1p" and score_p1 > self.stats["1p_best"]:
            self.stats["1p_best"] = score_p1
        elif mode == "2p":
            best = max(score_p1, score_p2)
            if best > self.stats["2p_best"]:
                self.stats["2p_best"] = best

        self.save()

    def update_breakout_level(self, level):
        """Update best breakout level."""
        if level > self.stats["breakout_best_level"]:
            self.stats["breakout_best_level"] = level
            self.save()

    def get_best_1p(self):
        return self.stats.get("1p_best", 0)

    def get_best_2p(self):
        return self.stats.get("2p_best", 0)

    def get_best_breakout_level(self):
        return self.stats.get("breakout_best_level", 1)


# ─────────────────────────────────────────────
#  GAME CLASS
# ─────────────────────────────────────────────
class PingPongGame:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption("Ping Pong")
        self.clock = pygame.time.Clock()
        self.font_large = pygame.font.Font(None, 54)
        self.font_medium = pygame.font.Font(None, 80)
        self.font_small = pygame.font.Font(None, 18)
        self.font_tiny = pygame.font.Font(None, 15)
        self.font_title = pygame.font.Font(None, 46)

        # Stats manager
        self.stats = StatsManager()

        # Particles and effects
        self.particles = []
        self.screen_shake = 0
        self.shake_intensity = 0

        # game state
        self.mode          = None   # "1p" | "2p" | "breakout"
        self.state         = "menu" # menu | countdown | playing | paused | over
        self.score         = [0, 0]
        self.rally         = 0
        self.countdown_val = 3
        self.flash_timer   = 0
        self.flash_side    = None
        
        # breakout mode
        self.blocks        = []
        self.current_level = 1
        self.breakout_lives = BREAKOUT_LIVES
        self.blocks_destroyed = 0

        # paddles  [x-center, y-center]
        self.p1 = [30 + PAD_W // 2,     H // 2]
        self.p2 = [W - 30 - PAD_W // 2, H // 2]

        # ball
        self.bx = self.by = 0.0
        self.prev_bx = self.prev_by = 0.0
        self.vx = self.vy = 0.0

        # trail
        self.trail = []
        
        # breakout blocks
        self.block_data = {}

        # keys held
        self.keys = set()
        
        # timers
        self.countdown_timer = 0
        self.flash_frame_timer = 0

        self._show_menu()

    # ── particle & effects ──────────────────────────────────────────────

    def _spawn_particles(self, x, y, count=8, color=CLR_TRAIL, speed=3.0):
        """Spawn particles for collision effects."""
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            vx = speed * math.cos(angle) * random.uniform(0.5, 1.5)
            vy = speed * math.sin(angle) * random.uniform(0.5, 1.5)
            particle = Particle(
                x=x, y=y, vx=vx, vy=vy,
                life=15, max_life=15,
                radius=random.randint(2, 5),
                color=color
            )
            self.particles.append(particle)

    def _set_screen_shake(self, intensity=5, duration=6):
        """Trigger screen shake effect."""
        self.shake_intensity = intensity
        self.screen_shake = duration

    def _update_particles(self):
        """Update and remove dead particles."""
        for particle in self.particles[:]:
            particle.update()
            if not particle.is_alive():
                self.particles.remove(particle)

    def _update_screen_shake(self):
        """Update screen shake timer."""
        if self.screen_shake > 0:
            self.screen_shake -= 1

    def _get_shake_offset(self):
        """Get current screen shake offset."""
        if self.screen_shake <= 0:
            return 0, 0
        shake_x = random.randint(-self.shake_intensity, self.shake_intensity)
        shake_y = random.randint(-self.shake_intensity, self.shake_intensity)
        return shake_x, shake_y

    # ── screens ─────────────────────────────────────────────────────────

    def _show_menu(self):
        self.state = "menu"
        self.mode = None
        self.blocks = []
        self.block_data = {}
        self.trail = []

    def _start_game(self, mode):
        self.mode  = mode
        self.score = [0, 0]
        self.rally = 0
        self.blocks = []
        self.block_data = {}
        self._reset_ball(serve_to=1)
        self._start_countdown()

    def _start_countdown(self):
        self.state         = "countdown"
        self.countdown_val = 3
        self.countdown_timer = 0

    def _begin_play(self):
        self.state = "playing"

    def _show_pause(self):
        self.state = "paused"

    def _show_game_over(self, winner):
        self.state  = "over"
        self.winner = winner

    # ── reset / serve ────────────────────────────────────────────────────

    def _reset_ball(self, serve_to=1):
        if self.mode == "breakout":
            # Start at paddle position in breakout mode
            self.bx = self.p1[0]
            self.by = H - 50  # Slightly above the paddle
            ang = random.uniform(-25, 25)
            spd = min(BALL_SPEED_MAX, BALL_SPEED_INIT * 0.8 +
                      (self.current_level - 1) * BREAKOUT_LEVEL_SPEED_INC)
            rad = math.radians(ang)
            self.vx = spd * math.sin(rad)
            self.vy = -spd * math.cos(rad)
        else:
            self.bx = W / 2
            self.by = H / 2
            ang = random.uniform(-35, 35)
            spd = BALL_SPEED_INIT
            if serve_to == 2:
                ang = 180 + random.uniform(-35, 35)
            rad = math.radians(ang)
            self.vx = spd * math.cos(rad)
            self.vy = spd * math.sin(rad)
        self.prev_bx = self.bx
        self.prev_by = self.by
        self.trail = []
        self.rally = 0

    def _reset_paddles(self):
        self.p1[1] = H // 2
        self.p2[1] = H // 2

    # ── breakout mode levels ────────────────────────────────────────────

    def _get_level_layout(self, level):
        """Return a 2D grid of blocks for each level (top to bottom, left to right)."""
        patterns = {
            1: [[1] * 8],
            2: [[2] * 8, [1] * 8],
            3: [[3] * 8, [2] * 8, [1] * 8],
            4: [[1, 2] * 5, [2, 1] * 5, [1, 2] * 5],
            5: [[4] * 10, [3] * 10, [2] * 10],
            6: [[1] * 10, [2] * 10, [3] * 10, [4] * 10],
            7: [
                [1, 2, 3, 4, 1, 2, 3, 4, 1, 2],
                [2, 3, 4, 1, 2, 3, 4, 1, 2, 3],
                [3, 4, 1, 2, 3, 4, 1, 2, 3, 4],
                [4, 1, 2, 3, 4, 1, 2, 3, 4, 1],
            ],
            8: [[1] * 10, [2] * 10, [3] * 10, [4] * 10, [1] * 10],
            9: [
                [1, 2] * 5,
                [2, 3] * 5,
                [3, 4] * 5,
                [4, 1] * 5,
                [1, 2] * 5,
            ],
            10: [[1] * 10, [2] * 10, [3] * 10, [4] * 10, [1] * 10, [2] * 10],
        }
        return patterns.get(level, patterns[1])

    def _load_level(self, level_num):
        """Create blocks for the given level."""
        self.blocks = []
        self.block_data = {}
        self.blocks_destroyed = 0
        layout = self._get_level_layout(level_num)
        
        colors = {
            1: (255, 107, 107),  # red
            2: (78, 205, 196),   # teal
            3: (255, 230, 109),  # yellow
            4: (149, 225, 211),  # mint
        }
        
        for row_idx, row in enumerate(layout):
            row_w = len(row) * BLOCK_W + (len(row) - 1) * 4
            start_x = (W - row_w) / 2
            for col_idx, block_type in enumerate(row):
                if block_type > 0:
                    x = start_x + col_idx * (BLOCK_W + 4)
                    y = 60 + row_idx * (BLOCK_H + 4)
                    block = {
                        "x": x,
                        "y": y,
                        "type": block_type,
                        "active": True
                    }
                    block_idx = len(self.blocks)
                    self.blocks.append(block)
                    self.block_data[block_idx] = colors.get(block_type, CLR_P1)

    def _start_breakout(self):
        """Initialize breakout mode."""
        self.mode = "breakout"
        self.current_level = 1
        self.breakout_lives = BREAKOUT_LIVES
        self.p1 = [W // 2, H // 2]  # Reset p1 position
        self._load_level(1)
        self._reset_ball(serve_to=1)
        self._start_countdown()

    def _next_level(self):
        """Progress to next level or show victory."""
        if self.current_level >= 10:
            self._show_breakout_victory()
        else:
            self.current_level += 1
            self.stats.update_breakout_level(self.current_level)
            self._load_level(self.current_level)
            self._reset_ball(serve_to=1)
            self._start_countdown()

    def _breakout_lost_life(self):
        """Player loses a life in breakout mode."""
        self.breakout_lives -= 1
        if self.breakout_lives <= 0:
            self._show_breakout_over()
        else:
            self._reset_ball(serve_to=1)
            self._start_countdown()

    def _show_breakout_over(self):
        """Show game over screen for breakout mode."""
        self.state = "over"
        self.winner = 0
        self.breakout_msg = "GAME OVER"
        self.stats.update_breakout_level(self.current_level)

    def _show_breakout_victory(self):
        """Show victory screen when all levels completed."""
        self.state = "over"
        self.winner = 1
        self.breakout_msg = "YOU WIN!"
        self.stats.update_breakout_level(10)

    # ── update (physics + AI) ────────────────────────────────────────────

    def update(self):
        """Main update loop."""
        # Update particles and screen shake every frame
        self._update_particles()
        self._update_screen_shake()
        
        if self.state == "countdown":
            self.countdown_timer += 1
            if self.countdown_timer >= 48:  # ~800ms at 60 FPS
                self.countdown_val -= 1
                self.countdown_timer = 0
                if self.countdown_val < 0:
                    self.countdown_timer = 0
                    self._begin_play()
        
        elif self.state == "playing":
            self._update_game()

    def _update_game(self):
        """Update game physics when playing."""
        # ── breakout mode paddle (left/right at bottom) ──
        if self.mode == "breakout":
            breakout_pad_min = BREAKOUT_PAD_W // 2 + 10
            breakout_pad_max = W - BREAKOUT_PAD_W // 2 - 10
            
            keys = pygame.key.get_pressed()
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:
                self.p1[0] = max(breakout_pad_min, self.p1[0] - 7)
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
                self.p1[0] = min(breakout_pad_max, self.p1[0] + 7)
        else:
            # ── Player controls RIGHT paddle (P2) with W / S ──
            keys = pygame.key.get_pressed()
            if keys[pygame.K_w]:
                self.p2[1] = max(PAD_H//2, self.p2[1] - 6)
            if keys[pygame.K_s]:
                self.p2[1] = min(H - PAD_H//2, self.p2[1] + 6)

            # ── Left paddle (P1) / AI / Player 2 ──
            if self.mode == "2p":
                if keys[pygame.K_UP]:
                    self.p1[1] = max(PAD_H//2, self.p1[1] - 6)
                if keys[pygame.K_DOWN]:
                    self.p1[1] = min(H - PAD_H//2, self.p1[1] + 6)
            else:
                self._ai_move()

        # ── ball movement ──
        self.prev_bx, self.prev_by = self.bx, self.by
        self.bx += self.vx
        self.by += self.vy

        # top / bottom bounce
        if self.by - BALL_R <= 2:
            self.by = 2 + BALL_R
            self.vy = abs(self.vy)
        if self.mode != "breakout":
            if self.by + BALL_R >= H - 2:
                self.by = H - 2 - BALL_R
                self.vy = -abs(self.vy)

        # Breakout side walls
        if self.mode == "breakout":
            if self.bx - BALL_R <= 2:
                self.bx = 2 + BALL_R
                self.vx = abs(self.vx)
            if self.bx + BALL_R >= W - 2:
                self.bx = W - 2 - BALL_R
                self.vx = -abs(self.vx)

        # ── paddle collision ──
        self._check_paddle_collision()

        # ── block collision (breakout mode) ──
        if self.mode == "breakout":
            self._check_block_collision()

        # ── scoring (ping pong only) ──
        if self.mode != "breakout":
            if self.bx - BALL_R < 0:
                self._point_scored(winner=2)
            elif self.bx + BALL_R > W:
                self._point_scored(winner=1)
        
        # Breakout: ball falls off bottom (only lose condition)
        if self.mode == "breakout" and self.by - BALL_R > H:
            self._breakout_lost_life()

        # ── trail ──
        self.trail.append((self.bx, self.by))
        if len(self.trail) > TRAIL_LEN:
            self.trail.pop(0)

        # ── flash ──
        if self.flash_timer > 0:
            self.flash_timer -= 1

    def _ai_move(self):
        """Simple but beatable AI with slight reaction delay."""
        target = self.by
        diff   = target - self.p1[1]
        move   = min(AI_SPEED, abs(diff))
        if abs(diff) > 4:
            self.p1[1] += math.copysign(move, diff)
        self.p1[1] = max(PAD_H//2, min(H - PAD_H//2, self.p1[1]))

    def _check_paddle_collision(self):
        if self.mode == "breakout":
            self._check_breakout_paddle_collision()
        else:
            self._check_side_paddle_collision(self.p1, side=1)
            self._check_side_paddle_collision(self.p2, side=2)

    def _circle_overlaps_rect(self, x1, y1, x2, y2):
        return (
            self.bx + BALL_R >= x1 and self.bx - BALL_R <= x2 and
            self.by + BALL_R >= y1 and self.by - BALL_R <= y2
        )

    def _register_paddle_hit(self, side):
        self.rally += 1
        self.flash_timer = 4
        self.flash_side = side
        # Particle effect
        color = CLR_P1 if side == 1 else CLR_P2
        self._spawn_particles(int(self.bx), int(self.by), count=6, color=color, speed=2.5)
        self._set_screen_shake(intensity=2, duration=3)

    def _bounce_off_side_paddle(self, paddle, side):
        self._register_paddle_hit(side)
        rel = max(-1.0, min(1.0, (self.by - paddle[1]) / (PAD_H / 2)))
        angle = rel * 60
        spd = min(BALL_SPEED_MAX, math.hypot(self.vx, self.vy) + BALL_SPEED_INC)
        rad = math.radians(angle)
        dirx = 1 if side == 1 else -1
        self.vx = dirx * spd * math.cos(rad)
        self.vy = spd * math.sin(rad)

    def _check_side_paddle_collision(self, paddle, side):
        px, py = paddle
        x1, y1 = px - PAD_W / 2, py - PAD_H / 2
        x2, y2 = px + PAD_W / 2, py + PAD_H / 2
        if not self._circle_overlaps_rect(x1, y1, x2, y2):
            return

        hit_from_side = (
            (side == 1 and self.prev_bx - BALL_R >= x2 and self.vx < 0) or
            (side == 2 and self.prev_bx + BALL_R <= x1 and self.vx > 0)
        )
        hit_from_top = self.prev_by + BALL_R <= y1 and self.vy > 0
        hit_from_bottom = self.prev_by - BALL_R >= y2 and self.vy < 0

        if hit_from_top:
            self.by = y1 - BALL_R
            self.vy = -abs(self.vy)
            self._register_paddle_hit(side)
        elif hit_from_bottom:
            self.by = y2 + BALL_R
            self.vy = abs(self.vy)
            self._register_paddle_hit(side)
        elif hit_from_side:
            self.bx = x2 + BALL_R if side == 1 else x1 - BALL_R
            self._bounce_off_side_paddle(paddle, side)
        else:
            self.bx = x2 + BALL_R if side == 1 else x1 - BALL_R
            self._bounce_off_side_paddle(paddle, side)

    def _check_breakout_paddle_collision(self):
        px, py = self.p1[0], H - 30
        x1, y1 = px - BREAKOUT_PAD_W / 2, py - BREAKOUT_PAD_H / 2
        x2, y2 = px + BREAKOUT_PAD_W / 2, py + BREAKOUT_PAD_H / 2
        if self.vy <= 0 or not self._circle_overlaps_rect(x1, y1, x2, y2):
            return

        self.by = y1 - BALL_R
        self._register_paddle_hit(1)
        rel = max(-1.0, min(1.0, (self.bx - px) / (BREAKOUT_PAD_W / 2)))
        angle = rel * 65
        spd = min(BALL_SPEED_MAX, math.hypot(self.vx, self.vy) + BALL_SPEED_INC)
        rad = math.radians(angle)
        self.vx = spd * math.sin(rad)
        self.vy = -spd * math.cos(rad)

    def _check_block_collision(self):
        """Check collision between ball and blocks in breakout mode."""
        for block_idx, block in enumerate(self.blocks):
            if not block["active"]:
                continue
            
            bx1, by1 = block["x"], block["y"]
            bx2, by2 = bx1 + BLOCK_W, by1 + BLOCK_H
            
            if self._circle_overlaps_rect(bx1, by1, bx2, by2):
                
                # Destroy block
                block["active"] = False
                self.blocks_destroyed += 1
                self.rally += 1
                
                # Particle effect for block destruction
                block_color = self.block_data.get(block_idx, CLR_P1)
                self._spawn_particles((bx1 + bx2) / 2, (by1 + by2) / 2, 
                                     count=12, color=block_color, speed=2.0)
                self._set_screen_shake(intensity=3, duration=4)
                
                self._bounce_off_block(bx1, by1, bx2, by2)
                
                self.flash_timer = 4
                self.flash_side = 1
                
                # Check if level complete
                if self.blocks_destroyed == len(self.blocks):
                    self._next_level()
                
                break  # Only one collision per frame

    def _bounce_off_block(self, x1, y1, x2, y2):
        hit_left = self.prev_bx + BALL_R <= x1 and self.vx > 0
        hit_right = self.prev_bx - BALL_R >= x2 and self.vx < 0
        hit_top = self.prev_by + BALL_R <= y1 and self.vy > 0
        hit_bottom = self.prev_by - BALL_R >= y2 and self.vy < 0

        if hit_left:
            self.bx = x1 - BALL_R
            self.vx = -abs(self.vx)
        elif hit_right:
            self.bx = x2 + BALL_R
            self.vx = abs(self.vx)

        if hit_top:
            self.by = y1 - BALL_R
            self.vy = -abs(self.vy)
        elif hit_bottom:
            self.by = y2 + BALL_R
            self.vy = abs(self.vy)

        if not (hit_left or hit_right or hit_top or hit_bottom):
            x_overlap = min(self.bx + BALL_R - x1, x2 - (self.bx - BALL_R))
            y_overlap = min(self.by + BALL_R - y1, y2 - (self.by - BALL_R))
            if x_overlap < y_overlap:
                self.vx = -self.vx
            elif y_overlap < x_overlap:
                self.vy = -self.vy
            else:
                self.vx = -self.vx
                self.vy = -self.vy

    def _point_scored(self, winner):
        self.score[winner - 1] += 1
        self.trail = []
        
        # Celebration particles
        color = CLR_P1 if winner == 1 else CLR_P2
        self._spawn_particles(W//2, H//2, count=16, color=color, speed=4.0)
        self._set_screen_shake(intensity=4, duration=5)

        if self.score[winner - 1] >= WIN_SCORE:
            self.stats.update_win(self.mode, winner, self.score[0], self.score[1])
            self._show_game_over(winner)
        else:
            self._reset_paddles()
            self._reset_ball(serve_to=winner)
            self._start_countdown()

    # ── input ────────────────────────────────────────────────────────────

    def handle_events(self):
        """Handle keyboard input and window events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                self._handle_action_key(event.key)
        return True

    def _handle_action_key(self, key):
        """Handle action keys (menu navigation, pause, etc)."""
        # menu
        if self.state == "menu":
            if key == pygame.K_1:
                self._start_game("1p")
            elif key == pygame.K_2:
                self._start_game("2p")
            elif key == pygame.K_3:
                self._start_breakout()

        # playing
        elif self.state == "playing":
            if key == pygame.K_p or key == pygame.K_ESCAPE:
                self._show_pause()

        # paused
        elif self.state == "paused":
            if key == pygame.K_p or key == pygame.K_ESCAPE:
                self.state = "playing"
            elif key == pygame.K_m:
                self._reset_paddles()
                self._show_menu()

        # game over
        elif self.state == "over":
            if key == pygame.K_r:
                if self.mode == "breakout":
                    self._start_breakout()
                else:
                    self._start_game(self.mode)
            elif key == pygame.K_m:
                self._reset_paddles()
                self._show_menu()

    # ── render ───────────────────────────────────────────────────────────

    def render(self):
        """Render everything to the screen."""
        self.screen.fill(CLR_BG)
        
        # Get screen shake offset
        shake_x, shake_y = self._get_shake_offset()

        # Draw static elements
        self._draw_net()
        self._draw_borders()

        if self.state == "menu":
            self._draw_menu()
        elif self.state == "countdown":
            self._draw_countdown()
        elif self.state == "playing":
            self._draw_game()
        elif self.state == "paused":
            self._draw_pause()
        elif self.state == "over":
            self._draw_game_over()

        # Draw particles last (on top)
        self._draw_particles()
        
        # Apply screen shake by shifting viewport
        if shake_x != 0 or shake_y != 0:
            # Shift the display surface
            temp_surface = self.screen.copy()
            self.screen.fill(CLR_BG)
            self.screen.blit(temp_surface, (shake_x, shake_y))

        pygame.display.flip()

    def _draw_net(self):
        """Draw the dashed net in the middle."""
        for y in range(0, H, 20):
            pygame.draw.rect(self.screen, CLR_NET, (W//2 - 2, y, 4, 11))

    def _draw_borders(self):
        """Draw top and bottom border lines."""
        pygame.draw.line(self.screen, CLR_NET, (0, 2), (W, 2), 2)
        pygame.draw.line(self.screen, CLR_NET, (0, H-2), (W, H-2), 2)

    def _draw_menu(self):
        """Draw the main menu screen."""
        title = self.font_medium.render("PING  PONG", True, CLR_GOLD)
        sub1 = self.font_small.render("[ 1 ]  vs  Computer", True, CLR_TEXT)
        sub2 = self.font_small.render("[ 2 ]  vs  Friend  (same keyboard)", True, CLR_TEXT)
        sub3 = self.font_small.render("[ 3 ]  Breakout  (10 levels)", True, CLR_TEXT)

        title_rect = title.get_rect(center=(W//2, H//2 - 100))
        sub1_rect = sub1.get_rect(center=(W//2, H//2))
        sub2_rect = sub2.get_rect(center=(W//2, H//2 + 50))
        sub3_rect = sub3.get_rect(center=(W//2, H//2 + 100))

        self.screen.blit(title, title_rect)
        self.screen.blit(sub1, sub1_rect)
        self.screen.blit(sub2, sub2_rect)
        self.screen.blit(sub3, sub3_rect)
        
        # Display high scores at the bottom
        best_1p = self.stats.get_best_1p()
        best_2p = self.stats.get_best_2p()
        best_breakout = self.stats.get_best_breakout_level()
        
        hs1 = self.font_tiny.render(f"Best 1P Score: {best_1p}", True, CLR_DIM)
        hs2 = self.font_tiny.render(f"Best 2P Score: {best_2p}", True, CLR_DIM)
        hs3 = self.font_tiny.render(f"Best Breakout Level: {best_breakout}", True, CLR_DIM)
        
        self.screen.blit(hs1, hs1.get_rect(topleft=(10, H - 60)))
        self.screen.blit(hs2, hs2.get_rect(topleft=(10, H - 40)))
        self.screen.blit(hs3, hs3.get_rect(topleft=(10, H - 20)))

        self._draw_paddles()

    def _draw_countdown(self):
        """Draw countdown screen."""
        msg = self.font_medium.render(str(self.countdown_val), True, CLR_GOLD)
        sub = self.font_small.render("Get ready...", True, CLR_DIM)

        msg_rect = msg.get_rect(center=(W//2, H//2 - 100))
        sub_rect = sub.get_rect(center=(W//2, H//2))

        self.screen.blit(msg, msg_rect)
        self.screen.blit(sub, sub_rect)

        self._draw_paddles()

    def _draw_game(self):
        """Draw the active game state."""
        self._draw_trail()
        self._draw_ball()
        self._draw_paddles()
        self._draw_scores()
        self._draw_rally()
        if self.mode == "breakout":
            self._draw_breakout_info()
        else:
            self._draw_blocks_empty()

    def _draw_pause(self):
        """Draw pause overlay."""
        # Semi-transparent overlay
        overlay = pygame.Surface((W, H))
        overlay.set_alpha(128)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        title = self.font_large.render("PAUSED", True, CLR_TEXT)
        sub1 = self.font_small.render("[ P ]  Resume", True, CLR_TEXT)
        sub2 = self.font_small.render("[ M ]  Main Menu", True, CLR_DIM)

        title_rect = title.get_rect(center=(W//2, H//2 - 60))
        sub1_rect = sub1.get_rect(center=(W//2, H//2))
        sub2_rect = sub2.get_rect(center=(W//2, H//2 + 50))

        self.screen.blit(title, title_rect)
        self.screen.blit(sub1, sub1_rect)
        self.screen.blit(sub2, sub2_rect)

    def _draw_game_over(self):
        """Draw game over screen."""
        # Semi-transparent overlay
        overlay = pygame.Surface((W, H))
        overlay.set_alpha(128)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        if self.mode == "breakout":
            if hasattr(self, 'breakout_msg'):
                title = self.font_title.render(self.breakout_msg, True, 
                                               CLR_GREEN if self.winner else CLR_P2)
                sub1 = self.font_small.render(f"Level: {self.current_level}", True, CLR_TEXT)
            else:
                title = self.font_title.render("GAME OVER", True, CLR_P2)
                sub1 = self.font_small.render(f"Level: {self.current_level}", True, CLR_TEXT)
        else:
            name  = "Player 1" if self.winner == 1 else ("Computer" if self.mode=="1p" else "Player 2")
            color = CLR_P1 if self.winner == 1 else CLR_P2
            title = self.font_title.render(f"{name} WINS!", True, color)
            sub1 = self.font_small.render(f"{self.score[0]}  -  {self.score[1]}", True, CLR_TEXT)

        sub2 = self.font_small.render("[ R ]  Play Again", True, CLR_TEXT)
        sub3 = self.font_small.render("[ M ]  Main Menu", True, CLR_DIM)

        title_rect = title.get_rect(center=(W//2, H//2 - 80))
        sub1_rect = sub1.get_rect(center=(W//2, H//2))
        sub2_rect = sub2.get_rect(center=(W//2, H//2 + 60))
        sub3_rect = sub3.get_rect(center=(W//2, H//2 + 100))

        self.screen.blit(title, title_rect)
        self.screen.blit(sub1, sub1_rect)
        self.screen.blit(sub2, sub2_rect)
        self.screen.blit(sub3, sub3_rect)
        
        # Display high score achievement if applicable
        if not self.mode == "breakout":
            if self.winner == 1 and self.score[0] == self.stats.get_best_1p() and self.score[0] > 0:
                hs_text = self.font_tiny.render("★ NEW 1P RECORD! ★", True, CLR_GOLD)
                self.screen.blit(hs_text, hs_text.get_rect(center=(W//2, 30)))
            elif self.winner == 1 and self.score[1] == self.stats.get_best_2p() and self.score[1] > 0:
                hs_text = self.font_tiny.render("★ NEW 2P RECORD! ★", True, CLR_GOLD)
                self.screen.blit(hs_text, hs_text.get_rect(center=(W//2, 30)))

    def _draw_trail(self):
        """Draw the ball trail effect."""
        for i, (tx, ty) in enumerate(self.trail):
            alpha = (i + 1) / TRAIL_LEN
            r = max(1, int(BALL_R * alpha * 0.75))
            
            # Calculate fade color
            g = int(100 * alpha)
            b = int(220 * alpha)
            col = (50, g, b)
            
            pygame.draw.circle(self.screen, col, (int(tx), int(ty)), r)

    def _draw_ball(self):
        """Draw the ball."""
        if self.state != "playing":
            return
        col = CLR_BALL
        if self.flash_timer > 0:
            col = CLR_P1 if self.flash_side == 1 else CLR_P2
        pygame.draw.circle(self.screen, col, (int(self.bx), int(self.by)), BALL_R)

    def _draw_paddles(self):
        """Draw both paddles."""
        def _pad_rect(cx, cy, w, h):
            return pygame.Rect(cx - w//2, cy - h//2, w, h)

        if self.mode == "breakout":
            rect = _pad_rect(self.p1[0], H - 30, BREAKOUT_PAD_W, BREAKOUT_PAD_H)
            pygame.draw.rect(self.screen, CLR_P1, rect)
        else:
            # Normal ping pong mode
            rect1 = _pad_rect(self.p1[0], self.p1[1], PAD_W, PAD_H)
            rect2 = _pad_rect(self.p2[0], self.p2[1], PAD_W, PAD_H)

            # glow highlight when flash
            p1col = CLR_GOLD if (self.flash_timer > 0 and self.flash_side == 1) else CLR_P1
            p2col = CLR_GOLD if (self.flash_timer > 0 and self.flash_side == 2) else CLR_P2
            
            pygame.draw.rect(self.screen, p1col, rect1)
            pygame.draw.rect(self.screen, p2col, rect2)

    def _draw_scores(self):
        """Draw the score display."""
        if self.mode != "breakout":
            score1 = self.font_large.render(str(self.score[0]), True, CLR_P1)
            score2 = self.font_large.render(str(self.score[1]), True, CLR_P2)

            score1_rect = score1.get_rect(center=(W//4, 50))
            score2_rect = score2.get_rect(center=(3*W//4, 50))

            self.screen.blit(score1, score1_rect)
            self.screen.blit(score2, score2_rect)

    def _draw_rally(self):
        """Draw the rally counter."""
        if self.state == "playing" and self.rally >= 3:
            txt = f"{self.rally}-hit rally" if self.rally < 10 else f"{self.rally} HITS!!"
            col = CLR_GOLD if self.rally >= 10 else CLR_DIM
            rally_text = self.font_tiny.render(txt, True, col)
            rally_rect = rally_text.get_rect(center=(W//2, 25))
            self.screen.blit(rally_text, rally_rect)

    def _draw_breakout_info(self):
        """Draw level and lives info for breakout mode."""
        level_text = self.font_small.render(f"Level: {self.current_level}/10", True, CLR_TEXT)
        lives_text = self.font_small.render(f"Lives: {self.breakout_lives}", True, CLR_TEXT)

        level_rect = level_text.get_rect(topleft=(10, 50))
        lives_rect = lives_text.get_rect(topright=(W - 10, 50))

        self.screen.blit(level_text, level_rect)
        self.screen.blit(lives_text, lives_rect)

        # Draw blocks
        for block_idx, block in enumerate(self.blocks):
            if block["active"]:
                color = self.block_data.get(block_idx, CLR_P1)
                rect = pygame.Rect(block["x"], block["y"], BLOCK_W, BLOCK_H)
                pygame.draw.rect(self.screen, color, rect)
                pygame.draw.rect(self.screen, CLR_TEXT, rect, 1)

    def _draw_particles(self):
        """Draw all active particles."""
        for particle in self.particles:
            alpha = particle.get_alpha()
            current_radius = max(1, int(particle.radius * alpha))
            # Blend color with alpha
            color = particle.color
            pygame.draw.circle(self.screen, color, (int(particle.x), int(particle.y)), current_radius)

    def _draw_blocks_empty(self):
        """Empty placeholder for non-breakout modes."""
        pass


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
def main():
    game = PingPongGame()
    running = True

    while running:
        running = game.handle_events()
        game.update()
        game.render()
        game.clock.tick(FPS)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
