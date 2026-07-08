"""氏名・学籍番号の手書き画像を一覧表にした確認用シートを生成する。

チャット型AIに「この画像を見て書き起こして」と渡すための一覧画像。
1バッチ分をまとめて1枚にすると人数が多い場合に縦長になりすぎて縮小時に
手書き文字が潰れるため、per_page 人ごとに複数ページのPNGへ分割する
（呼び出し側でZIPにまとめてダウンロードさせる想定）。
"""

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX
PAD_H = 20
PAD_V = 14
HEADER_H = 60
SEQ_COL_W = 110
DEFAULT_PER_PAGE = 20

_DEFAULT_NAME_SIZE = (1200, 160)
_DEFAULT_ID_SIZE = (900, 120)


def build_pages(rows, per_page=DEFAULT_PER_PAGE):
    """rows: [{"seq": int, "name_image": grayscale ndarray|None, "id_image": ...|None}, ...]
    戻り値: 1ページ分ずつのPNGバイト列のリスト。"""
    name_w, name_h = _max_size([r["name_image"] for r in rows], _DEFAULT_NAME_SIZE)
    id_w, id_h = _max_size([r["id_image"] for r in rows], _DEFAULT_ID_SIZE)

    pages = []
    for i in range(0, len(rows), per_page):
        chunk = rows[i:i + per_page]
        pages.append(_render_page(chunk, name_w, name_h, id_w, id_h))
    return pages


def _max_size(images, default):
    sizes = [(img.shape[1], img.shape[0]) for img in images if img is not None]
    if not sizes:
        return default
    return max(w for w, h in sizes), max(h for w, h in sizes)


def _render_page(chunk, name_w, name_h, id_w, id_h):
    name_col_w = name_w + 2 * PAD_H
    id_col_w = id_w + 2 * PAD_H
    row_h = max(name_h, id_h) + 2 * PAD_V
    total_w = SEQ_COL_W + name_col_w + id_col_w
    total_h = HEADER_H + row_h * len(chunk)

    canvas = np.full((total_h, total_w), 255, dtype=np.uint8)

    cv2.putText(canvas, "No.", (12, 42), FONT, 1.0, 0, 2, cv2.LINE_AA)
    cv2.putText(canvas, "Name (handwritten)", (SEQ_COL_W + 12, 42), FONT, 1.0, 0, 2, cv2.LINE_AA)
    cv2.putText(canvas, "Student ID (handwritten)", (SEQ_COL_W + name_col_w + 12, 42), FONT, 1.0, 0, 2, cv2.LINE_AA)
    cv2.line(canvas, (0, HEADER_H), (total_w, HEADER_H), 0, 2)
    cv2.line(canvas, (SEQ_COL_W, 0), (SEQ_COL_W, total_h), 0, 1)
    cv2.line(canvas, (SEQ_COL_W + name_col_w, 0), (SEQ_COL_W + name_col_w, total_h), 0, 1)

    for i, row in enumerate(chunk):
        y0 = HEADER_H + i * row_h
        y1 = y0 + row_h
        cv2.line(canvas, (0, y1), (total_w, y1), 0, 1)

        seq_text = f"#{row['seq']}"
        (_, th), _ = cv2.getTextSize(seq_text, FONT, 1.0, 2)
        cv2.putText(canvas, seq_text, (12, y0 + row_h // 2 + th // 2), FONT, 1.0, 0, 2, cv2.LINE_AA)

        _paste_or_placeholder(canvas, row["name_image"], SEQ_COL_W, y0, name_col_w, row_h)
        _paste_or_placeholder(canvas, row["id_image"], SEQ_COL_W + name_col_w, y0, id_col_w, row_h)

    return cv2.imencode(".png", canvas)[1].tobytes()


def _paste_or_placeholder(canvas, img, col_x, row_y, col_w, row_h):
    if img is not None:
        h, w = img.shape
        x = col_x + max(0, (col_w - w) // 2)
        y = row_y + max(0, (row_h - h) // 2)
        canvas[y:y + h, x:x + w] = img
    else:
        text = "(no image)"
        (tw, th), _ = cv2.getTextSize(text, FONT, 0.8, 2)
        cx = col_x + 20
        cy = row_y + row_h // 2
        cv2.putText(canvas, text, (cx, cy + th // 2), FONT, 0.8, 150, 2, cv2.LINE_AA)
