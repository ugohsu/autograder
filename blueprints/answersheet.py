import io
import os
import re

import fitz
from flask import Blueprint, abort, jsonify, redirect, render_template, request, send_file, url_for

from helpers import BASE_DIR, get_db

answersheet_bp = Blueprint("answersheet", __name__)

TEMPLATE_PDF_PATH = os.path.join(BASE_DIR, "answersheet", "sheet.pdf")

MM = 2.834645669  # 1mm を PDF point に変換する係数

# 試験情報の挿入位置。answersheet/sheet.tex のタイトル「解答用紙」と同じ高さの左右の
# 余白（タイトルの実際のグリフ範囲は x≈95.6〜114.4mm, y≈22.3〜29.1mm）に収まるよう、
# 試験名は左寄せ・実施日／担当教員は右寄せで配置する。sheet.tex 側のレイアウトを変更
# した場合はここも合わせて調整すること。TeX Live を使わず PyMuPDF の組み込みCJKフォント
# （fontname="japan"）でテキストを重ね書きするだけなので、配布アプリに TeX Live を
# 含めずに済む（sheet.tex 自体は汎用のまま変更しない）。
META_LEFT_X_MM = 20
META_RIGHT_EDGE_X_MM = 198
META_Y_MM = 27
META_LINE_PITCH_MM = 5  # 実施日・担当を2行にする場合の行間
META_FONT_SIZE = 9

_EDITABLE_FIELDS = {"exam_name", "exam_date", "teacher_name"}


def _build_right_lines(exam_date, teacher_name):
    """実施日・担当は、両方あるときだけ2行に分けて窮屈にならないようにする。"""
    lines = []
    if exam_date:
        lines.append(f"実施日: {exam_date}")
    if teacher_name:
        lines.append(f"担当: {teacher_name}")
    return lines


def _sanitize_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", name).strip()
    return name or "解答用紙"


@answersheet_bp.get("/answersheets")
def list_answersheets():
    db = get_db()
    sheets = db.execute("SELECT * FROM answer_sheets ORDER BY created_at DESC").fetchall()
    return render_template("answersheets.html", sheets=sheets)


@answersheet_bp.post("/answersheets")
def create_answersheet():
    exam_name = request.form.get("exam_name", "").strip() or None
    exam_date = request.form.get("exam_date", "").strip() or None
    teacher_name = request.form.get("teacher_name", "").strip() or None

    db = get_db()
    cur = db.execute(
        "INSERT INTO answer_sheets (exam_name, exam_date, teacher_name) VALUES (?, ?, ?)",
        (exam_name, exam_date, teacher_name),
    )
    db.commit()
    return redirect(url_for("answersheet.answersheet_detail", sheet_id=cur.lastrowid))


@answersheet_bp.get("/answersheets/<int:sheet_id>")
def answersheet_detail(sheet_id):
    db = get_db()
    sheet = db.execute("SELECT * FROM answer_sheets WHERE id = ?", (sheet_id,)).fetchone()
    if sheet is None:
        abort(404)
    return render_template("answersheet_detail.html", sheet=sheet)


@answersheet_bp.post("/answersheets/<int:sheet_id>")
def update_answersheet(sheet_id):
    payload = request.get_json(silent=True) or {}
    field = payload.get("field")
    if field not in _EDITABLE_FIELDS:
        abort(400)
    value = str(payload.get("value") or "").strip() or None

    db = get_db()
    cur = db.execute(f"UPDATE answer_sheets SET {field} = ? WHERE id = ?", (value, sheet_id))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    return jsonify({"ok": True, "field": field, "value": value})


@answersheet_bp.delete("/answersheets/<int:sheet_id>")
def delete_answersheet(sheet_id):
    db = get_db()
    cur = db.execute("DELETE FROM answer_sheets WHERE id = ?", (sheet_id,))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    return jsonify({"ok": True})


@answersheet_bp.get("/answersheets/<int:sheet_id>/download")
def download_answersheet(sheet_id):
    db = get_db()
    sheet = db.execute("SELECT * FROM answer_sheets WHERE id = ?", (sheet_id,)).fetchone()
    if sheet is None:
        abort(404)

    doc = fitz.open(TEMPLATE_PDF_PATH)
    page = doc[0]

    if sheet["exam_name"]:
        page.insert_text(
            fitz.Point(META_LEFT_X_MM * MM, META_Y_MM * MM),
            sheet["exam_name"], fontsize=META_FONT_SIZE, fontname="japan",
        )

    right_lines = _build_right_lines(sheet["exam_date"], sheet["teacher_name"])
    if len(right_lines) == 1:
        line_ys_mm = [META_Y_MM]
    elif len(right_lines) == 2:
        half_pitch = META_LINE_PITCH_MM / 2
        line_ys_mm = [META_Y_MM - half_pitch, META_Y_MM + half_pitch]
    else:
        line_ys_mm = []

    for line, y_mm in zip(right_lines, line_ys_mm):
        width = fitz.get_text_length(line, fontname="japan", fontsize=META_FONT_SIZE)
        page.insert_text(
            fitz.Point(META_RIGHT_EDGE_X_MM * MM - width, y_mm * MM),
            line, fontsize=META_FONT_SIZE, fontname="japan",
        )

    pdf_bytes = doc.tobytes()
    doc.close()

    filename = _sanitize_filename(sheet["exam_name"] or "解答用紙") + ".pdf"
    return send_file(
        io.BytesIO(pdf_bytes), mimetype="application/pdf",
        as_attachment=True, download_name=filename,
    )
