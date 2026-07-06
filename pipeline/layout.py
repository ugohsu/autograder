"""解答用紙の座標定義（mm 単位、ページ左上原点・右下方向が正）。

answersheet/sheet.tex の TikZ 座標と1対1で対応する。sheet.tex 側の数値を
変更した場合は、この対応する数値も必ず合わせて変更すること
（座標のズレはそのまま採点ミスに直結するため、両者は常に同期させる）。
"""

PAGE_W_MM = 210.0
PAGE_H_MM = 297.0

# ---------- 位置合わせマーク（四隅・8mm角） ----------
REG_MARK_SIZE_MM = 8.0
REG_MARK_CORNERS_MM = [
    (10.0, 10.0),   # top-left
    (192.0, 10.0),  # top-right
    (10.0, 279.0),  # bottom-left
    (192.0, 279.0), # bottom-right
]


def reg_mark_centers_mm():
    half = REG_MARK_SIZE_MM / 2
    return [(x + half, y + half) for x, y in REG_MARK_CORNERS_MM]


# ---------- 学籍番号欄（10桁 × 値0-9） ----------
N_ID_DIGITS = 10
N_ID_VALUES = 10
ID_DIGIT_X0_MM = 63.0
ID_DIGIT_PITCH_MM = 8.5
ID_BOX_Y_MM = 64.0
ID_BOX_W_MM = 7.0
ID_BOX_H_MM = 9.0
ID_GRID_Y0_MM = 76.0
ID_GRID_ROW_PITCH_MM = 5.0
ID_BUBBLE_RADIUS_MM = 2.0


def id_box_rect_mm(dig):
    """dig: 0-9 (桁位置、左から). 手書き記入ボックスの (x, y, w, h)。"""
    x = ID_DIGIT_X0_MM + dig * ID_DIGIT_PITCH_MM
    return (x, ID_BOX_Y_MM, ID_BOX_W_MM, ID_BOX_H_MM)


def id_bubble_center_mm(dig, val):
    """dig: 0-9 (桁位置), val: 0-9 (マークする数字)."""
    x = ID_DIGIT_X0_MM + dig * ID_DIGIT_PITCH_MM + ID_BOX_W_MM / 2
    y = ID_GRID_Y0_MM + val * ID_GRID_ROW_PITCH_MM + ID_GRID_ROW_PITCH_MM / 2
    return (x, y)


# 学籍番号・手書き記入欄10桁ぶんの外接矩形（Web UIでの確認用画像切り出しに使う）
ID_HANDWRITTEN_ROW_RECT_MM = (
    ID_DIGIT_X0_MM,
    ID_BOX_Y_MM,
    (N_ID_DIGITS - 1) * ID_DIGIT_PITCH_MM + ID_BOX_W_MM,
    ID_BOX_H_MM,
)

# 氏名欄（手書きのみ）の矩形。sheet.tex の \draw ($(O)+(32,37)$) rectangle ($(O)+(200,51)$) に対応
NAME_BOX_RECT_MM = (32.0, 37.0, 168.0, 14.0)


# ---------- 解答エリア（4列 × 20行 × 5択 = 80問） ----------
N_COLS = 4
N_ROWS = 20
N_OPTS = 5
COL_X0_MM = 14.0
COL_PITCH_MM = 46.5
ROW_Y0_MM = 141.4
ROW_PITCH_MM = 6.8
OPT_X_OFFSET_MM = 8.0 + 3.25  # 列の左端からバブル1個目中心までのオフセット
OPT_PITCH_MM = 6.5
ANSWER_BUBBLE_RADIUS_MM = 2.25


def question_number(col, row):
    """col: 0-3, row: 0-19 -> 設問番号 1-80。"""
    return col * N_ROWS + row + 1


def answer_bubble_center_mm(col, row, opt):
    """col: 0-3, row: 0-19, opt: 0-4 (①-⑤)."""
    x0 = COL_X0_MM + col * COL_PITCH_MM
    x = x0 + OPT_X_OFFSET_MM + opt * OPT_PITCH_MM
    y = ROW_Y0_MM + row * ROW_PITCH_MM
    return (x, y)


def answer_row_rect_mm(col, row):
    """該当設問の①〜⑤バブルをまとめて囲む矩形 (x, y, w, h)。実スキャン画像の
    切り出し表示（採点者による目視確認）に使う。"""
    x_first, y = answer_bubble_center_mm(col, row, 0)
    x_last, _ = answer_bubble_center_mm(col, row, N_OPTS - 1)
    r = ANSWER_BUBBLE_RADIUS_MM
    return (x_first - r, y - r, (x_last - x_first) + 2 * r, 2 * r)


def iter_answer_bubbles():
    """(qnum, col, row, opt, (x_mm, y_mm)) を全80問×5択ぶん列挙する。"""
    for col in range(N_COLS):
        for row in range(N_ROWS):
            qnum = question_number(col, row)
            for opt in range(N_OPTS):
                yield qnum, col, row, opt, answer_bubble_center_mm(col, row, opt)


def iter_id_bubbles():
    """(dig, val, (x_mm, y_mm)) を学籍番号10桁×0-9ぶん列挙する。"""
    for dig in range(N_ID_DIGITS):
        for val in range(N_ID_VALUES):
            yield dig, val, id_bubble_center_mm(dig, val)
