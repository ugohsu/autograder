"""フェーズ3: 画像前処理・座標抽出。

スキャン画像（またはスキャン後の PDF）を受け取り、
1. グレースケール化・二値化
2. 四隅レジストレーションマークの検出
3. マークを用いた射影変換で正規化（傾き・ズレ補正）
4. layout.py の座標に基づく各マーク欄の切り出し・塗りつぶし判定

まで行う。座標の定義そのものは layout.py 側にあり、ここでは扱わない。
"""

import cv2
import fitz
import numpy as np

from pipeline import layout

MM_PER_INCH = 25.4

DEFAULT_DPI = 300

# 塗りつぶし判定のしきい値。実スキャン（鉛筆マーク・300dpi）で較正した値:
# 未マークのバブル（印刷された円周のみ）でも fill_ratio は 0.11〜0.17 程度になる
# （印刷線自体が黒画素として拾われるため）。実際にマークされたバブルは 0.38〜0.50 程度まで
# 跳ね上がるため、間を取って 0.25 に設定。ボールペン等インクが変わる場合は要再較正。
DARK_PIXEL_THRESHOLD = 200  # グレースケール値がこれ未満の画素を「黒」とみなす（鉛筆の淡いグレー対応）
MARK_THRESHOLD = 0.25  # この割合以上黒画素があれば「塗りつぶされている」とみなす

# 未マークのバブルの fill_ratio は通常 0.11〜0.17程度（上のコメント参照）。しきい値
# 0.25 には届かないが 0.18 を超える場合、薄い鉛筆・部分的な塗りなど「実際にマークされて
# いるが検出しきい値をわずかに下回った」可能性があるため、複数マーク時と同様に要確認
# （is_ambiguous）扱いにする。無回答なのに無条件に確定させてしまう false negative 対策。
NEAR_MISS_THRESHOLD = 0.18


def mm_to_px(mm, dpi):
    return mm / MM_PER_INCH * dpi


def _pixmap_to_bgr(pix):
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        return cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def render_pdf_page(pdf_path, dpi=DEFAULT_DPI, page_index=0):
    """PDF の1ページを OpenCV (BGR) 画像として読み込む。"""
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    pix = page.get_pixmap(dpi=dpi)
    return _pixmap_to_bgr(pix)


def render_pdf_all_pages(pdf_path, dpi=DEFAULT_DPI):
    """PDF の全ページを OpenCV (BGR) 画像のリストとして読み込む（1ページ=1学生の一括スキャン用）。"""
    doc = fitz.open(pdf_path)
    return [_pixmap_to_bgr(doc[i].get_pixmap(dpi=dpi)) for i in range(len(doc))]


def to_gray(img_bgr):
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


def binarize_otsu(gray):
    """大津の二値化。戻り値は (しきい値, 二値画像[0/255, マーク側=255])。"""
    thresh_val, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return thresh_val, bw


