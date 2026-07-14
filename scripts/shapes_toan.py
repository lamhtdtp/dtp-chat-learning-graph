"""Vật thể 3D minh hoạ cho từng khái niệm Toán 6 — render nền TRONG SUỐT (.mov)
để pipeline video overlay vào góc bảng (app/video/animate.py).

Render (local, cần manim + ffmpeg):
    manim --transparent -qm scripts/shapes_toan.py \
        PrimeCubes CountCubes PowerCubes SetSpheres NumberLine \
        FractionBar TriShape BoxPrism AngleRays
Xuất media/videos/shapes_toan/720p30/<Class>.mov -> đổi tên + bỏ vào
app/video/assets/shapes3d/<key>.mov (xem SHAPE_KEY bên dưới).
"""
from manim import *

BLUE_N = "#4FC3F7"; GREEN_P = "#66BB6A"; ORANGE_C = "#FFB74D"
YELLOW_D = "#FFD54F"; GREY = "#B4B2A9"; WHITE_T = "#ECEFF4"
config.movie_file_extension = ".mov"

# key file -> các slug khái niệm dùng chung (map trong app/video/shapes.py)
SHAPE_KEY = {
    "prime_cubes": ["so_nguyen_to"],
    "count_cubes": ["uoc_va_boi", "uoc_chung_lon_nhat", "boi_chung_nho_nhat", "dau_hieu_chia_het"],
    "power_cubes": ["luy_thua"],
    "set_spheres": ["tap_hop"],
    "number_line": ["so_nguyen_am", "so_thap_phan", "doan_thang_trung_diem"],
    "fraction_bar": ["phan_so", "ti_so_phan_tram"],
    "tri_shape": ["tam_giac_deu"],
    "box_prism": ["chu_vi_dien_tich"],
    "angle_rays": ["goc"],
}


class _Base(ThreeDScene):
    secs = 6.0

    def build(self):
        raise NotImplementedError

    def construct(self):
        self.set_camera_orientation(phi=64 * DEGREES, theta=-48 * DEGREES)
        g = self.build().move_to(ORIGIN)
        # FadeIn (giữ NGUYÊN kích thước) thay vì GrowFromCenter -> mọi frame full
        # size, overlay không bị nhỏ khi loop.
        self.add(g)
        self.begin_ambient_camera_rotation(rate=0.22)
        self.wait(self.secs)


def _cube(color, s=0.7):
    return Cube(side_length=s, fill_opacity=0.95, fill_color=color, stroke_width=1)


class PrimeCubes(_Base):
    def build(self):
        return VGroup(*[_cube(GREEN_P) for _ in range(7)]).arrange(RIGHT, buff=0.12)


class CountCubes(_Base):
    def build(self):
        return VGroup(*[_cube(BLUE_N) for _ in range(6)]).arrange(RIGHT, buff=0.12)


class PowerCubes(_Base):
    def build(self):
        return VGroup(*[_cube(ORANGE_C) for _ in range(8)]).arrange_in_grid(rows=2, cols=4, buff=0.1)


class SetSpheres(_Base):
    def build(self):
        return VGroup(*[Sphere(radius=0.38, resolution=(16, 16)).set_color(BLUE_N)
                        for _ in range(5)]).arrange_in_grid(rows=2, cols=3, buff=0.25)


class NumberLine(_Base):
    def build(self):
        axis = Prism(dimensions=[5.4, 0.12, 0.12]).set_color(WHITE_T)
        dots = VGroup(*[Sphere(radius=0.22, resolution=(14, 14)).set_color(YELLOW_D)
                        for _ in range(5)]).arrange(RIGHT, buff=0.9)
        dots.move_to(axis.get_center())
        return VGroup(axis, dots)


class FractionBar(_Base):
    def build(self):
        parts = []
        for i in range(5):
            c = GREEN_P if i < 2 else GREY          # 2/5 tô đậm
            parts.append(Prism(dimensions=[0.85, 1.25, 0.4]).set_fill(c, 0.95).set_stroke(WHITE_T, 1))
        return VGroup(*parts).arrange(RIGHT, buff=0.06)


class TriShape(_Base):
    def build(self):
        # tam giác đều bằng khối cầu (1+2+3) — nhìn ra tam giác khi xoay
        rows = [1, 2, 3]
        g = VGroup()
        for r, n in enumerate(rows):
            row = VGroup(*[Sphere(radius=0.3, resolution=(14, 14)).set_color(GREEN_P)
                           for _ in range(n)]).arrange(RIGHT, buff=0.25)
            row.shift(UP * (1 - r) * 0.75)
            g.add(row)
        return g


class BoxPrism(_Base):
    def build(self):
        return VGroup(Prism(dimensions=[2.6, 1.6, 1.2]).set_fill(ORANGE_C, 0.9).set_stroke(WHITE_T, 1.5))


class AngleRays(_Base):
    def build(self):
        o = ORIGIN
        r1 = Line3D(o, np.array([2.4, 0, 0]), color=BLUE_N, thickness=0.03)
        r2 = Line3D(o, np.array([1.7, 1.7, 0]), color=BLUE_N, thickness=0.03)
        arc = Arc(radius=0.7, start_angle=0, angle=45 * DEGREES, color=YELLOW_D, stroke_width=6)
        return VGroup(r1, r2, arc)
