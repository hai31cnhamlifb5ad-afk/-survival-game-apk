"""
像素生存游戏 - Pixel Survival (无限地图版)
黑/白/灰像素风格，在怪物浪潮中生存下去！
"""

import pygame
import random
import math
import sys
import struct
from typing import List, Tuple, Optional

# ============================================================
# 初始化
# ============================================================
pygame.init()
try:
    pygame.mixer.init()
except pygame.error:
    # Android 某些设备音频初始化失败，静默降级（无声但游戏可玩）
    pass

SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 576  # 16:9 横板，适配手机横屏
FPS = 60

# Android 上用 FULLSCREEN 标志（p4a 会忽略 set_caption）
_is_android = hasattr(sys, 'getandroidapilevel')
if _is_android:
    screen = pygame.display.set_mode(
        (SCREEN_WIDTH, SCREEN_HEIGHT),
        pygame.FULLSCREEN | pygame.SCALED
    )
else:
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Pixel Survival")
clock = pygame.time.Clock()

# 像素画布（低分辨率渲染再放大，获得像素风格）
PIXEL_SCALE = 3
CANVAS_W = SCREEN_WIDTH // PIXEL_SCALE
CANVAS_H = SCREEN_HEIGHT // PIXEL_SCALE
pixel_canvas = pygame.Surface((CANVAS_W, CANVAS_H))

# ============================================================
# 黑白灰色调
# ============================================================
BLACK       = (0, 0, 0)
WHITE       = (255, 255, 255)
GRAY_10     = (25, 25, 25)
GRAY_15     = (38, 38, 38)
GRAY_06     = (15, 15, 15)
GRAY_08     = (20, 20, 20)
GRAY_12     = (31, 31, 31)
GRAY_18     = (46, 46, 46)
GRAY_20     = (51, 51, 51)
GRAY_22     = (56, 56, 56)
GRAY_25     = (64, 64, 64)
GRAY_30     = (76, 76, 76)
GRAY_40     = (102, 102, 102)
GRAY_42     = (107, 107, 107)
GRAY_45     = (115, 115, 115)
GRAY_50     = (128, 128, 128)
GRAY_55     = (140, 140, 140)
GRAY_60     = (153, 153, 153)
GRAY_70     = (179, 179, 179)
GRAY_80     = (204, 204, 204)
GRAY_85     = (217, 217, 217)
GRAY_90     = (229, 229, 229)
GRAY_93     = (237, 237, 237)
GRAY_95     = (242, 242, 242)
RED_BLOOD   = (180, 40, 40)

# ============================================================
# 通用像素绘制 — 先画整体轮廓再填色，强调剪影辨识度
# ============================================================
def _sprite(surf, x, y, body_pixels, body_color, hl_pixels=None, hl_color=None):
    """统一精灵绘制：黑轮廓→身体填色→白色高光点。
    body_pixels/hl_pixels 格式: [(dx,dy), ...] 每个坐标一个像素点"""
    # 1) 黑轮廓（所有身体像素+1px膨胀）
    for dx, dy in body_pixels:
        for nx, ny in [(dx-1,dy),(dx+1,dy),(dx,dy-1),(dx,dy+1),
                        (dx-1,dy-1),(dx+1,dy-1),(dx-1,dy+1),(dx+1,dy+1)]:
            if (nx, ny) not in body_pixels:
                surf.set_at((x+nx, y+ny), BLACK)
    # 2) 身体填色
    for dx, dy in body_pixels:
        surf.set_at((x+dx, y+dy), body_color)
    # 3) 高光/细节（白色单点，无轮廓）
    if hl_pixels:
        hc = hl_color if hl_color else WHITE
        for dx, dy in hl_pixels:
            surf.set_at((x+dx, y+dy), hc)

def _gun(surf, sx, sy, angle, length, width, color):
    """枪管：粗线带黑边"""
    ex, ey = sx+int(math.cos(angle)*length), sy+int(math.sin(angle)*length)
    for w in [width+2, width]:
        c = BLACK if w == width+2 else color
        pygame.draw.line(surf, c, (sx,sy), (ex,ey), max(1,w))


# ============================================================
# 字体（解决中文方框问题）
# ============================================================
import os

_BUNDLED_CJK_FONT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "assets", "fonts", "cjk.ttf"
)

def get_cjk_font(size: int) -> pygame.font.Font:
    """获取支持中文的字体，带降级策略。
    优先加载随 APK 打包的字体文件（assets/fonts/cjk.ttf），
    这样在 Android 上也能正常显示中文（手机系统里通常没有
    Microsoft YaHei / SimHei 这些桌面字体，SysFont 在 Android 上基本找不到）。
    找不到打包字体时，退回系统字体探测（仅用于桌面开发调试），
    最终降级为 pygame 默认字体（英文正常，中文可能是方块）。"""
    if os.path.exists(_BUNDLED_CJK_FONT_PATH):
        try:
            f = pygame.font.Font(_BUNDLED_CJK_FONT_PATH, size)
            test = f.render("测试", True, WHITE)
            if test.get_width() > 10:
                return f
        except Exception:
            pass

    # 桌面调试兜底：尝试常见系统字体
    candidates = [
        "Microsoft YaHei", "SimHei", "SimSun", "FangSong", "KaiTi",
        "Noto Sans CJK SC", "WenQuanYi Micro Hei", "AR PL UMing CN",
    ]
    for name in candidates:
        try:
            f = pygame.font.SysFont(name, size)
            test = f.render("测试", True, WHITE)
            if test.get_width() > 10:
                return f
        except Exception:
            continue
    # 最终降级：用默认字体（可能还是方框，但不会崩溃）
    return pygame.font.Font(None, size)

FONT_SMALL   = get_cjk_font(16)
FONT_MEDIUM  = get_cjk_font(24)
FONT_LARGE   = get_cjk_font(36)
FONT_TITLE   = get_cjk_font(56)

# ============================================================
# 程序化音效
# ============================================================
class _NullSound:
    """无声的 Sound 占位符（Android mixer 初始化失败时用）"""
    def play(self, *args, **kwargs): pass
    def stop(self): pass
    def set_volume(self, *args, **kwargs): pass

def _make_sound(generator):
    """生成音效的内部辅助；mixer 不可用时返回无声占位"""
    if not pygame.mixer.get_init():
        return _NullSound()
    try:
        import struct as _st
        sample_rate = 22050
        duration, gen = generator()
        n_samples = int(sample_rate * duration)
        buf = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            sample = int(gen(t) * 0.3 * max(0, 1 - t / duration))
            buf.extend(_st.pack('b', max(-127, min(127, sample))))
        return pygame.mixer.Sound(bytes(buf))
    except Exception:
        return _NullSound()

def _gen_shoot():
    return 0.06, lambda t: (127 if (int(t * (800 - t * 4000 + 50))) % 2 == 0 else -127) if (800 - t * 4000) >= 50 else (127 if (int(t * 50)) % 2 == 0 else -127)

def _gen_hit():
    return 0.1, lambda t: (80 if (int(t * (200 + random.randint(-50, 50)))) % 2 == 0 else -80)

def _gen_pickup():
    return 0.15, lambda t: (100 if (int(t * (400 + t * 1200))) % 2 == 0 else -100)

def _gen_death():
    return 0.2, lambda t: random.randint(-100, 100) if (300 - t * 1000) >= 60 else random.randint(-100, 100)

snd_shoot   = _make_sound(_gen_shoot)
snd_hit     = _make_sound(_gen_hit)
snd_pickup  = _make_sound(_gen_pickup)
snd_death   = _make_sound(_gen_death)


# ============================================================
# 触屏输入系统（虚拟摇杆）
# 在 PC 上按 F11 切换到"手机模拟模式"，用鼠标模拟拇指
# ============================================================
class VirtualJoystick:
    """虚拟摇杆 — 拖拽产生方向向量，抬起回中"""

    def __init__(self, base_x: int, base_y: int, base_radius: int = 60, knob_radius: int = 25):
        # base_x/base_y 是屏幕坐标（px），在 set_mode 后一次性布局
        self.base_x = base_x
        self.base_y = base_y
        self.base_radius = base_radius      # 底座半径（可拖范围）
        self.knob_radius = knob_radius      # 摇杆头半径
        self.knob_x = base_x                # 摇杆头当前位置
        self.knob_y = base_y
        self.active = False                 # 是否被按住
        self.touch_id = None                # pygame FINGERDOWN 的 finger_id（多指区分）
        self.value_x = 0.0                  # 归一化方向 [-1, 1]
        self.value_y = 0.0

    def begin(self, x: int, y: int, touch_id=0) -> bool:
        """检查按下是否在摇杆范围内，是则激活"""
        dist = math.hypot(x - self.base_x, y - self.base_y)
        # 判定范围：底座半径的 1.5 倍（手指不用精确按在底座上）
        if dist <= self.base_radius * 1.5:
            self.active = True
            self.touch_id = touch_id
            self._update_knob(x, y)
            return True
        return False

    def move(self, x: int, y: int, touch_id=0):
        if self.active and self.touch_id == touch_id:
            self._update_knob(x, y)

    def end(self, touch_id=0):
        if self.touch_id == touch_id:
            self.active = False
            self.touch_id = None
            self.knob_x = self.base_x
            self.knob_y = self.base_y
            self.value_x = 0.0
            self.value_y = 0.0

    def _update_knob(self, x: int, y: int):
        dx = x - self.base_x
        dy = y - self.base_y
        dist = math.hypot(dx, dy)
        if dist > self.base_radius:
            # 限制在底座边缘
            scale = self.base_radius / dist
            dx *= scale
            dy *= scale
        self.knob_x = self.base_x + dx
        self.knob_y = self.base_y + dy
        # 归一化（-1 到 1）
        self.value_x = dx / self.base_radius
        self.value_y = dy / self.base_radius

    def is_engaged(self, dead_zone: float = 0.15) -> bool:
        """是否被推动（离开死区）"""
        return self.active and math.hypot(self.value_x, self.value_y) > dead_zone

    def draw(self, surf: pygame.Surface):
        """在 screen 上绘制（不是 pixel_canvas — UI 用屏幕分辨率更清晰）"""
        # 底座：半透明圆环
        overlay = pygame.Surface((self.base_radius * 2 + 4, self.base_radius * 2 + 4), pygame.SRCALPHA)
        cx = self.base_radius + 2
        cy = self.base_radius + 2
        # 外环
        pygame.draw.circle(overlay, (*GRAY_60, 90), (cx, cy), self.base_radius, 2)
        # 内部淡填充
        pygame.draw.circle(overlay, (*GRAY_30, 40), (cx, cy), self.base_radius - 2)
        surf.blit(overlay, (self.base_x - cx, self.base_y - cy))

        # 摇杆头：实心圆
        knob_overlay = pygame.Surface((self.knob_radius * 2 + 4, self.knob_radius * 2 + 4), pygame.SRCALPHA)
        kx = self.knob_radius + 2
        ky = self.knob_radius + 2
        color = (*WHITE, 200) if self.active else (*GRAY_80, 140)
        pygame.draw.circle(knob_overlay, color, (kx, ky), self.knob_radius)
        pygame.draw.circle(knob_overlay, (*BLACK, 180), (kx, ky), self.knob_radius, 2)
        surf.blit(knob_overlay, (int(self.knob_x) - kx, int(self.knob_y) - ky))