def _largest_square_contour_center(bw_window):
    contours, _ = cv2.findContours(bw_window, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    M = cv2.moments(largest)
    if M["m00"] == 0:
        return None
    cx = M["m10"] / M["m00"]
    cy = M["m01"] / M["m00"]
    return cx, cy


def find_registration_marks(gray, dpi, search_margin_mm=20.0):
    """四隅のレジストレーションマークをそれぞれの想定位置付近で探索する。

    戻り値: layout.REG_MARK_CORNERS_MM と同じ順番（TL, TR, BL, BR）の
    検出中心座標 [(x_px, y_px), ...]。見つからない角があれば None が入る。
    """
    h, w = gray.shape[:2]
    margin_px = mm_to_px(search_margin_mm, dpi)
    half_mark_px = mm_to_px(layout.REG_MARK_SIZE_MM, dpi) / 2

    centers = []
    for cx_mm, cy_mm in layout.reg_mark_centers_mm():
        cx_px = mm_to_px(cx_mm, dpi)
        cy_px = mm_to_px(cy_mm, dpi)

        x0 = max(0, int(cx_px - half_mark_px - margin_px))
        x1 = min(w, int(cx_px + half_mark_px + margin_px))
        y0 = max(0, int(cy_px - half_mark_px - margin_px))
        y1 = min(h, int(cy_px + half_mark_px + margin_px))

        window = gray[y0:y1, x0:x1]
        _, bw_window = binarize_otsu(window)
        found = _largest_square_contour_center(bw_window)
        if found is None:
            centers.append(None)
            continue
        lx, ly = found
        centers.append((x0 + lx, y0 + ly))
    return centers


def compute_homography(detected_px, canonical_dpi):
    """検出済みの四隅マーク中心(px) から、canonical_dpi に正規化する射影行列を求める。

    戻り値: (M, (out_w_px, out_h_px))
    """
    if any(c is None for c in detected_px):
        missing = [i for i, c in enumerate(detected_px) if c is None]
        raise ValueError(f"レジストレーションマークが検出できません: index={missing}")

    src = np.float32(detected_px)
    dst = np.float32([
        (mm_to_px(x, canonical_dpi), mm_to_px(y, canonical_dpi))
        for x, y in layout.reg_mark_centers_mm()
    ])
    M = cv2.getPerspectiveTransform(src, dst)
    out_w = int(round(mm_to_px(layout.PAGE_W_MM, canonical_dpi)))
    out_h = int(round(mm_to_px(layout.PAGE_H_MM, canonical_dpi)))
    return M, (out_w, out_h)


def warp_to_canonical(gray, M, size_px):
    return cv2.warpPerspective(gray, M, size_px, flags=cv2.INTER_LINEAR, borderValue=255)


def normalize(gray, dpi, canonical_dpi=DEFAULT_DPI, search_margin_mm=20.0):
    """レジストレーションマーク検出 → 射影変換までを行うヘルパー。"""
    detected = find_registration_marks(gray, dpi, search_margin_mm=search_margin_mm)
    M, size_px = compute_homography(detected, canonical_dpi)
    return warp_to_canonical(gray, M, size_px)


def bubble_fill_ratio(canonical_gray, center_mm, radius_mm, dpi, thresh=DARK_PIXEL_THRESHOLD, margin_factor=1.3):
    """center_mm を中心とする正方形領域を切り出し、閾値未満(黒)画素の割合を返す。"""
    cx = mm_to_px(center_mm[0], dpi)
    cy = mm_to_px(center_mm[1], dpi)
    half = mm_to_px(radius_mm * margin_factor, dpi)

    h, w = canonical_gray.shape[:2]
    x0 = max(0, int(cx - half))
    x1 = min(w, int(cx + half))
    y0 = max(0, int(cy - half))
    y1 = min(h, int(cy + half))
    cell = canonical_gray[y0:y1, x0:x1]
    if cell.size == 0:
        return 0.0
    return float(np.sum(cell < thresh)) / cell.size


def read_id_number(canonical_gray, dpi, thresh=DARK_PIXEL_THRESHOLD):
    """学籍番号10桁を読み取る。各桁ごとに最も塗りつぶし率が高い値を採用する。"""
    digits = []
    for dig in range(layout.N_ID_DIGITS):
        ratios = [
            bubble_fill_ratio(
                canonical_gray, layout.id_bubble_center_mm(dig, val),
                layout.ID_BUBBLE_RADIUS_MM, dpi, thresh=thresh,
            )
            for val in range(layout.N_ID_VALUES)
        ]
        best_val = int(np.argmax(ratios))
        digits.append(str(best_val) if ratios[best_val] > MARK_THRESHOLD else "?")
    return "".join(digits)


def read_all_answers(canonical_gray, dpi, thresh=DARK_PIXEL_THRESHOLD):
    """80問ぶんの解答を読み取る。

    戻り値: {qnum: {"option": opt(0-4)またはNone, "raw_marked": [検出された0-4のリスト],
    "is_ambiguous": bool}}。マーク欄が2つ以上しきい値を超えた場合は誤記入（二重マーク等）
    とみなし、option は自動では決めずNoneのままにする（採点者が確認して選び直す前提）。
    """
    answers = {}
    for col in range(layout.N_COLS):
        for row in range(layout.N_ROWS):
            qnum = layout.question_number(col, row)
            ratios = [
                bubble_fill_ratio(
                    canonical_gray, layout.answer_bubble_center_mm(col, row, opt),
                    layout.ANSWER_BUBBLE_RADIUS_MM, dpi, thresh=thresh,
                )
                for opt in range(layout.N_OPTS)
            ]
            raw_marked = [i for i, r in enumerate(ratios) if r > MARK_THRESHOLD]
            near_miss = len(raw_marked) == 0 and max(ratios) > NEAR_MISS_THRESHOLD
            is_ambiguous = len(raw_marked) > 1 or near_miss
            option = raw_marked[0] if len(raw_marked) == 1 else None
            answers[qnum] = {"option": option, "raw_marked": raw_marked, "is_ambiguous": is_ambiguous}
    return answers


def crop_region_mm(canonical_gray, rect_mm, dpi, pad_mm=1.0):
    """rect_mm=(x,y,w,h) の矩形（余白 pad_mm 付き）を正規化画像から切り出す。"""
    x, y, w, h = rect_mm
    h_img, w_img = canonical_gray.shape[:2]
    x0 = max(0, int(mm_to_px(x - pad_mm, dpi)))
    y0 = max(0, int(mm_to_px(y - pad_mm, dpi)))
    x1 = min(w_img, int(mm_to_px(x + w + pad_mm, dpi)))
    y1 = min(h_img, int(mm_to_px(y + h + pad_mm, dpi)))
    return canonical_gray[y0:y1, x0:x1]


def crop_name_image(canonical_gray, dpi):
    """氏名欄（手書きのみ）を切り出す。"""
    return crop_region_mm(canonical_gray, layout.NAME_BOX_RECT_MM, dpi)


def crop_id_handwritten_image(canonical_gray, dpi):
    """学籍番号・手書き記入欄（10桁ぶん）を切り出す。"""
    return crop_region_mm(canonical_gray, layout.ID_HANDWRITTEN_ROW_RECT_MM, dpi)


def crop_answer_row_image(canonical_gray, col, row, dpi):
    """該当設問の①〜⑤マーク欄をまとめて切り出す（採点者による目視確認用）。"""
    return crop_region_mm(canonical_gray, layout.answer_row_rect_mm(col, row), dpi, pad_mm=1.5)


def process_page(gray, dpi=DEFAULT_DPI, search_margin_mm=25.0):
    """1ページぶんの前処理〜抽出までを一括で行う。

    戻り値の dict: student_id(str), answers({qnum:opt}), name_image, id_image (共に
    グレースケール numpy 配列), canonical (正規化済み全体画像)。
    """
    detected = find_registration_marks(gray, dpi, search_margin_mm=search_margin_mm)
    M, size_px = compute_homography(detected, canonical_dpi=dpi)
    canonical = warp_to_canonical(gray, M, size_px)
    return {
        "student_id": read_id_number(canonical, dpi),
        "answers": read_all_answers(canonical, dpi),
        "name_image": crop_name_image(canonical, dpi),
        "id_image": crop_id_handwritten_image(canonical, dpi),
        "canonical": canonical,
    }


def process_pdf(pdf_path, dpi=DEFAULT_DPI, search_margin_mm=25.0):
    """PDFの全ページ（1ページ=1学生の一括スキャン）を処理する。

    レジストレーションマークが検出できないページ（スキャン不良・白紙混入など）が
    あっても、その旨を error に記録して処理を継続し、バッチ全体は止めない。
    """
    results = []
    for page_index, img_bgr in enumerate(render_pdf_all_pages(pdf_path, dpi=dpi)):
        gray = to_gray(img_bgr)
        try:
            result = process_page(gray, dpi=dpi, search_margin_mm=search_margin_mm)
            result["error"] = None
        except ValueError as e:
            result = {
                "student_id": None, "answers": {},
                "name_image": None, "id_image": None, "canonical": None,
                "error": str(e),
            }
        result["page_index"] = page_index
        results.append(result)
    return results
