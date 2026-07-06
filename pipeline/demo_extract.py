"""フェーズ3パイプラインの動作確認デモ。

実スキャンがまだ無いため、以下の手順で「スキャンっぽい」画像を合成し、
前処理パイプライン（マーク検出→射影補正→座標抽出）が正しく機能するかを検証する。

1. answersheet/sheet.tex を組版した PDF を画像化（未記入の解答用紙）
2. 既知の学籍番号・解答パターンをマーク（塗りつぶし円）として書き込む
3. 余白パディング＋回転＋平行移動でスキャン時のズレ・傾きを模擬
4. パイプラインを実行し、書き込んだ内容と読み取り結果が一致するか検証する
"""

import os
import subprocess
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import layout, preprocess

DPI = 300
SHEET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "answersheet")
SHEET_TEX = os.path.join(SHEET_DIR, "sheet.tex")
SHEET_PDF = os.path.join(SHEET_DIR, "sheet.pdf")

# 既知の正解パターン（検証用）
KNOWN_ID = "1234567890"
KNOWN_ANSWERS = {1: 2, 20: 0, 21: 4, 40: 1, 41: 3, 60: 2, 61: 0, 80: 4}  # qnum -> opt(0-4)


def ensure_pdf_built():
    if not os.path.exists(SHEET_PDF):
        subprocess.run(
            ["lualatex", "-interaction=nonstopmode", "-halt-on-error", "sheet.tex"],
            cwd=SHEET_DIR, check=True, capture_output=True,
        )


def draw_filled_circle(canvas, center_mm, radius_mm, dpi, offset_px=(0, 0)):
    cx = preprocess.mm_to_px(center_mm[0], dpi) + offset_px[0]
    cy = preprocess.mm_to_px(center_mm[1], dpi) + offset_px[1]
    r = preprocess.mm_to_px(radius_mm, dpi) * 0.85
    cv2.circle(canvas, (int(round(cx)), int(round(cy))), int(round(r)), color=0, thickness=-1)


def build_synthetic_scan():
    """未記入シートに既知パターンを書き込み、傾き・パディングを加えた合成スキャン画像を作る。"""
    page_bgr = preprocess.render_pdf_page(SHEET_PDF, dpi=DPI)
    gray = preprocess.to_gray(page_bgr)

    pad_mm = 15.0
    pad_px = int(round(preprocess.mm_to_px(pad_mm, DPI)))
    h, w = gray.shape
    canvas = np.full((h + 2 * pad_px, w + 2 * pad_px), 255, dtype=np.uint8)
    canvas[pad_px:pad_px + h, pad_px:pad_px + w] = gray

    offset = (pad_px, pad_px)
    for dig, ch in enumerate(KNOWN_ID):
        val = int(ch)
        draw_filled_circle(canvas, layout.id_bubble_center_mm(dig, val), layout.ID_BUBBLE_RADIUS_MM, DPI, offset)

    for qnum, opt in KNOWN_ANSWERS.items():
        col = (qnum - 1) // layout.N_ROWS
        row = (qnum - 1) % layout.N_ROWS
        center = layout.answer_bubble_center_mm(col, row, opt)
        draw_filled_circle(canvas, center, layout.ANSWER_BUBBLE_RADIUS_MM, DPI, offset)

    # スキャン時に生じる傾き・微妙なズレを模擬（回転2.5度 + わずかな平行移動 + 微小ノイズ）
    center = (canvas.shape[1] / 2, canvas.shape[0] / 2)
    M = cv2.getRotationMatrix2D(center, angle=2.5, scale=1.0)
    M[0, 2] += 6  # 平行移動 (px)
    M[1, 2] += -4
    rotated = cv2.warpAffine(canvas, M, (canvas.shape[1], canvas.shape[0]), flags=cv2.INTER_LINEAR, borderValue=255)

    noise = np.random.default_rng(0).normal(0, 4, rotated.shape)
    noisy = np.clip(rotated.astype(np.float64) + noise, 0, 255).astype(np.uint8)
    return noisy


def main():
    ensure_pdf_built()
    scan = build_synthetic_scan()

    detected = preprocess.find_registration_marks(scan, dpi=DPI, search_margin_mm=40.0)
    print("検出したレジストレーションマーク座標(px):", detected)
    if any(c is None for c in detected):
        print("FAIL: レジストレーションマークを検出できませんでした")
        return 1

    M, size_px = preprocess.compute_homography(detected, canonical_dpi=DPI)
    canonical = preprocess.warp_to_canonical(scan, M, size_px)

    read_id = preprocess.read_id_number(canonical, dpi=DPI)
    read_answers = preprocess.read_all_answers(canonical, dpi=DPI)

    ok = True

    print(f"学籍番号: 期待={KNOWN_ID} / 読取={read_id}")
    if read_id != KNOWN_ID:
        ok = False
        print("FAIL: 学籍番号が一致しません")

    for qnum, expected_opt in KNOWN_ANSWERS.items():
        actual_opt = read_answers.get(qnum, {}).get("option")
        status = "OK" if actual_opt == expected_opt else "FAIL"
        if actual_opt != expected_opt:
            ok = False
        print(f"  Q{qnum}: 期待={expected_opt} 読取={actual_opt} [{status}]")

    unmarked_sample = [q for q in (2, 22, 42, 62) if q not in KNOWN_ANSWERS]
    for qnum in unmarked_sample:
        actual_opt = read_answers.get(qnum, {}).get("option")
        status = "OK" if actual_opt is None else "FAIL"
        if actual_opt is not None:
            ok = False
        print(f"  Q{qnum}(未回答想定): 読取={actual_opt} [{status}]")

    cv2.imwrite("/tmp/synthetic_scan.png", scan)
    cv2.imwrite("/tmp/canonical.png", canonical)

    print("=== RESULT:", "PASS" if ok else "FAIL", "===")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