class TouchInputManager:
    """触屏输入管理器 — 管理双摇杆 + 触屏按钮
    提供与键盘鼠标等价的接口：
      - move_vector() -> (dx, dy)
      - aim_vector()  -> (dx, dy) 或 None
      - is_shooting() -> bool
    """
    # 暂停按钮在屏幕上的位置（右上角）
    PAUSE_BTN_SIZE = 50
    PAUSE_BTN_MARGIN = 15

    def __init__(self):
        # 布局在 set_layout() 中根据屏幕尺寸计算
        self.move_stick: VirtualJoystick = None
        self.aim_stick: VirtualJoystick = None
        self.set_layout(SCREEN_WIDTH, SCREEN_HEIGHT)
        # 用于检测"瞬时点击"（武器切换、暂停、重开）
        self.pending_tap: Optional[Tuple[int, int]] = None
        self.pause_tapped = False

    def set_layout(self, screen_w: int, screen_h: int):
        """根据屏幕尺寸布局摇杆位置"""
        margin = 40
        base_r = max(50, screen_h // 9)  # 摇杆底座约为屏高 1/9
        knob_r = base_r // 2
        # 左下：移动摇杆
        self.move_stick = VirtualJoystick(
            margin + base_r, screen_h - margin - base_r, base_r, knob_r)
        # 右下：瞄准摇杆
        self.aim_stick = VirtualJoystick(
            screen_w - margin - base_r, screen_h - margin - base_r, base_r, knob_r)

    # ── 事件处理 ──
    def handle_mouse_down(self, x: int, y: int):
        """PC 模拟模式：左半屏 = 移动摇杆，右半屏 = 瞄准摇杆"""
        # 先检查暂停按钮
        if self._in_pause_btn(x, y):
            self.pause_tapped = True
            return
        # 左半屏 → 移动摇杆
        if x < SCREEN_WIDTH // 2:
            self.move_stick.begin(x, y, touch_id=0)
        else:
            self.aim_stick.begin(x, y, touch_id=0)

    def handle_mouse_move(self, x: int, y: int):
        self.move_stick.move(x, y, touch_id=0)
        self.aim_stick.move(x, y, touch_id=0)

    def handle_mouse_up(self, x: int, y: int):
        # 抬起时：如果是"短按"（几乎没拖动），记为一次点击（用于物品栏/gameover）
        if not self.move_stick.is_engaged() and not self.aim_stick.is_engaged():
            self.pending_tap = (x, y)
        self.move_stick.end(touch_id=0)
        self.aim_stick.end(touch_id=0)

    def handle_finger_down(self, x: int, y: int, finger_id: int):
        """真实触屏：根据按下的位置分配给左/右摇杆"""
        if self._in_pause_btn(x, y):
            self.pause_tapped = True
            return
        if x < SCREEN_WIDTH // 2:
            self.move_stick.begin(x, y, touch_id=finger_id)
        else:
            self.aim_stick.begin(x, y, touch_id=finger_id)

    def handle_finger_move(self, x: int, y: int, finger_id: int):
        self.move_stick.move(x, y, touch_id=finger_id)
        self.aim_stick.move(x, y, touch_id=finger_id)

    def handle_finger_up(self, x: int, y: int, finger_id: int):
        if not self.move_stick.is_engaged() and not self.aim_stick.is_engaged():
            self.pending_tap = (x, y)
        self.move_stick.end(touch_id=finger_id)
        self.aim_stick.end(touch_id=finger_id)

    # ── 查询接口（供 main 循环调用）──
    def move_vector(self) -> Tuple[float, float]:
        """移动方向（归一化），无输入时返回 (0,0)"""
        if self.move_stick.is_engaged():
            return self.move_stick.value_x, self.move_stick.value_y
        return 0.0, 0.0

    def aim_vector(self) -> Optional[Tuple[float, float]]:
        """瞄准方向（单位向量），无输入时返回 None"""
        if self.aim_stick.is_engaged():
            vx, vy = self.aim_stick.value_x, self.aim_stick.value_y
            mag = math.hypot(vx, vy)
            if mag > 0.01:
                return vx / mag, vy / mag
        return None

    def is_shooting(self) -> bool:
        """是否在射击（瞄准摇杆被推动即射击）"""
        return self.aim_stick.is_engaged()

    def consume_tap(self) -> Optional[Tuple[int, int]]:
        """取出待处理的点击（一次性）"""
        tap = self.pending_tap
        self.pending_tap = None
        return tap

    def consume_pause_tap(self) -> bool:
        """取出暂停按钮点击（一次性）"""
        t = self.pause_tapped
        self.pause_tapped = False
        return t

    def _in_pause_btn(self, x: int, y: int) -> bool:
        btn_x = SCREEN_WIDTH - self.PAUSE_BTN_SIZE - self.PAUSE_BTN_MARGIN
        btn_y = self.PAUSE_BTN_MARGIN
        return btn_x <= x <= btn_x + self.PAUSE_BTN_SIZE and btn_y <= y <= btn_y + self.PAUSE_BTN_SIZE

    # ── 绘制 ──
    def draw(self, surf: pygame.Surface):
        self.move_stick.draw(surf)
        self.aim_stick.draw(surf)
        self._draw_pause_btn(surf)

    def _draw_pause_btn(self, surf: pygame.Surface):
        size = self.PAUSE_BTN_SIZE
        x = SCREEN_WIDTH - size - self.PAUSE_BTN_MARGIN
        y = self.PAUSE_BTN_MARGIN
        # 半透明背景
        overlay = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.rect(overlay, (*GRAY_30, 100), (0, 0, size, size), border_radius=8)
        pygame.draw.rect(overlay, (*WHITE, 160), (0, 0, size, size), 2, border_radius=8)
        surf.blit(overlay, (x, y))
        # 暂停图标（两条竖线）
        bar_w = size // 6
        bar_h = size // 2
        gap = size // 8
        left_x = x + size // 2 - gap - bar_w
        right_x = x + size // 2 + gap
        top_y = y + (size - bar_h) // 2
        pygame.draw.rect(surf, WHITE, (left_x, top_y, bar_w, bar_h))
        pygame.draw.rect(surf, WHITE, (right_x, top_y, bar_w, bar_h))


# ============================================================
# 相机系统
# ============================================================
class Camera:
    """跟随玩家的摄像机"""
    def __init__(self):
        self.x = 0.0  # 相机中心在世界坐标中的位置
        self.y = 0.0

    def follow(self, target_x: float, target_y: float, smooth: float = 0.15):
        """平滑跟随目标"""
        self.x += (target_x - self.x) * smooth
        self.y += (target_y - self.y) * smooth

    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        """世界坐标 → 画布坐标（返回整数像素）"""
        sx = int(wx - self.x + CANVAS_W // 2)
        sy = int(wy - self.y + CANVAS_H // 2)
        return sx, sy

    def is_visible(self, wx: float, wy: float, margin: int = 30) -> bool:
        """检查世界坐标是否在屏幕可见范围内"""
        sx, sy = self.world_to_screen(wx, wy)
        return -margin < sx < CANVAS_W + margin and -margin < sy < CANVAS_H + margin


# ============================================================
# 无限地图 — 程序化背景
# ============================================================
class GameMap:
    CHUNK_SIZE = 48  # 每个块 48x48 像素

    def __init__(self):
        self.speckle_chunks = {}  # (cx, cy) → [(lx, ly, shade, size), ...]
        self.rock_chunks = {}     # (cx, cy) → [(lx, ly, size), ...]
        self.item_chunks = {}     # (cx, cy) → [(lx, ly, item_type), ...]

    def _chunk_key(self, wx: float, wy: float) -> Tuple[int, int]:
        return (int(wx // self.CHUNK_SIZE), int(wy // self.CHUNK_SIZE))

    def _get_speckles(self, cx: int, cy: int):
        key = (cx, cy)
        if key in self.speckle_chunks:
            return self.speckle_chunks[key]
        rng = random.Random(cx * 0x9E3779B9 + cy * 0x85EBCA77 + 12345)
        speckles = []
        count = rng.randint(10, 25)
        for _ in range(count):
            lx = rng.randint(0, self.CHUNK_SIZE - 1)
            ly = rng.randint(0, self.CHUNK_SIZE - 1)
            shade = rng.choices(
                [GRAY_80, GRAY_85, GRAY_90, GRAY_70, GRAY_93, GRAY_50, GRAY_60],
                weights=[30, 35, 15, 8, 5, 1, 1]
            )[0]
            sz = rng.choices([1, 2], weights=[90, 10])[0]
            speckles.append((lx, ly, shade, sz))
        self.speckle_chunks[key] = speckles
        # 限制缓存大小
        if len(self.speckle_chunks) > 400:
            self.speckle_chunks.pop(next(iter(self.speckle_chunks)))
        return speckles

    def _get_rocks(self, cx: int, cy: int):
        key = (cx, cy)
        if key in self.rock_chunks:
            return self.rock_chunks[key]
        rng = random.Random(cx * 0xA1B2C3D4 + cy * 0xE5F60718 + 54321)
        rocks = []
        # 并非每个块都有石头
        if rng.random() < 0.3:
            count = rng.randint(1, 2)
            for _ in range(count):
                lx = rng.randint(4, self.CHUNK_SIZE - 4)
                ly = rng.randint(4, self.CHUNK_SIZE - 4)
                sz = rng.randint(4, 8)
                rocks.append((lx, ly, sz))
        self.rock_chunks[key] = rocks
        if len(self.rock_chunks) > 400:
            self.rock_chunks.pop(next(iter(self.rock_chunks)))
        return rocks

    def _get_items(self, cx: int, cy: int):
        """每个区块可能包含一个盲盒物品（约15%概率）"""
        key = (cx, cy)
        if key in self.item_chunks:
            return self.item_chunks[key]
        rng = random.Random(cx * 0xDEADBEEF + cy * 0xCAFEBABE + 99999)
        items = []
        if rng.random() < 0.15:
            lx = rng.randint(6, self.CHUNK_SIZE - 6)
            ly = rng.randint(6, self.CHUNK_SIZE - 6)
            it = Item.random_mystery()
            items.append((lx, ly, it))
        self.item_chunks[key] = items
        if len(self.item_chunks) > 400:
            self.item_chunks.pop(next(iter(self.item_chunks)))
        return items

    def draw(self, surf: pygame.Surface, camera: Camera):
        """只绘制相机可见范围内的地面"""
        # 浅色纯色底色
        surf.fill(GRAY_93)

        # 计算可见的块范围
        left   = int((camera.x - CANVAS_W // 2) // self.CHUNK_SIZE) - 1
        right  = int((camera.x + CANVAS_W // 2) // self.CHUNK_SIZE) + 1
        top    = int((camera.y - CANVAS_H // 2) // self.CHUNK_SIZE) - 1
        bottom = int((camera.y + CANVAS_H // 2) // self.CHUNK_SIZE) + 1

        for cy in range(top, bottom + 1):
            for cx in range(left, right + 1):
                base_wx = cx * self.CHUNK_SIZE
                base_wy = cy * self.CHUNK_SIZE

                # 画斑点
                for lx, ly, shade, sz in self._get_speckles(cx, cy):
                    wx = base_wx + lx
                    wy = base_wy + ly
                    sx, sy = camera.world_to_screen(wx, wy)
                    if 0 <= sx < CANVAS_W and 0 <= sy < CANVAS_H:
                        if sz == 1:
                            surf.set_at((sx, sy), shade)
                        else:
                            pygame.draw.rect(surf, shade, (sx, sy, sz, sz))

                # 画石头
                for lx, ly, rock_sz in self._get_rocks(cx, cy):
                    wx = base_wx + lx
                    wy = base_wy + ly
                    sx, sy = camera.world_to_screen(wx, wy)
                    # 简化绘制：只绘制屏幕上的部分
                    for dx in range(-rock_sz, rock_sz + 1):
                        for dy in range(-rock_sz, rock_sz + 1):
                            if dx * dx + dy * dy <= rock_sz * rock_sz:
                                draw_sx = sx + dx
                                draw_sy = sy + dy
                                if 0 <= draw_sx < CANVAS_W and 0 <= draw_sy < CANVAS_H:
                                    c = GRAY_85 if (dx + dy) % 2 == 0 else GRAY_80
                                    surf.set_at((draw_sx, draw_sy), c)


# ============================================================
# 粒子系统（烟花式外爆，无重力）
# ============================================================
class Particle:
    __slots__ = ('x','y','vx','vy','life','max_life','color','size','shape')
    def __init__(self, x, y, vx, vy, life, color, size=1, shape=0):
        self.x=x; self.y=y; self.vx=vx; self.vy=vy
        self.life=life; self.max_life=life
        self.color=color; self.size=size
        self.shape=shape  # 0=方块 1=菱形 2=星点

class ParticleSystem:
    def __init__(self):
        self.particles: List[Particle] = []

    def emit(self, x, y, count, color, speed=2.0, life=0.5):
        for _ in range(count):
            a = random.uniform(0, 2*math.pi)
            spd = random.uniform(speed*0.4, speed)
            self.particles.append(Particle(
                x, y, math.cos(a)*spd, math.sin(a)*spd,
                life, color, random.randint(1,3), random.randint(0,2)))

    def emit_directional(self, x, y, angle, count, color,
                         spread=0.5, speed=2.0, life=0.5):
        for _ in range(count):
            a = angle + random.uniform(-spread, spread)
            spd = random.uniform(speed*0.3, speed)
            self.particles.append(Particle(
                x, y, math.cos(a)*spd, math.sin(a)*spd,
                life, color, random.randint(1,3), random.randint(0,2)))

    def emit_burst(self, x, y, count, color, speed=4.0, life=0.6):
        """烟花式均匀外爆——所有粒子从中心向四面八方均匀射出"""
        for i in range(count):
            a = (2*math.pi) * i / count + random.uniform(-0.15, 0.15)
            spd = random.uniform(speed*0.5, speed)
            self.particles.append(Particle(
                x, y, math.cos(a)*spd, math.sin(a)*spd,
                life, color, random.randint(1,4), random.randint(0,2)))

    def emit_burst_rings(self, x, y, count, color, rings=2, speed=4.0, life=0.6):
        """多层环状烟花——内环+外环两个速度层"""
        for ring in range(rings):
            n = count // rings
            base_spd = speed * (0.5 + ring * 0.5)
            for i in range(n):
                a = (2*math.pi) * i / n + random.uniform(-0.1, 0.1)
                spd = random.uniform(base_spd*0.6, base_spd)
                self.particles.append(Particle(
                    x, y, math.cos(a)*spd, math.sin(a)*spd,
                    life, color, random.randint(2,4), random.randint(0,2)))

    def update(self, dt: float):
        for p in self.particles[:]:
            p.x += p.vx
            p.y += p.vy
            p.life -= dt
            if p.life <= 0:
                self.particles.remove(p)

    def draw(self, surf: pygame.Surface, camera: Camera):
        for p in self.particles:
            sx, sy = camera.world_to_screen(p.x, p.y)
            a = max(0, p.life/p.max_life)
            c = WHITE if random.random()<0.04 else p.color
            gray = max(0, min(255, int(c[0]*a)))
            color = (gray, gray, gray)
            sz = max(1, int(p.size * a))

            if p.shape == 0:
                pygame.draw.rect(surf, color, (sx-sz//2, sy-sz//2, sz, sz))
            elif p.shape == 1:
                # 菱形
                pygame.draw.rect(surf, color, (sx, sy-sz//2, 1, sz))
                pygame.draw.rect(surf, color, (sx-sz//2, sy, sz, 1))
            else:
                # 双像素星点
                pygame.draw.rect(surf, color, (sx, sy, 2, 2))


# ============================================================
# 武器系统
# ============================================================
class WeaponType:
    PISTOL  = 0
    SHOTGUN = 1
    RIFLE   = 2
    ROCKET  = 3
    DYNAMITE = 4

WEAPON_STATS = [
    {"name": "手枪",   "ename": "Pistol",   "damage": 12, "fire_rate": 0.35, "bullet_speed": 8,  "spread": 0.05, "count": 1,  "color": WHITE,    "max_ammo": 999, "size": 2, "explosive": False},
    {"name": "霰弹枪", "ename": "Shotgun",  "damage": 10, "fire_rate": 0.70, "bullet_speed": 6,  "spread": 0.30, "count": 6,  "color": GRAY_70,   "max_ammo": 30,  "size": 1, "explosive": False},
    {"name": "步枪",   "ename": "Rifle",    "damage": 18, "fire_rate": 0.12, "bullet_speed": 12, "spread": 0.08, "count": 1,  "color": GRAY_90,   "max_ammo": 60,  "size": 1, "explosive": False},
    {"name": "火箭筒", "ename": "Rocket",   "damage": 100,"fire_rate": 0.80, "bullet_speed": 3.5,"spread": 0.0,  "count": 1,  "color": RED_BLOOD,"max_ammo": 99,  "size": 3, "explosive": True,  "explosion_radius": 38},
    {"name": "炸药",   "ename": "Dynamite","damage": 200,"fire_rate": 0.50, "bullet_speed": 0,  "spread": 0.0,  "count": 1,  "color": RED_BLOOD,"max_ammo": 99,  "size": 0, "explosive": True,  "explosion_radius": 55},
]


# ============================================================
# 子弹
# ============================================================
class Bullet:
    def __init__(self, x, y, angle, weapon: int):
        s = WEAPON_STATS[weapon]
        self.x = x; self.y = y
        self.vx = math.cos(angle) * s["bullet_speed"]
        self.vy = math.sin(angle) * s["bullet_speed"]
        self.damage = s["damage"]
        self.color = s["color"]
        self.size = s["size"]
        self.life = 3.0
        self.alive = True

    def update(self, dt):
        self.x += self.vx
        self.y += self.vy
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf, camera: Camera):
        if not self.alive: return
        sx, sy = camera.world_to_screen(self.x, self.y)
        if not (-10 < sx < CANVAS_W + 10 and -10 < sy < CANVAS_H + 10): return
        tx, ty = camera.world_to_screen(self.x - self.vx * 0.3, self.y - self.vy * 0.3)
        pygame.draw.line(surf, GRAY_40, (tx, ty), (sx, sy), max(1, self.size))
        pygame.draw.rect(surf, self.color,
                         (sx - self.size//2, sy - self.size//2, self.size, self.size))


# ============================================================
# 坦克子弹（敌人射击）
# ============================================================
class TankBullet:
    def __init__(self, x, y, angle):
        self.x = x; self.y = y
        speed = 3.5
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.damage = 8
        self.size = 3
        self.color = GRAY_60
        self.life = 4.0
        self.alive = True

    def update(self, dt):
        self.x += self.vx
        self.y += self.vy
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf, camera: Camera):
        if not self.alive: return
        sx, sy = camera.world_to_screen(self.x, self.y)
        if not (-10 < sx < CANVAS_W + 10 and -10 < sy < CANVAS_H + 10): return
        # 方形子弹(敌人)
        pygame.draw.rect(surf, BLACK, (sx-2, sy-2, 5, 5))
        pygame.draw.rect(surf, self.color, (sx-1, sy-1, 3, 3))


# ============================================================
# 火箭弹（玩家火箭筒，爆炸AOE）
# ============================================================
class RocketBullet:
    def __init__(self, x, y, angle):
        s = WEAPON_STATS[WeaponType.ROCKET]
        self.x = x; self.y = y
        self.vx = math.cos(angle) * s["bullet_speed"]
        self.vy = math.sin(angle) * s["bullet_speed"]
        self.damage = s["damage"]
        self.explosion_radius = s["explosion_radius"]
        self.size = 4
        self.life = 8.0
        self.alive = True
        self.trail: List[Tuple[float, float]] = []

    def update(self, dt):
        self.trail.append((self.x, self.y))
        if len(self.trail) > 6:
            self.trail.pop(0)
        self.x += self.vx
        self.y += self.vy
        self.life -= dt
        if self.life <= 0:
            self.alive = False

    def draw(self, surf, camera: Camera):
        if not self.alive: return
        # 拖尾
        for i, (tx, ty) in enumerate(self.trail):
            a = (i + 1) / len(self.trail) * 0.6
            tsx, tsy = camera.world_to_screen(tx, ty)
            gray = int(180 * a)
            pygame.draw.rect(surf, (gray, gray // 3, gray // 3),
                             (tsx - 1, tsy - 1, 3, 3))
        sx, sy = camera.world_to_screen(self.x, self.y)
        # 弹体
        pygame.draw.rect(surf, BLACK, (sx - 3, sy - 3, 7, 7))
        pygame.draw.rect(surf, RED_BLOOD, (sx - 2, sy - 2, 5, 5))
        pygame.draw.rect(surf, (255, 180, 180), (sx - 1, sy - 1, 3, 3))


# ============================================================
# 炸药（放置型AOE，1秒引爆）
# ============================================================
class DynamiteEntity:
    def __init__(self, x: float, y: float):
        s = WEAPON_STATS[WeaponType.DYNAMITE]
        self.x = x; self.y = y
        self.damage = s["damage"]
        self.explosion_radius = s["explosion_radius"]
        self.fuse = 1.0  # 1秒引信
        self.alive = True
        self.bob = 0.0

    def update(self, dt: float):
        self.fuse -= dt
        self.bob += dt * 12
        if self.fuse <= 0:
            self.alive = False

    def draw(self, surf, camera: Camera):
        if not self.alive: return
        sx, sy = camera.world_to_screen(self.x, self.y)
        # 闪烁警告（最后 0.3 秒快速闪）
        if self.fuse < 0.3 and int(self.fuse * 20) % 2 == 0:
            # 红色闪烁
            pygame.draw.rect(surf, RED_BLOOD, (sx - 5, sy - 5, 11, 11))
            pygame.draw.rect(surf, WHITE, (sx - 3, sy - 3, 7, 7))
            return
        # 炸药外观：深灰方块+红色引信火花
        bob_offset = int(math.sin(self.bob) * 1)
        pygame.draw.rect(surf, BLACK, (sx - 4, sy - 4 + bob_offset, 9, 9))
        pygame.draw.rect(surf, GRAY_15, (sx - 3, sy - 3 + bob_offset, 7, 7))
        # 引信火花（顶部闪烁红点）
        spark_intensity = 1.0 - (0.7 * (self.fuse / 1.0))
        if random.random() < spark_intensity * 0.6:
            r = int(255 * spark_intensity)
            spark_color = (r, max(0, int(80 * spark_intensity)), 0)
            pygame.draw.rect(surf, spark_color, (sx - 1, sy - 6 + bob_offset, 3, 3))
            surf.set_at((sx, sy - 5 + bob_offset), (255, 200, 100))
        # TNT 字样
        if self.fuse > 0.5:
            pygame.draw.rect(surf, RED_BLOOD, (sx - 2, sy - 1 + bob_offset, 2, 1))
            pygame.draw.rect(surf, RED_BLOOD, (sx + 1, sy - 1 + bob_offset, 1, 3))


# ============================================================
# 玩家
# ============================================================
class Player:
    SIZE = 8  # 碰撞半径

    # 武器对应的枪管参数: (长度, 宽度, 颜色)
    # 子弹出膛距离（基于图标实际枪管长度，手持精灵是图标半尺寸）
    # (长度, 宽度, 颜色) — 宽度/颜色仅兼容旧代码，视觉已改用图标精灵
    GUN_PARAMS = {
        0: (5,  2, GRAY_20),   # 手枪
        1: (7,  3, GRAY_10),   # 霰弹
        2: (8,  1, GRAY_20),   # 步枪
        3: (9,  5, GRAY_08),   # 火箭筒
        4: (0,  0, (0,0,0)),   # 炸药（无枪管）
    }

    def __init__(self):
        self.x = 0.0; self.y = 0.0  # 世界坐标，初始在原点
        self.speed = 2.0
        self.health = 100; self.max_health = 100
        self.alive = True
        self.weapons = [WeaponType.PISTOL]
        self.current_weapon = WeaponType.PISTOL
        self.ammo = {WeaponType.PISTOL: 999, WeaponType.SHOTGUN: 15, WeaponType.RIFLE: 30, WeaponType.ROCKET: 0, WeaponType.DYNAMITE: 0}
        self.cooldown = 0.0
        self.hit_flash = 0.0
        self.invincible = 0.0
        self.aim_angle = 0.0
        self.score = 0; self.kills = 0

    def take_damage(self, amount):
        if self.invincible > 0: return
        self.health -= amount
        self.hit_flash = 0.15
        self.invincible = 0.5
        if self.health <= 0:
            self.health = 0; self.alive = False

    def switch_weapon(self):
        """循环切换武器"""
        idx = self.weapons.index(self.current_weapon)
        self.current_weapon = self.weapons[(idx + 1) % len(self.weapons)]

    def select_weapon(self, weapon_type: int) -> bool:
        """直接选中指定武器槽位。返回是否成功"""
        if weapon_type in self.weapons:
            self.current_weapon = weapon_type
            return True
        return False

    def add_weapon(self, w):
        if w not in self.weapons:
            self.weapons.append(w)

    def update(self, dt, keys, mouse_wx, mouse_wy):
        if not self.alive: return
        dx = mouse_wx - self.x
        dy = mouse_wy - self.y
        self.aim_angle = math.atan2(dy, dx)

        mx = my = 0
        if keys[pygame.K_w] or keys[pygame.K_UP]:    my -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:  my += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:  mx -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: mx += 1
        if mx and my:
            mx *= 0.707; my *= 0.707

        self.x += mx * self.speed
        self.y += my * self.speed
        # 无限地图 — 不限制边界！

        if self.cooldown > 0: self.cooldown -= dt
        if self.invincible > 0: self.invincible -= dt
        if self.hit_flash > 0: self.hit_flash -= dt

    def shoot(self) -> List[Bullet]:
        if self.cooldown > 0 or not self.alive: return []
        w = self.current_weapon
        s = WEAPON_STATS[w]
        if self.ammo[w] <= 0: return []
        self.cooldown = s["fire_rate"]
        self.ammo[w] -= 1

        gun_len = self.GUN_PARAMS.get(w, self.GUN_PARAMS[0])[0]
        muzzle_dist = self.SIZE + gun_len
        mx = self.x + math.cos(self.aim_angle) * muzzle_dist
        my = self.y + math.sin(self.aim_angle) * muzzle_dist

        bullets = []
        for _ in range(s["count"]):
            spread = random.uniform(-s["spread"], s["spread"])
            angle = self.aim_angle + spread
            bullets.append(Bullet(mx, my, angle, w))
        return bullets

    def draw(self, surf, camera: Camera):
        if not self.alive: return
        if self.invincible > 0 and int(self.invincible * 20) % 2 == 0: return

        sx, sy = camera.world_to_screen(self.x, self.y)
        flip = 1 if math.cos(self.aim_angle) >= 0 else -1
        t = pygame.time.get_ticks() * 0.001
        walk = int(math.sin(t * 8))
        hit = self.hit_flash > 0

        # 参考图调色板: 深色身体+浅灰高光+白色护目镜亮点
        dark  = WHITE if hit else GRAY_12   # 极深身体(参考图暗色)
        mid   = WHITE if hit else GRAY_42   # 中灰高光
        brite = BLACK if hit else WHITE      # 白色亮点

        fx = lambda dx: dx * flip
        body = [
            # 圆顶头盔(参考图:弧形顶部)
            (fx(-1),-9),(fx(0),-9),
            (fx(-3),-8),(fx(-2),-8),(fx(1),-8),(fx(2),-8),
            (fx(-4),-7),(fx(-3),-7),(fx(2),-7),(fx(3),-7),
            (fx(-4),-6),(fx(-3),-6),(fx(-2),-6),(fx(-1),-6),(fx(0),-6),(fx(1),-6),(fx(2),-6),(fx(3),-6),
            # 护目镜横条(参考图:横贯眼部的亮条)
            (fx(-3),-5),(fx(-2),-5),(fx(-1),-5),(fx(0),-5),(fx(1),-5),(fx(2),-5),
            # 面部/领口
            (fx(-3),-4),(fx(-2),-4),(fx(-1),-4),(fx(0),-4),(fx(1),-4),(fx(2),-4),
            # 宽肩胸甲(参考图:倒三角上身)
            (fx(-5),-3),(fx(-4),-3),(fx(-3),-3),(fx(2),-3),(fx(3),-3),(fx(4),-3),
            (fx(-5),-2),(fx(-4),-2),(fx(-3),-2),(fx(-2),-2),(fx(-1),-2),(fx(0),-2),(fx(1),-2),(fx(2),-2),(fx(3),-2),(fx(4),-2),
            (fx(-5),-1),(fx(-4),-1),(fx(3),-1),(fx(4),-1),
            # 躯干
            (fx(-5),0),(fx(-4),0),(fx(-3),0),(fx(-2),0),(fx(-1),0),(fx(0),0),(fx(1),0),(fx(2),0),(fx(3),0),(fx(4),0),
            (fx(-4),1),(fx(-3),1),(fx(-2),1),(fx(-1),1),(fx(0),1),(fx(1),1),(fx(2),1),(fx(3),1),
            (fx(-4),2),(fx(-3),2),(fx(2),2),(fx(3),2),
            (fx(-3),3),(fx(-2),3),(fx(1),3),(fx(2),3),
            # 腰带(参考图:腰间横线)
            (fx(-4),4),(fx(-3),4),(fx(-2),4),(fx(-1),4),(fx(0),4),(fx(1),4),(fx(2),4),(fx(3),4),
            # 分开的腿+行走动画
            (fx(-4),5+walk),(fx(-3),5+walk),
            (fx(-4),6+walk),(fx(-3),6+walk),
            (fx(1),5-walk),(fx(2),5-walk),
            (fx(1),6-walk),(fx(2),6-walk),
            # 靴子
            (fx(-5),7+walk),(fx(-4),7+walk),(fx(-2),7+walk),
            (fx(1),7-walk),(fx(3),7-walk),(fx(4),7-walk),
        ]
        hl = [
            (fx(-1),-7),(fx(1),-7),               # 护目镜亮点(白)
            (fx(-4),-3),(fx(3),-3),               # 肩甲高光
            (fx(-2),2),(fx(1),2),                 # 腰
        ]
        _sprite(surf, sx, sy-3, body, dark, hl, brite)

        # 持枪手臂
        ax = int(sx + math.cos(self.aim_angle) * 5)
        ay = int(sy-3 + math.sin(self.aim_angle) * 5)
        pygame.draw.line(surf, BLACK, (sx+fx(3), sy-3), (ax+1, ay+1), 3)
        pygame.draw.line(surf, dark,  (sx+fx(3), sy-3), (ax, ay), 1)

        # 手持武器（与物品栏图标视觉一致，按瞄准角度旋转）
        gsx = int(sx + math.cos(self.aim_angle) * 4)
        gsy = int(sy-3 + math.sin(self.aim_angle) * 4)
        _draw_hand_gun(surf, gsx, gsy, self.aim_angle, self.current_weapon, hit)


# ============================================================
# 敌人
# ============================================================
class Enemy:
    def __init__(self, x, y, etype: str, wave: int):
        self.x = x; self.y = y
        self.type = etype
        self.alive = True
        diff = 1 + wave * 0.12

        if etype == "runner":
            # 中速中攻脆皮 — 追不上玩家但有威胁
            self.health = int(35 * diff); self.max_health = self.health
            self.speed = 1.1 + wave * 0.02; self.damage = 14 + wave
            self.color = GRAY_60; self.size = 4  # 狼灰色
            self.score = 15; self.behavior = "zigzag"
        elif etype == "tank":
            # 远程射击+极高血量+极慢移速+高射速
            self.health = int(180 * diff); self.max_health = self.health
            self.speed = 0.2 + wave * 0.015; self.damage = 15 + wave
            self.color = GRAY_06; self.size = 7
            self.score = 30; self.behavior = "chase"
            self.shoot_cooldown = 0.0
            self.shoot_interval = 0.6  # 高射速，持续火力压制
            self.shoot_range = 90
        else:  # ghost
            # 隐形+快速+中等攻击 — 飘得快有压迫感
            self.health = int(50 * diff); self.max_health = self.health
            self.speed = 0.9 + wave * 0.04; self.damage = 12 + wave
            self.color = GRAY_50; self.size = 5
            self.score = 20; self.behavior = "float"
            self.visible = False
            self.reveal_timer = 0.0

        self.stun_timer = 0.0
        self.zigzag_timer = random.uniform(0, 3)
        self.zigzag_dir = random.choice([-1, 1])
        self.float_offset = random.uniform(0, 6.28)

    def take_damage(self, dmg):
        self.health -= dmg
        if self.health <= 0: self.alive = False

    def update(self, dt, px, py):
        if not self.alive: return 0, 0, None, None
        if self.stun_timer > 0:
            self.stun_timer -= dt; return 0, 0, None, None

        dx = px - self.x; dy = py - self.y
        dist = math.hypot(dx, dy) or 1

        mx = (dx / dist) * self.speed
        my = (dy / dist) * self.speed

        if self.behavior == "zigzag":
            self.zigzag_timer += dt
            if self.zigzag_timer > 0.8:
                self.zigzag_timer = 0; self.zigzag_dir *= -1
            mx += (-dy / dist) * self.speed * 0.6 * self.zigzag_dir
            my += (dx / dist) * self.speed * 0.6 * self.zigzag_dir
        elif self.behavior == "float":
            self.float_offset += dt * 2
            my += math.sin(self.float_offset) * 0.3

        self.x += mx; self.y += my

        # ── 坦克射击逻辑 ──
        bullet = None
        muzzle = None  # (x,y,angle) for muzzle flash
        if self.type == "tank":
            self.shoot_cooldown -= dt
            if self.shoot_cooldown <= 0 and dist < self.shoot_range:
                self.shoot_cooldown = self.shoot_interval
                angle = math.atan2(py - self.y, px - self.x)
                bullet = TankBullet(self.x, self.y, angle)
                muzzle = (self.x + math.cos(angle)*8,
                          self.y + math.sin(angle)*8, angle)

        # ── 幽灵隐身逻辑 ──
        if self.type == "ghost":
            if dist < 25:
                self.visible = True
                self.reveal_timer = 1.5
            elif self.reveal_timer > 0:
                self.reveal_timer -= dt
                self.visible = True
            else:
                self.visible = False

        return mx, my, bullet, muzzle

    def draw(self, surf, camera: Camera):
        if not self.alive: return
        sx, sy = camera.world_to_screen(self.x, self.y)
        if not (-30 < sx < CANVAS_W+30 and -30 < sy < CANVAS_H+30): return

        # 幽灵隐身：不可见时只画一个极淡轮廓
        if self.type == "ghost" and not self.visible:
            ghost_sx, ghost_sy = sx, sy
            pygame.draw.rect(surf, GRAY_85, (ghost_sx-3, ghost_sy-3, 6, 6), 1)
            return

        t = pygame.time.get_ticks()*0.001

        if self.type == "runner":
            # 四腿兽形(狼/狗), 长吻, 低趴
            leg = int(math.sin(t*10 + self.zigzag_timer*3)*2)
            body_c, teeth_c = GRAY_15, GRAY_80
            bp = [
                # 头部+长吻
                (-2,-5),(-1,-5),(0,-5),(1,-5),(2,-5),
                (-2,-4),(-1,-4),(0,-4),(1,-4),(2,-4),(3,-4),
                (-1,-3),(0,-3),(1,-3),(2,-3),(3,-3),
                # 身体(低趴长条)
                (-4,-2),(-3,-2),(-2,-2),(-1,-2),(0,-2),(1,-2),(2,-2),(3,-2),(4,-2),(5,-2),
                (-4,-1),(-3,-1),(-2,-1),(-1,-1),(0,-1),(1,-1),(2,-1),(3,-1),(4,-1),(5,-1),
                (-3,0),(-2,0),(-1,0),(0,0),(1,0),(2,0),(3,0),(4,0),(5,0),
                # 背脊
                (-2,-3),
                # 四条腿(交替动画)
                (-4,1+leg),(-3,1+leg),(-1,1-leg),(0,1-leg),
                (-4,2+leg),(-3,2+leg),(-1,2-leg),(0,2-leg),
                (4,1-leg),(5,1-leg),(6,1+leg),(7,1+leg),
                (4,2-leg),(5,2-leg),(6,2+leg),(7,2+leg),
                # 尾部
                (-5,0),(-5,1+leg),(-6,1+leg),
            ]
            hl = [(1,-4),(2,-4),(3,-4),(-2,-3)]
            _sprite(surf, sx, sy, bp, body_c, hl, teeth_c)

        elif self.type == "tank":
            # 极暗近乎黑的宽体坦克,护甲高光=极其明显的对比
            breath = int(abs(math.sin(t*2)))
            body_c, armor_c = GRAY_06, GRAY_50
            bp = [
                # 极小头(参考图特征:头身比极小)
                (-1,-9+breath),(0,-9+breath),(1,-9+breath),
                (-2,-8+breath),(-1,-8+breath),(0,-8+breath),(1,-8+breath),(2,-8+breath),
                (-2,-7+breath),(-1,-7+breath),(0,-7+breath),(1,-7+breath),(2,-7+breath),
                # 极宽身躯(参考图:10+px宽)
                (-5,-6+breath),(-4,-6+breath),(-3,-6+breath),(-2,-6+breath),(-1,-6+breath),(0,-6+breath),
                (1,-6+breath),(2,-6+breath),(3,-6+breath),(4,-6+breath),(5,-6+breath),
                (-5,-5+breath),(-4,-5+breath),(-3,-5+breath),(-2,-5+breath),(-1,-5+breath),(0,-5+breath),
                (1,-5+breath),(2,-5+breath),(3,-5+breath),(4,-5+breath),(5,-5+breath),
                (-6,-4+breath),(-5,-4+breath),(-4,-4+breath),(4,-4+breath),(5,-4+breath),(6,-4+breath),
                (-6,-3+breath),(-5,-3+breath),(-4,-3+breath),(4,-3+breath),(5,-3+breath),(6,-3+breath),
                (-6,-2+breath),(-5,-2+breath),(-4,-2+breath),(4,-2+breath),(5,-2+breath),(6,-2+breath),
                (-5,-1+breath),(-4,-1+breath),(4,-1+breath),(5,-1+breath),
                (-5,0+breath),(-4,0+breath),(4,0+breath),(5,0+breath),
                # 粗腿
                (-5,1+breath),(-4,1+breath),(-3,1+breath),(3,1+breath),(4,1+breath),(5,1+breath),
                (-5,2+breath),(-4,2+breath),(-3,2+breath),(3,2+breath),(4,2+breath),(5,2+breath),
                (-4,3+breath),(-3,3+breath),(3,3+breath),(4,3+breath),
            ]
            hl = [(-4,-5+breath),(4,-5+breath),(-3,-3+breath),(3,-3+breath),
                  (0,-7+breath),(2,-7+breath)]
            _sprite(surf, sx, sy, bp, body_c, hl, armor_c)

        else:  # ghost
            # 经典幽灵形象：圆顶+波浪底边+两只大眼睛
            fy = int(math.sin(t*2.5+self.float_offset)*3)
            body_c, eye_c = GRAY_50, WHITE
            # 波浪底部偏移
            w1 = int(math.sin(t*3+self.float_offset)*2+fy)
            w2 = int(math.cos(t*3+self.float_offset)*2+fy)
            w3 = int(math.sin(t*3+1+self.float_offset)*2+fy)
            w4 = int(math.cos(t*3+1+self.float_offset)*2+fy)
            bp = [
                # 圆顶头部
                (-3,-9),(3,-9),
                (-4,-8),(-3,-8),(-2,-8),(-1,-8),(0,-8),(1,-8),(2,-8),(3,-8),(4,-8),
                (-5,-7),(-4,-7),(-3,-7),(-2,-7),(-1,-7),(0,-7),(1,-7),(2,-7),(3,-7),(4,-7),(5,-7),
                (-5,-6),(-4,-6),(-3,-6),(-2,-6),(-1,-6),(0,-6),(1,-6),(2,-6),(3,-6),(4,-6),(5,-6),
                (-6,-5),(-5,-5),(-4,-5),(-3,-5),(-2,-5),(-1,-5),(0,-5),(1,-5),(2,-5),(3,-5),(4,-5),(5,-5),(6,-5),
                (-6,-4),(-5,-4),(-4,-4),(-3,-4),(-2,-4),(-1,-4),(0,-4),(1,-4),(2,-4),(3,-4),(4,-4),(5,-4),(6,-4),
                # 身体（宽大）
                (-6,-3),(-5,-3),(-4,-3),(-3,-3),(-2,-3),(-1,-3),(0,-3),(1,-3),(2,-3),(3,-3),(4,-3),(5,-3),(6,-3),
                (-6,-2),(-5,-2),(-4,-2),(-3,-2),(-2,-2),(-1,-2),(0,-2),(1,-2),(2,-2),(3,-2),(4,-2),(5,-2),(6,-2),
                (-6,-1),(-5,-1),(-4,-1),(-3,-1),(-2,-1),(-1,-1),(0,-1),(1,-1),(2,-1),(3,-1),(4,-1),(5,-1),(6,-1),
                (-5,0),(-4,0),(-3,0),(-2,0),(-1,0),(0,0),(1,0),(2,0),(3,0),(4,0),(5,0),
                # 波浪底边（上凹下凸交替）
                (-5,1+w1),(-4,1+w1),(-3,1+w1),
                (-2,1+w2),(-1,1+w2),(0,1+w2),(1,1+w2),
                (2,1+w3),(3,1+w3),
                (4,1+w4),(5,1+w4),
                (-5,2+w1),(-4,2+w1),(-3,2+w1),
                (-2,2+w2),(2,2+w3),
                (4,2+w4),(5,2+w4),
            ]
            # 大眼睛（白色+黑瞳孔）
            hl = [(-4,-3),(3,-3),(-4,-4),(3,-4),(-3,-3),(4,-3),(-3,-4),(4,-4),
                  (-2,-5),(4,-5),(-2,-6),(4,-6),
                  (-5,-1),(5,-1),(-5,-2),(5,-2)]
            _sprite(surf, sx, sy, bp, body_c, hl, eye_c)
            # 眼球瞳孔（看向玩家方向 — 左右交替）
            pupil_off = 1 if int(t*1.5) % 2 == 0 else -1
            pupil_color = BLACK if self.visible else GRAY_40
            for px_off in [-3, 3]:
                surf.set_at((sx+px_off+pupil_off, sy-3), pupil_color)
                surf.set_at((sx+px_off+pupil_off, sy-4), pupil_color)

        # 被击晕十字标记
        if self.stun_timer > 0:
            stx, sty = sx+9, sy-7
            for d in [(1,0),(-1,0),(0,1),(0,-1)]:
                pygame.draw.line(surf, WHITE, (stx,sty),(stx+d[0]*2,sty+d[1]*2), 1)

        # 头顶血条
        bar_w = self.size * 3
        bar_h = 2
        bar_x = sx - bar_w // 2
        bar_y = sy - self.size - 5
        if 0 <= bar_y < CANVAS_H:
            bar_x = max(0, bar_x)
            bar_w = min(bar_w, CANVAS_W - bar_x)
            pct = max(0, self.health / self.max_health)
            pygame.draw.rect(surf, BLACK, (bar_x - 1, bar_y - 1, bar_w + 2, bar_h + 2))
            pygame.draw.rect(surf, GRAY_30, (bar_x, bar_y, bar_w, bar_h))
            if pct > 0:
                bar_c = GRAY_70 if pct > 0.5 else (GRAY_50 if pct > 0.25 else RED_BLOOD)
                pygame.draw.rect(surf, bar_c, (bar_x, bar_y, int(bar_w * pct), bar_h))


# ============================================================
# 掉落物
# ============================================================
class Item:
    # 地图散落的盲盒（等概率武器/弹药）
    # 普通池（80%概率）：枪支弹药
    GUN_POOL = [
        "ammo_pistol", "ammo_shotgun", "ammo_rifle",
        "weapon_shotgun", "weapon_rifle",
    ]
    # 稀有池（20%概率）：爆炸物
    RARE_POOL = ["rocket", "dynamite"]

    @classmethod
    def random_mystery(cls) -> str:
        """80%枪支弹药，20%爆炸物"""
        if random.random() < 0.2:
            return random.choice(cls.RARE_POOL)
        return random.choice(cls.GUN_POOL)

    def __init__(self, x, y, item_type):
        self.x = x; self.y = y
        self.type = item_type
        self.alive = True
        self.bob = random.uniform(0, 6.28)
        self.life = 9999.0  # 永久存在，只靠距离清理
        self.flash_after = 9999.0

    def update(self, dt):
        # 物品不会因时间消失，只靠距离清理
        pass

    def draw(self, surf, camera: Camera):
        if not self.alive: return

        sx, sy = camera.world_to_screen(self.x, self.y)
        bob = int(math.sin(self.bob + pygame.time.get_ticks() * 0.003) * 2)
        sy += bob

        if self.type == "health":
            # 回血方块 — 深色底+红色十字
            bx, by_box = sx - 5, sy - 5
            pygame.draw.rect(surf, BLACK, (bx - 1, by_box - 1, 12, 12))
            pygame.draw.rect(surf, GRAY_20, (bx, by_box, 10, 10))
            # 红色十字
            pygame.draw.rect(surf, RED_BLOOD, (bx + 4, by_box + 1, 2, 8))  # 竖
            pygame.draw.rect(surf, RED_BLOOD, (bx + 1, by_box + 4, 8, 2))  # 横
            # 十字中心高光
            surf.set_at((bx + 5, by_box + 4), (255, 140, 140))
        else:
            # 盲盒 — 黑方块+白色问号
            bx, by_box = sx - 5, sy - 5
            pygame.draw.rect(surf, WHITE, (bx - 1, by_box - 1, 12, 12), 1)
            pygame.draw.rect(surf, BLACK, (bx, by_box, 10, 10))
            q_color = GRAY_80
            pygame.draw.rect(surf, q_color, (bx + 2, by_box + 1, 5, 1))
            pygame.draw.rect(surf, q_color, (bx + 6, by_box + 2, 1, 2))
            pygame.draw.rect(surf, q_color, (bx + 5, by_box + 4, 2, 1))
            pygame.draw.rect(surf, q_color, (bx + 6, by_box + 5, 1, 2))
            pygame.draw.rect(surf, q_color, (bx + 4, by_box + 7, 2, 2))
            if int(pygame.time.get_ticks() * 0.004) % 2 == 0:
                surf.set_at((bx + 1, by_box + 1), WHITE)


# ============================================================
# 安全屋
# ============================================================
# HUD
# ============================================================
# ============================================================
# 物品栏像素图标 — 大尺寸高辨识度
# 每个图标14x20区域, 填满30x28槽位
# ============================================================
# 颜色编码: B=主色, H=高光, S=阴影/暗部, F=火焰
# 高细节武器图标（24×14，水平剪影）
# 字符含义:
#   B = 主体金属      b = 暗金属/阴影
#   H = 高光          h = 极暗高光/深色防滑纹
#   W = 木质          w = 暗木
#   G = 握把塑料      g = 暗握把
#   F = 火花/引信     S = 绑带
#   R = 红色战斗部    r = 暗红
WEAPON_ICON_DATA = {
    # M1911 手枪 — 套筒防滑纹+击锤+扳机护圈+木握把
    WeaponType.PISTOL: [
        "                        ",
        "                        ",
        "                        ",
        "    HHHHHHHHHHH         ",
        "   BBBBBBBBBBBBBh       ",
        "   BHBHBHBHBHB BB       ",
        "   BBBBBBBBBBBBBBB      ",
        "   BBB  bb    bbb       ",
        "   GGG  bb     bb       ",
        "   GGGG bb              ",
        "   GGgG bb              ",
        "   GGgG                 ",
        "   GGG                  ",
        "                        ",
    ],
    # 雷明顿870 — 泵动滑套+管状弹仓+机匣+木枪托
    WeaponType.SHOTGUN: [
        "                        ",
        "                        ",
        "    HHHHHHHHHHHHHH      ",
        "   BBBBBBBBBBBBBBBB     ",
        "  BBBBBBBBBBBBBBBBBBW   ",
        "  BBBbbbbbBBBBBBBBBWWW  ",
        "  BBBBBBBBBBBBBBBBWWWW  ",
        "   bbbbbb  BBB    WWWw  ",
        "           BB     WWw   ",
        "           Bbb    WW    ",
        "            bb   Ww     ",
        "                 Ww     ",
        "                        ",
        "                        ",
    ],
    # AK-47 — 弯弹匣+导气管+准星+木护木+木枪托
    WeaponType.RIFLE: [
        "                        ",
        "        H               ",
        "       BB  HHHHHHHHH    ",
        "   HHH BBBBBBBBBBBBBB   ",
        "  BBBBBBBBBBBBBBBBBBBW  ",
        "  BBBWWWWBBBBBBbBBWWWW  ",
        "  BBWWWWWBBBBBBBbBWWWW  ",
        "  B  WWWW  BBB BB WWw   ",
        "          BBB  BB Ww    ",
        "         BBB    BB      ",
        "        BBB     BB      ",
        "       BBB       B      ",
        "       BB               ",
        "                        ",
    ],
    # RPG-7 — 红色战斗部+黑管身+尾喷+握把扳机
    WeaponType.ROCKET: [
        "                        ",
        "        RR              ",
        "       RRRR             ",
        "      RRRRRR            ",
        "     RRRRRRRR           ",
        "    RRRRRRRRRRBBBBBBB   ",
        "   rRRRRRRRRBBBBBBBBBB  ",
        "  rrRRRRRRBBBBBBBBBBBBb ",
        "   rRRRRRBBBBBBBBBBBBBbb",
        "    RRRBBBBBBBb bbb bbb ",
        "     RBBBB  bb          ",
        "      BBB    bb   bbb   ",
        "       B          bb    ",
        "                        ",
    ],
    # TNT 炸药捆 — 整体红色为主+黑绑带+引信火花
    WeaponType.DYNAMITE: [
        "           F            ",
        "          FFF           ",
        "          FFF           ",
        "           b            ",
        "   RRR RRR RRR  b       ",
        "  RRRRRRRRRRRR b        ",
        "  RHRRHRRHRRHRb         ",
        "  RRRRRRRRRRRR          ",
        "  SSSSSSSSSSSS          ",
        "  RRRRRRRRRRRR          ",
        "  RHRRHRRHRRHR          ",
        "  RRRRRRRRRRRR          ",
        "   RRR RRR RRR          ",
        "                        ",
    ],
}

SLOT_W, SLOT_H = 30, 28
SLOT_GAP = 4
NUM_SLOTS = 5
BOTTOM_PAD = 8

_inv_slot_rects = []

# 武器图标颜色映射（v2 — 高细节调色板）
_ICON_PALETTES = {
    WeaponType.PISTOL: {
        'B': (70, 70, 75), 'b': (45, 45, 50),
        'H': (200, 200, 210), 'h': (30, 30, 35),
        'G': (90, 65, 40), 'g': (60, 45, 30),
        'W': (110, 80, 50), 'w': (75, 55, 35),
        'R': (180, 40, 40), 'r': (120, 25, 25),
        'F': (255, 220, 80), 'S': (25, 25, 25),
    },
    WeaponType.SHOTGUN: {
        'B': (50, 50, 55), 'b': (35, 35, 40),
        'H': (170, 170, 180), 'h': (25, 25, 30),
        'G': (80, 80, 85), 'g': (55, 55, 60),
        'W': (120, 85, 50), 'w': (80, 55, 35),
        'R': (180, 40, 40), 'r': (120, 25, 25),
        'F': (255, 220, 80), 'S': (25, 25, 25),
    },
    WeaponType.RIFLE: {
        'B': (55, 55, 60), 'b': (40, 40, 45),
        'H': (190, 190, 200), 'h': (30, 30, 35),
        'G': (80, 80, 85), 'g': (55, 55, 60),
        'W': (125, 90, 55), 'w': (85, 60, 40),
        'R': (180, 40, 40), 'r': (120, 25, 25),
        'F': (255, 220, 80), 'S': (25, 25, 25),
    },
    WeaponType.ROCKET: {
        'B': (45, 45, 50), 'b': (30, 30, 35),
        'H': (160, 160, 170), 'h': (25, 25, 30),
        'G': (75, 75, 80), 'g': (50, 50, 55),
        'W': (110, 80, 50), 'w': (75, 55, 35),
        'R': (200, 50, 50), 'r': (140, 30, 30),
        'F': (255, 220, 80), 'S': (25, 25, 25),
    },
    WeaponType.DYNAMITE: {
        'B': (50, 50, 55), 'b': (35, 35, 40),
        'H': (255, 180, 140), 'h': (25, 25, 30),
        'G': (80, 80, 85), 'g': (55, 55, 60),
        'W': (110, 80, 50), 'w': (75, 55, 35),
        'R': (190, 45, 35), 'r': (130, 30, 25),
        'F': (255, 230, 100), 'S': (20, 15, 15),
    },
}


def _draw_pixel_icon(surf, cx: int, cy: int, icon_data: list, colors: dict):
    """绘制像素图标。colors key 对应图标数据中的字符。
    先绘制8向黑色描边，再绘制主体，确保在深色背景里清晰。"""
    rows = len(icon_data)
    cols = len(icon_data[0])
    # 收集所有非空格像素
    filled = set()
    for r, row in enumerate(icon_data):
        for c, ch in enumerate(row):
            if ch != ' ':
                filled.add((c, r))
    # 第一遍：绘制黑边（所有填充像素的8邻域中不属于填充的位置）
    outline = set()
    for (c, r) in filled:
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if dc == 0 and dr == 0:
                    continue
                n = (c + dc, r + dr)
                if n not in filled:
                    outline.add(n)
    for (c, r) in outline:
        dx = c - cols // 2
        dy = r - rows // 2
        px, py = cx + dx, cy + dy
        if 0 <= px < surf.get_width() and 0 <= py < surf.get_height():
            surf.set_at((px, py), BLACK)
    # 第二遍：绘制主体
    for r, row in enumerate(icon_data):
        for c, ch in enumerate(row):
            if ch == ' ':
                continue
            dx = c - cols // 2
            dy = r - rows // 2
            px, py = cx + dx, cy + dy
            if 0 <= px < surf.get_width() and 0 <= py < surf.get_height():
                clr = colors.get(ch)
                if clr:
                    surf.set_at((px, py), clr)


def _draw_slot_icon(surf, sx: int, sy: int, weapon_type: int):
    icon = WEAPON_ICON_DATA.get(weapon_type)
    if not icon:
        return
    rows = len(icon)
    cx = sx + SLOT_W // 2
    # 垂直居中偏上一点（给弹药数字留底部空间）
    cy = sy + (SLOT_H - 6) // 2 + 1
    colors = _ICON_PALETTES.get(weapon_type, {'B': GRAY_60, 'H': GRAY_80, 'F': WHITE})
    _draw_pixel_icon(surf, cx, cy, icon, colors)


# ============================================================
# 手持武器精灵（复用物品栏图标数据，与物品栏视觉一致）
# ============================================================
_HAND_GUN_CACHE: dict = {}

def _get_hand_gun_sprite(weapon_type: int, hit: bool = False) -> pygame.Surface:
    """根据 WEAPON_ICON_DATA 构建手持武器精灵 Surface（带缓存）。
    返回朝右的枪的 surface，尺寸约为 12x7。
    hit=True 时返回全白版本（受击闪白用）。"""
    key = (weapon_type, hit)
    if key in _HAND_GUN_CACHE:
        return _HAND_GUN_CACHE[key]

    icon = WEAPON_ICON_DATA.get(weapon_type)
    if not icon:
        s = pygame.Surface((1, 1), pygame.SRCALPHA)
        _HAND_GUN_CACHE[key] = s
        return s

    palette = _ICON_PALETTES.get(weapon_type, {'B': GRAY_60, 'H': GRAY_80, 'F': WHITE})
    rows = len(icon)
    cols = len(icon[0])

    # 收集填充像素
    filled = set()
    for r, row in enumerate(icon):
        for c, ch in enumerate(row):
            if ch != ' ':
                filled.add((c, r))
    # 8向黑边
    outline = set()
    for (c, r) in filled:
        for dc in (-1, 0, 1):
            for dr in (-1, 0, 1):
                if dc == 0 and dr == 0:
                    continue
                n = (c + dc, r + dr)
                if n not in filled:
                    outline.add(n)

    surf = pygame.Surface((cols, rows), pygame.SRCALPHA)
    # 描边
    for (c, r) in outline:
        surf.set_at((c, r), WHITE if hit else BLACK)
    # 主体
    for r, row in enumerate(icon):
        for c, ch in enumerate(row):
            if ch == ' ':
                continue
            color = WHITE if hit else palette.get(ch, GRAY_60)
            surf.set_at((c, r), color)

    # 缩小一半（24x14 -> 12x7），更像"手里的枪"
    small = pygame.transform.scale(surf, (cols // 2, rows // 2))
    _HAND_GUN_CACHE[key] = small
    return small


def _draw_hand_gun(surf, sx: int, sy: int, angle: float, weapon_type: int, hit: bool = False):
    """在玩家手上绘制当前武器精灵，按瞄准角度旋转。
    sx, sy: 手部位置（屏幕坐标）
    angle: 瞄准角度（弧度，0=右）
    """
    sprite = _get_hand_gun_sprite(weapon_type, hit)

    # 瞄准左边时水平翻转（让枪管始终指向鼠标方向）
    flip = math.cos(angle) < 0
    if flip:
        sprite = pygame.transform.flip(sprite, True, False)

    # pygame 旋转角度是逆时针，屏幕 y 轴向下，所以要取负
    rot_angle = -math.degrees(angle)
    if flip:
        rot_angle = 180 - rot_angle
    rotated = pygame.transform.rotate(sprite, rot_angle)

    # 精灵中心对齐手部，向瞄准方向偏移一点
    offset_dist = 3
    cx = sx + int(math.cos(angle) * offset_dist)
    cy = sy + int(math.sin(angle) * offset_dist)
    rect = rotated.get_rect(center=(cx, cy))
    surf.blit(rotated, rect)


def _draw_inventory(surf, player):
    """半透明物品栏 — 大范围透明+淡灰框架+精细武器图标+英文名称"""
    global _inv_slot_rects
    _inv_slot_rects = []
    owned = set(player.weapons)

    slot_types = [
        (WeaponType.PISTOL, None),
        (WeaponType.SHOTGUN, None),
        (WeaponType.RIFLE, None),
        (WeaponType.ROCKET, None),
        (WeaponType.DYNAMITE, None),
    ]

    total_w = NUM_SLOTS * SLOT_W + (NUM_SLOTS - 1) * SLOT_GAP
    start_x = CANVAS_W // 2 - total_w // 2
    bar_y = CANVAS_H - SLOT_H - BOTTOM_PAD

    # 半透明分隔线 — 上下对称间距
    INV_VPAD = 5
    top_line_y = bar_y + 2 - INV_VPAD
    bottom_line_y = bar_y + 2 + SLOT_H + INV_VPAD
    pygame.draw.line(surf, GRAY_40,
                     (start_x - 4, top_line_y), (start_x + total_w + 4, top_line_y), 1)
    pygame.draw.line(surf, GRAY_30,
                     (start_x - 4, bottom_line_y), (start_x + total_w + 4, bottom_line_y), 1)

    for i, (wtype, _) in enumerate(slot_types):
        sx = start_x + i * (SLOT_W + SLOT_GAP)
        sy = bar_y + 2
        is_current = (wtype == player.current_weapon)
        has_weapon = (wtype in owned)
        _inv_slot_rects.append((sx, sy, SLOT_W, SLOT_H, wtype))

        if is_current:
            border_color = WHITE
            border_w = 2
        elif not has_weapon:
            border_color = GRAY_20
            border_w = 1
        else:
            border_color = GRAY_30
            border_w = 1
        pygame.draw.rect(surf, border_color, (sx, sy, SLOT_W, SLOT_H), border_w)

        if is_current:
            pygame.draw.rect(surf, GRAY_15, (sx + 2, sy + 2, SLOT_W - 4, SLOT_H - 4))

        if has_weapon:
            _draw_slot_icon(surf, sx, sy, wtype)
            ammo = player.ammo.get(wtype, 0)
            if wtype == WeaponType.PISTOL:
                ammo_str = "inf"
            elif ammo >= 1000:
                ammo_str = "999"
            else:
                ammo_str = str(ammo)
            ammo_txt = FONT_SMALL.render(ammo_str, True, GRAY_80)
            atx = sx + SLOT_W - ammo_txt.get_width() - 3
            aty = sy + SLOT_H - ammo_txt.get_height() - 1
            surf.blit(ammo_txt, (atx, aty))
            if is_current:
                pygame.draw.line(surf, WHITE, (sx + 4, sy - 1), (sx + SLOT_W - 4, sy - 1), 2)
        else:
            cx = sx + SLOT_W // 2
            cy = sy + SLOT_H // 2
            for ox, oy in [(-3, -3), (3, 3), (-3, 3), (3, -3)]:
                px, py = cx + ox, cy + oy
                if 0 <= px < surf.get_width() and 0 <= py < surf.get_height():
                    surf.set_at((px, py), GRAY_22)

    # 英文名称 + 伤害（物品栏上方，留间距）
    ws = WEAPON_STATS[player.current_weapon]
    name_txt = FONT_SMALL.render(f"{ws['ename']}  dmg:{ws['damage']}", True, WHITE)
    surf.blit(name_txt, (start_x, top_line_y - name_txt.get_height() - 3))


def get_clicked_slot(mouse_screen_x: int, mouse_screen_y: int) -> int:
    """检测鼠标点击落在哪个物品栏槽位上。返回 weapon_type 或 -1"""
    # 屏幕坐标 → 画布坐标
    px = mouse_screen_x // PIXEL_SCALE
    py = mouse_screen_y // PIXEL_SCALE
    for sx, sy, sw, sh, wtype in _inv_slot_rects:
        if sx <= px <= sx + sw and sy <= py <= sy + sh:
            return wtype
    return -1


def draw_hud(surf, player, wave, enemies_left, time_alive):
    # 生命条
    bar_x, bar_y, bar_w, bar_h = 3, 2, 60, 7
    pct = player.health / player.max_health
    pygame.draw.rect(surf, GRAY_20, (bar_x, bar_y, bar_w, bar_h))
    pygame.draw.rect(surf, BLACK, (bar_x-1, bar_y-1, bar_w+2, bar_h+2), 1)
    if pct > 0:
        hp_c = GRAY_60 if pct > 0.5 else (GRAY_50 if pct > 0.25 else RED_BLOOD)
        pygame.draw.rect(surf, hp_c, (bar_x, bar_y, int(bar_w * pct), bar_h))

    hp_txt = FONT_SMALL.render(f"HP {player.health}", True, WHITE)
    surf.blit(hp_txt, (bar_x + bar_w + 4, bar_y - 1))

    ws = WEAPON_STATS[player.current_weapon]
    wp_txt = FONT_SMALL.render(
        f"[{ws['name']}] Ammo:{player.ammo[player.current_weapon]}", True, GRAY_70)
    surf.blit(wp_txt, (bar_x + bar_w + 4, bar_y + 10))

    # 右上角信息
    wave_txt = FONT_SMALL.render(
        f"Wave {wave}  Left:{enemies_left}  Time:{int(time_alive)}s", True, WHITE)
    surf.blit(wave_txt, (CANVAS_W - 3 - wave_txt.get_width(), 2))

    score_txt = FONT_SMALL.render(
        f"Score:{player.score}  Kills:{player.kills}", True, GRAY_70)
    surf.blit(score_txt, (CANVAS_W - 3 - score_txt.get_width(), 16))

    # 顶部中央：玩家世界坐标（出生点为原点）
    coord_txt = FONT_SMALL.render(
        f"({int(player.x)}, {int(player.y)})", True, GRAY_60)
    surf.blit(coord_txt, (CANVAS_W // 2 - coord_txt.get_width() // 2, 2))

    # ── 底部物品栏 ──
    _draw_inventory(surf, player)


def draw_gameover(surf, player, wave, time_alive):
    overlay = pygame.Surface((CANVAS_W, CANVAS_H))
    overlay.set_alpha(180); overlay.fill(BLACK)
    surf.blit(overlay, (0, 0))
    cx, cy = CANVAS_W // 2, CANVAS_H // 2

    title = FONT_TITLE.render("YOU DIED", True, WHITE)
    surf.blit(title, (cx - title.get_width()//2, cy - 80))

    stats_lines = [
        f"Survived: {int(time_alive)}s",
        f"Wave: {wave}",
        f"Kills: {player.kills}",
        f"Score: {player.score}",
    ]
    for i, line in enumerate(stats_lines):
        t = FONT_MEDIUM.render(line, True, GRAY_70)
        surf.blit(t, (cx - t.get_width()//2, cy - 10 + i * 30))

    restart = FONT_MEDIUM.render("Press R to Restart", True, WHITE)
    surf.blit(restart, (cx - restart.get_width()//2, cy + 120))

    if int(pygame.time.get_ticks() // 500) % 2:
        esc = FONT_SMALL.render("ESC to Quit", True, GRAY_50)
        surf.blit(esc, (cx - esc.get_width()//2, cy + 155))


def draw_pause(surf):
    overlay = pygame.Surface((CANVAS_W, CANVAS_H))
    overlay.set_alpha(150); overlay.fill(BLACK)
    surf.blit(overlay, (0, 0))
    t = FONT_LARGE.render("PAUSED", True, WHITE)
    surf.blit(t, (CANVAS_W//2 - t.get_width()//2, CANVAS_H//2 - t.get_height()//2))


# ============================================================
# 主游戏类
# ============================================================
class Game:
    SPAWN_RADIUS = 140   # 敌人生成半径（世界坐标）
    DESPAWN_RADIUS = 180  # 敌人消失半径
    ITEM_DESPAWN = 800   # 物品消失距离（远到几乎不会碰到）

    def __init__(self):
        self.map = GameMap()
        self.particles = ParticleSystem()
        self.camera = Camera()
        self.tank_bullets: List[TankBullet] = []
        self.rocket_bullets: List[RocketBullet] = []
        self.dynamites: List[DynamiteEntity] = []
        self.scatter_timer = 0.0
        self.reset()

    def reset(self):
        self.player = Player()
        self.bullets: List[Bullet] = []
        self.tank_bullets: List[TankBullet] = []
        self.rocket_bullets: List[RocketBullet] = []
        self.dynamites: List[DynamiteEntity] = []
        self.enemies: List[Enemy] = []
        self.items: List[Item] = []
        self.wave = 0
        self.enemies_to_spawn = 0
        self.spawn_timer = 0.0
        self.spawn_interval = 1.0
        self.time_alive = 0.0
        self.game_over = False
        self.paused = False
        self.shake = 0.0
        self.shake_x = 0; self.shake_y = 0
        self.camera.x = self.player.x
        self.camera.y = self.player.y
        self.scatter_timer = 0.0
        self.next_wave()
        self._scatter_items(40, 600.0)  # 初始盲盒：恢复充足数量

    def next_wave(self):
        self.wave += 1
        self.enemies_to_spawn = 12 + self.wave * 5  # 大幅增加刷怪量
        self.spawn_timer = 0.0
        self.spawn_interval = max(0.10, 0.8 - self.wave * 0.04)  # 更快刷出

    def spawn_enemy(self):
        # 在玩家周围环形区域生成敌人
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(self.SPAWN_RADIUS * 0.6, self.SPAWN_RADIUS)
        wx = self.player.x + math.cos(angle) * dist
        wy = self.player.y + math.sin(angle) * dist

        types = ["runner", "ghost", "tank"]  # 从第一波就三种怪都有
        wts = {"runner": 2, "ghost": 4, "tank": 4}  # 奔跑者:幽灵:坦克 = 2:4:4
        etype = random.choices(types, weights=[wts[t] for t in types])[0]

        self.enemies.append(Enemy(wx, wy, etype, self.wave))
        self.enemies_to_spawn -= 1

    def spawn_item(self, x, y, from_kill: bool = False):
        """from_kill=True → 回血方块；False → 盲盒（武器/弹药）"""
        it = "health" if from_kill else Item.random_mystery()
        self.items.append(Item(x, y, it))

    def _scatter_items(self, count: int, radius: float):
        """在地图上随机散落盲盒物品"""
        px, py = self.player.x, self.player.y
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(radius * 0.3, radius)
            wx = px + math.cos(angle) * dist
            wy = py + math.sin(angle) * dist
            it = Item.random_mystery()
            self.items.append(Item(wx, wy, it))

    def cleanup_offscreen(self):
        """清理远离玩家的实体"""
        px, py = self.player.x, self.player.y
        self.enemies = [e for e in self.enemies
                        if e.alive and math.hypot(e.x-px, e.y-py) < self.DESPAWN_RADIUS + 50]
        self.items = [i for i in self.items
                      if i.alive and math.hypot(i.x-px, i.y-py) < self.ITEM_DESPAWN]

    def handle_collisions(self):
        p = self.player
        # 子弹 vs 敌人
        for b in self.bullets[:]:
            if not b.alive: continue
            for e in self.enemies:
                if not e.alive: continue
                if math.hypot(b.x - e.x, b.y - e.y) < e.size + b.size:
                    b.alive = False
                    e.take_damage(b.damage)
                    e.stun_timer = 0.06
                    # 命中幽灵时短暂显形
                    if e.type == "ghost":
                        e.visible = True
                        e.reveal_timer = 1.0
                    # 命中火花：沿子弹方向锥形
                    hit_a = math.atan2(b.vy, b.vx)
                    self.particles.emit_directional(
                        b.x, b.y, hit_a+math.pi, 4, GRAY_70,
                        spread=1.0, speed=3, life=0.15)
                    if not e.alive:
                        # 烟花式外爆
                        self.particles.emit_burst_rings(
                            e.x, e.y, 25, e.color, rings=2, speed=5, life=0.55)
                        p.score += e.score; p.kills += 1
                        self.spawn_item(e.x, e.y, from_kill=True)
                    break

        self.bullets = [b for b in self.bullets if b.alive]

        # 火箭弹 vs 敌人（AOE 爆炸）
        for rb in self.rocket_bullets[:]:
            if not rb.alive: continue
            hit = False
            for e in self.enemies:
                if not e.alive: continue
                if math.hypot(rb.x - e.x, rb.y - e.y) < e.size + rb.size:
                    hit = True
                    break
            if hit or rb.life <= 0:
                rb.alive = False
                exp_x, exp_y = rb.x, rb.y
                exp_r = rb.explosion_radius
                for e in self.enemies:
                    if not e.alive: continue
                    dist = math.hypot(exp_x - e.x, exp_y - e.y)
                    if dist < exp_r + e.size:
                        dmg_ratio = max(0.3, 1.0 - dist / exp_r)
                        dmg = int(rb.damage * dmg_ratio)
                        e.take_damage(dmg)
                        e.stun_timer = 0.15
                        if e.type == "ghost":
                            e.visible = True
                            e.reveal_timer = 1.5
                        # 火箭击杀时才计入分数
                        if not e.alive:
                            p.score += e.score
                            p.kills += 1
                            self.spawn_item(e.x, e.y, from_kill=True)
                self.particles.emit_burst_rings(
                    exp_x, exp_y, 40, RED_BLOOD, rings=3, speed=6, life=0.6)
                self.particles.emit_burst_rings(
                    exp_x, exp_y, 20, WHITE, rings=2, speed=4, life=0.35)
                self.shake = max(self.shake, 0.3)
        self.rocket_bullets = [rb for rb in self.rocket_bullets if rb.alive]

        # 敌人 vs 玩家
        for e in self.enemies:
            if not e.alive: continue
            if math.hypot(e.x - p.x, e.y - p.y) < e.size + p.SIZE:
                # 幽灵攻击时强制显形
                if e.type == "ghost":
                    e.visible = True
                    e.reveal_timer = 2.0
                p.take_damage(e.damage)
                dx = p.x - e.x; dy = p.y - e.y
                dist = max(1, math.hypot(dx, dy))
                p.x += (dx / dist) * 6; p.y += (dy / dist) * 6
                self.shake = 0.2
                # 受伤血液：沿受伤方向烟花散射
                blood_a = math.atan2(p.y-e.y, p.x-e.x)
                self.particles.emit_directional(
                    p.x, p.y, blood_a, 14, RED_BLOOD,
                    spread=1.0, speed=3.5, life=0.35)
                break

        # 坦克子弹 vs 玩家
        for tb in self.tank_bullets:
            if not tb.alive: continue
            if math.hypot(tb.x - p.x, tb.y - p.y) < p.SIZE + tb.size:
                p.take_damage(tb.damage)
                tb.alive = False
                self.particles.emit_directional(
                    tb.x, tb.y, math.atan2(tb.vy, tb.vx), 5, GRAY_60,
                    spread=0.8, speed=2, life=0.2)
                break
        self.tank_bullets = [tb for tb in self.tank_bullets if tb.alive]

        # 玩家 vs 物品
        for it in self.items[:]:
            if not it.alive: continue
            if math.hypot(it.x - p.x, it.y - p.y) < p.SIZE + 6:
                self._pickup(it)
                self.items.remove(it)

    def _pickup(self, it: Item):
        p = self.player
        t = it.type
        if t == "health":
            p.health = min(p.max_health, p.health + 30)
            self.particles.emit(it.x, it.y, 8, GRAY_70, speed=2.5, life=0.4)
        elif t == "ammo_pistol":
            p.ammo[WeaponType.PISTOL] += 10
        elif t == "ammo_shotgun":
            p.ammo[WeaponType.SHOTGUN] += 8
        elif t == "ammo_rifle":
            p.ammo[WeaponType.RIFLE] += 15
        elif t == "weapon_shotgun":
            p.add_weapon(WeaponType.SHOTGUN)
            p.ammo[WeaponType.SHOTGUN] += 10
            p.score += 50
        elif t == "weapon_rifle":
            p.add_weapon(WeaponType.RIFLE)
            p.ammo[WeaponType.RIFLE] += 20
            p.score += 50
        elif t == "rocket":
            p.add_weapon(WeaponType.ROCKET)
            p.ammo[WeaponType.ROCKET] += 1
            p.score += 25
        elif t == "dynamite":
            p.add_weapon(WeaponType.DYNAMITE)
            p.ammo[WeaponType.DYNAMITE] += 1
            p.score += 25
        self.particles.emit(it.x, it.y, 6, GRAY_70, speed=1.5, life=0.4)
        snd_pickup.play()

    def update(self, dt, keys, mouse_world, shooting):
        if self.game_over: return

        p = self.player
        p.update(dt, keys, mouse_world[0], mouse_world[1])

        # 射击
        if shooting and p.alive:
            w = p.current_weapon
            if w == WeaponType.DYNAMITE:
                # 炸药：放置在脚下，1秒引爆
                if p.cooldown <= 0 and p.ammo[w] > 0:
                    ws = WEAPON_STATS[w]
                    p.cooldown = ws["fire_rate"]
                    p.ammo[w] -= 1
                    self.dynamites.append(DynamiteEntity(p.x, p.y))
                    self.particles.emit(p.x, p.y, 8, RED_BLOOD, speed=2, life=0.3)
                    self.shake = max(self.shake, 0.02)
                    snd_shoot.play()
                    if p.ammo[w] <= 0:
                        p.current_weapon = WeaponType.PISTOL
                        p.weapons = [wp for wp in p.weapons if wp != WeaponType.DYNAMITE]
            elif w == WeaponType.ROCKET:
                # 火箭筒：发射火箭弹
                if p.cooldown <= 0 and p.ammo[w] > 0:
                    ws = WEAPON_STATS[w]
                    p.cooldown = ws["fire_rate"]
                    p.ammo[w] -= 1
                    gun_len, _, _ = p.GUN_PARAMS.get(w, p.GUN_PARAMS[0])
                    muzzle = p.SIZE + gun_len
                    mx = p.x + math.cos(p.aim_angle) * muzzle
                    my = p.y + math.sin(p.aim_angle) * muzzle
                    self.rocket_bullets.append(RocketBullet(mx, my, p.aim_angle))
                    self.particles.emit_directional(
                        mx, my, p.aim_angle + math.pi, 10, RED_BLOOD,
                        spread=0.8, speed=4, life=0.2)
                    self.shake = max(self.shake, 0.08)
                    snd_shoot.play()
                    # 火箭用完自动切回手枪
                    if p.ammo[w] <= 0:
                        p.current_weapon = WeaponType.PISTOL
                        p.weapons = [wp for wp in p.weapons if wp != WeaponType.ROCKET]
            else:
                new_b = p.shoot()
                if new_b:
                    self.bullets.extend(new_b)
                    gun_len, _, _ = p.GUN_PARAMS.get(
                        p.current_weapon, p.GUN_PARAMS[0])
                    muzzle = p.SIZE + gun_len
                    mx = p.x + math.cos(p.aim_angle) * muzzle
                    my = p.y + math.sin(p.aim_angle) * muzzle
                    # 枪口锥形闪光
                    self.particles.emit_directional(
                        mx, my, p.aim_angle, 5, WHITE,
                        spread=0.4, speed=3, life=0.08)
                    self.shake = max(self.shake, 0.04)
                    snd_shoot.play()

        # 更新子弹
        for b in self.bullets: b.update(dt)
        self.bullets = [b for b in self.bullets if b.alive]

        # 更新敌人 + 收集坦克子弹和枪口闪光
        for e in self.enemies:
            _, _, tb, mz = e.update(dt, p.x, p.y)
            if tb:
                self.tank_bullets.append(tb)
            if mz:  # 坦克枪口闪光
                self.particles.emit_directional(
                    mz[0], mz[1], mz[2], 5, GRAY_60,
                    spread=0.5, speed=2.5, life=0.12)
            # 奔跑者高速移动拖尾
            if e.type == "runner" and e.alive:
                self.particles.emit(e.x, e.y, 1, GRAY_70, speed=0.3, life=0.15)
        self.enemies = [e for e in self.enemies if e.alive]

        # ── 敌人互斥（禁止重合）──
        for i, a in enumerate(self.enemies):
            if not a.alive: continue
            for j in range(i + 1, len(self.enemies)):
                b = self.enemies[j]
                if not b.alive: continue
                min_dist = a.size + b.size + 1
                dx = a.x - b.x
                dy = a.y - b.y
                dist = math.hypot(dx, dy)
                if dist < min_dist and dist > 0.01:
                    overlap = min_dist - dist
                    ndx = dx / dist
                    ndy = dy / dist
                    a.x += ndx * overlap * 0.5
                    a.y += ndy * overlap * 0.5
                    b.x -= ndx * overlap * 0.5
                    b.y -= ndy * overlap * 0.5

        # 更新炸药
        for dy in self.dynamites: dy.update(dt)
        for dy in self.dynamites[:]:
            if not dy.alive:
                # 引爆！
                exp_x, exp_y = dy.x, dy.y
                exp_r = dy.explosion_radius
                for e in self.enemies:
                    if not e.alive: continue
                    dist = math.hypot(exp_x - e.x, exp_y - e.y)
                    if dist < exp_r + e.size:
                        dmg_ratio = max(0.3, 1.0 - dist / exp_r)
                        dmg = int(dy.damage * dmg_ratio)
                        e.take_damage(dmg)
                        e.stun_timer = 0.2
                        if e.type == "ghost":
                            e.visible = True
                            e.reveal_timer = 2.0
                        if not e.alive:
                            p.score += e.score
                            p.kills += 1
                            self.spawn_item(e.x, e.y, from_kill=True)
                # 极具冲击力的爆炸粒子
                self.particles.emit_burst_rings(exp_x, exp_y, 60, RED_BLOOD, rings=4, speed=8, life=0.7)
                self.particles.emit_burst_rings(exp_x, exp_y, 35, WHITE, rings=3, speed=5, life=0.4)
                self.particles.emit_burst(exp_x, exp_y, 25, (255, 120, 50), speed=6, life=0.5)
                # 冲击波粒子环
                for i in range(16):
                    a = (2 * math.pi) * i / 16
                    self.particles.particles.append(Particle(exp_x, exp_y, math.cos(a)*6, math.sin(a)*6, 0.5, WHITE, 3, 0))
                self.shake = max(self.shake, 0.5)
                # 清理死亡敌人
                self.enemies = [e for e in self.enemies if e.alive]
        self.dynamites = [dy for dy in self.dynamites if dy.alive]

        # 更新火箭弹
        for rb in self.rocket_bullets: rb.update(dt)
        self.rocket_bullets = [rb for rb in self.rocket_bullets if rb.alive]

        # 更新坦克子弹
        for tb in self.tank_bullets: tb.update(dt)
        self.tank_bullets = [tb for tb in self.tank_bullets if tb.alive]

        # 更新物品
        for it in self.items: it.update(dt)
        self.items = [i for i in self.items if i.alive]

        # 碰撞
        self.handle_collisions()

        # 生成敌人
        if self.enemies_to_spawn > 0:
            self.spawn_timer += dt
            while self.spawn_timer >= self.spawn_interval and self.enemies_to_spawn > 0:
                self.spawn_timer -= self.spawn_interval
                self.spawn_enemy()

        # 定期补充散落盲盒
        self.scatter_timer += dt
        if self.scatter_timer > 10.0:
            self.scatter_timer -= 10.0
            nearby = sum(1 for it in self.items
                         if it.alive and math.hypot(it.x - p.x, it.y - p.y) < 400)
            if nearby < 15:
                self._scatter_items(8, 500.0)

        self.time_alive += dt

        # 新波次
        if self.enemies_to_spawn <= 0 and len(self.enemies) == 0:
            self.next_wave()
            p.score += self.wave * 20
            for _ in range(2):
                self.spawn_item(p.x + random.uniform(-60, 60),
                                p.y + random.uniform(-60, 60))

        # 清理离屏实体
        if self.time_alive - int(self.time_alive) < dt:
            self.cleanup_offscreen()

        # 相机平滑跟随
        self.camera.follow(p.x, p.y)

        # 屏幕震动
        if self.shake > 0:
            self.shake -= dt
            self.shake_x = random.randint(-2, 2)
            self.shake_y = random.randint(-2, 2)
        else:
            self.shake_x = self.shake_y = 0

        # 粒子
        self.particles.update(dt)

        if not p.alive:
            self.game_over = True
            # 玩家死亡：双层烟花环
            self.particles.emit_burst_rings(p.x, p.y, 45, RED_BLOOD, rings=3, speed=5.5, life=0.7)
            self.particles.emit_burst_rings(p.x, p.y, 25, WHITE, rings=2, speed=3, life=0.45)
            snd_death.play()

    def draw(self):
        self.map.draw(pixel_canvas, self.camera)

        for it in self.items: it.draw(pixel_canvas, self.camera)
        for e in self.enemies: e.draw(pixel_canvas, self.camera)
        for b in self.bullets: b.draw(pixel_canvas, self.camera)
        for rb in self.rocket_bullets: rb.draw(pixel_canvas, self.camera)
        for dy in self.dynamites: dy.draw(pixel_canvas, self.camera)
        for tb in self.tank_bullets: tb.draw(pixel_canvas, self.camera)
        self.player.draw(pixel_canvas, self.camera)
        self.particles.draw(pixel_canvas, self.camera)

        enemies_left = self.enemies_to_spawn + len(self.enemies)
        draw_hud(pixel_canvas, self.player, self.wave, enemies_left, self.time_alive)

        if self.game_over:
            draw_gameover(pixel_canvas, self.player, self.wave, self.time_alive)
        elif self.paused:
            draw_pause(pixel_canvas)

        scaled = pygame.transform.scale(pixel_canvas, (SCREEN_WIDTH, SCREEN_HEIGHT))
        screen.blit(scaled, (self.shake_x, self.shake_y))
        # 注意：flip 由 main 循环统一调用（触屏模式下要在 flip 前叠加摇杆 UI）


# ============================================================
# 主循环
# ============================================================
class _FakeKeys:
    """模拟 pygame.key.get_pressed() 返回的键位字典，
    用于把摇杆方向向量"翻译"成 WASD 按键 — 让 Player.update 不用改"""
    def __init__(self):
        self._pressed = set()
    def __getitem__(self, key):
        return key in self._pressed
    def set(self, key, val: bool):
        if val:
            self._pressed.add(key)
        else:
            self._pressed.discard(key)


def main():
    game = Game()
    clock = pygame.time.Clock()
    running = True

    # 触屏模式：F11 切换；手机上默认开启
    is_android = hasattr(sys, 'getandroidapilevel')
    touch_mode = is_android
    touch_input = TouchInputManager()
    fake_keys = _FakeKeys()

    while running:
        dt = min(clock.tick(FPS) / 1000.0, 0.1)

        if not touch_mode:
            shooting = pygame.mouse.get_pressed()[0]

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            # ─── 触屏模式事件 ───
            elif touch_mode and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # PC 模拟模式：鼠标按下
                x, y = event.pos
                touch_input.handle_mouse_down(x, y)
            elif touch_mode and event.type == pygame.MOUSEMOTION:
                if event.buttons[0]:  # 左键按住
                    x, y = event.pos
                    touch_input.handle_mouse_move(x, y)
            elif touch_mode and event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                x, y = event.pos
                touch_input.handle_mouse_up(x, y)
            elif touch_mode and event.type == pygame.FINGERDOWN:
                x = int(event.x * SCREEN_WIDTH)
                y = int(event.y * SCREEN_HEIGHT)
                touch_input.handle_finger_down(x, y, event.finger_id)
            elif touch_mode and event.type == pygame.FINGERMOTION:
                x = int(event.x * SCREEN_WIDTH)
                y = int(event.y * SCREEN_HEIGHT)
                touch_input.handle_finger_move(x, y, event.finger_id)
            elif touch_mode and event.type == pygame.FINGERUP:
                x = int(event.x * SCREEN_WIDTH)
                y = int(event.y * SCREEN_HEIGHT)
                touch_input.handle_finger_up(x, y, event.finger_id)

            # ─── 键盘事件（两种模式通用）───
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    touch_mode = not touch_mode
                elif event.key == pygame.K_ESCAPE:
                    if game.game_over: running = False
                    else: game.paused = not game.paused
                elif event.key == pygame.K_r and game.game_over:
                    game.reset()
                elif event.key == pygame.K_q and not game.game_over and not game.paused:
                    game.player.switch_weapon()
                elif event.key == pygame.K_SPACE and game.game_over:
                    game.reset()
                # 数字键 1-5 直接选择武器
                elif not game.game_over and not game.paused:
                    key_slot_map = {
                        pygame.K_1: WeaponType.PISTOL,
                        pygame.K_2: WeaponType.SHOTGUN,
                        pygame.K_3: WeaponType.RIFLE,
                        pygame.K_4: WeaponType.ROCKET,
                        pygame.K_5: WeaponType.DYNAMITE,
                    }
                    if event.key in key_slot_map:
                        game.player.select_weapon(key_slot_map[event.key])

            # ─── PC 模式的鼠标点击（物品栏）───
            elif not touch_mode and event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1 and not game.game_over and not game.paused:
                    mx, my = pygame.mouse.get_pos()
                    clicked = get_clicked_slot(mx, my)
                    if clicked >= 0:
                        game.player.select_weapon(clicked)

        # ═══════════════════════════════════════
        # 根据模式构造 game.update 的输入
        # ═══════════════════════════════════════
        if touch_mode:
            # 触屏模式：摇杆 → 假键盘 + 虚拟鼠标位置
            move_dx, move_dy = touch_input.move_vector()
            fake_keys.set(pygame.K_w, move_dy < -0.3)
            fake_keys.set(pygame.K_s, move_dy > 0.3)
            fake_keys.set(pygame.K_a, move_dx < -0.3)
            fake_keys.set(pygame.K_d, move_dx > 0.3)

            # 瞄准：摇杆方向 → 玩家前方的虚拟鼠标点
            aim = touch_input.aim_vector()
            if aim is not None:
                # 把摇杆方向转换成"玩家前方 200 像素的世界坐标"
                mouse_world_x = game.player.x + aim[0] * 200
                mouse_world_y = game.player.y + aim[1] * 200
            else:
                # 没推瞄准摇杆：保持上次的瞄准角度（用 aim_angle 反推一个远点）
                mouse_world_x = game.player.x + math.cos(game.player.aim_angle) * 200
                mouse_world_y = game.player.y + math.sin(game.player.aim_angle) * 200

            shooting = touch_input.is_shooting()
            keys = fake_keys

            # 触屏的"点击"事件 → 处理 UI 交互
            tap = touch_input.consume_tap()
            if tap is not None:
                tx, ty = tap
                if game.game_over:
                    game.reset()
                elif not game.paused:
                    clicked = get_clicked_slot(tx, ty)
                    if clicked >= 0:
                        game.player.select_weapon(clicked)

            if touch_input.consume_pause_tap():
                if game.game_over:
                    running = False
                else:
                    game.paused = not game.paused
        else:
            # 键盘鼠标模式：原有逻辑
            mx, my = pygame.mouse.get_pos()
            mouse_world_x = mx // PIXEL_SCALE + game.camera.x - CANVAS_W // 2
            mouse_world_y = my // PIXEL_SCALE + game.camera.y - CANVAS_H // 2
            keys = pygame.key.get_pressed()

        if not game.paused or game.game_over:
            game.update(dt, keys, (mouse_world_x, mouse_world_y), shooting)
        game.draw()

        # 触屏模式：在 screen 上叠加摇杆 UI（像素画布已缩放到 screen）
        if touch_mode:
            touch_input.draw(screen)
            # 触屏模式下显示一个提示文字（PC 模拟用）
            if not is_android:
                hint = pygame.font.Font(None, 20).render(
                    "F11: toggle touch mode", True, GRAY_50)
                screen.blit(hint, (10, SCREEN_HEIGHT - 25))

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
