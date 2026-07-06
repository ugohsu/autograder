import csv
import io

import cv2
import numpy as np
from flask import Blueprint, Response, abort, jsonify, render_template, request, send_file

from blueprints.answer_key import get_graded_keys, max_score, score_answers
from helpers import OPTION_SYMBOLS, get_db
from pipeline import layout, preprocess

batch_bp = Blueprint("batch", __name__)


@batch_bp.get("/batch/<int:batch_id>")
def view_batch(batch_id):
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)

    students = db.execute(
        "SELECT id, page_index, student_id_read, student_id_confirmed, error, "
        "name_image IS NOT NULL AS has_name_image, id_image IS NOT NULL AS has_id_image "
        "FROM students WHERE batch_id = ? ORDER BY page_index",
        (batch_id,),
    ).fetchall()

    rows = db.execute(
        "SELECT s.id AS student_id, a.question_number, a.option, a.is_ambiguous, a.reviewed "
        "FROM answers a JOIN students s ON s.id = a.student_id "
        "WHERE s.batch_id = ? ORDER BY s.id, a.question_number",
        (batch_id,),
    ).fetchall()

    per_student_rows = {}
    for row in rows:
        per_student_rows.setdefault(row["student_id"], []).append(row)

    graded = get_graded_keys(db, batch_id)
    batch_max_score = max_score(graded)

    PREVIEW_N = 5
    summaries = {}
    for sid, srows in per_student_rows.items():
        symbols = [OPTION_SYMBOLS[r["option"] - 1] if r["option"] else "―" for r in srows]
        needs_review = sum(1 for r in srows if r["is_ambiguous"] and not r["reviewed"])
        score, correct_count = score_answers(graded, srows)
        summaries[sid] = {
            "answered_count": sum(1 for r in srows if r["option"] is not None),
            "total_count": len(srows),
            "preview": "".join(symbols[:PREVIEW_N]),
            "needs_review": needs_review,
            "score": score,
            "correct_count": correct_count,
        }

    return render_template(
        "batch.html", batch=batch, students=students, summaries=summaries,
        is_graded=bool(graded), batch_max_score=batch_max_score,
    )


@batch_bp.get("/batch/<int:batch_id>/student/<int:student_id>")
def student_detail(batch_id, student_id):
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    student = db.execute(
        "SELECT id, page_index, student_id_read, student_id_confirmed, error, "
        "name_image IS NOT NULL AS has_name_image, id_image IS NOT NULL AS has_id_image, "
        "canonical_image IS NOT NULL AS has_canonical "
        "FROM students WHERE id = ? AND batch_id = ?",
        (student_id, batch_id),
    ).fetchone()
    if batch is None or student is None:
        abort(404)

    rows = db.execute(
        "SELECT question_number, option, raw_marked_options, is_ambiguous, reviewed "
        "FROM answers WHERE student_id = ? ORDER BY question_number",
        (student_id,),
    ).fetchall()

    graded = get_graded_keys(db, batch_id)
    score, correct_count = score_answers(graded, rows)
    batch_max_score = max_score(graded)

    questions = []
    for row in rows:
        raw_marked = set()
        if row["raw_marked_options"]:
            raw_marked = {int(x) for x in row["raw_marked_options"].split(",")}
        qnum = row["question_number"]
        key = graded.get(qnum)
        questions.append({
            "qnum": qnum,
            "option": row["option"],
            "symbol": OPTION_SYMBOLS[row["option"] - 1] if row["option"] else None,
            "raw_marked": raw_marked,
            "is_ambiguous": bool(row["is_ambiguous"]),
            "reviewed": bool(row["reviewed"]),
            "is_graded": key is not None,
            "is_correct": (key is not None and row["option"] == key[0]),
            "correct_symbol": OPTION_SYMBOLS[key[0] - 1] if key is not None else None,
            "points": key[1] if key is not None else None,
        })

    return render_template(
        "student_detail.html", batch=batch, student=student, questions=questions,
        option_symbols=OPTION_SYMBOLS, is_graded=bool(graded),
        score=score, correct_count=correct_count, batch_max_score=batch_max_score,
    )


@batch_bp.post("/batch/<int:batch_id>/note")
def update_note(batch_id):
    payload = request.get_json(silent=True) or {}
    note = str(payload.get("note", "")).strip()
    db = get_db()
    cur = db.execute("UPDATE batches SET note = ? WHERE id = ?", (note, batch_id))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    return jsonify({"ok": True, "note": note})


@batch_bp.delete("/batch/<int:batch_id>")
def delete_batch(batch_id):
    db = get_db()
    cur = db.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    return jsonify({"ok": True})


@batch_bp.post("/batch/<int:batch_id>/student/<int:student_id>/id")
def update_student_id(batch_id, student_id):
    payload = request.get_json(silent=True) or {}
    new_id = str(payload.get("student_id", "")).strip()
    db = get_db()
    cur = db.execute(
        "UPDATE students SET student_id_confirmed = ? WHERE id = ? AND batch_id = ?",
        (new_id, student_id, batch_id),
    )
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    return jsonify({"ok": True, "student_id": new_id})


@batch_bp.post("/batch/<int:batch_id>/student/<int:student_id>/answer/<int:question_number>")
def update_answer(batch_id, student_id, question_number):
    payload = request.get_json(silent=True) or {}
    raw_value = payload.get("option")
    option = int(raw_value) if raw_value not in (None, "") else None
    if option is not None and not (1 <= option <= len(OPTION_SYMBOLS)):
        abort(400)

    db = get_db()
    cur = db.execute(
        "UPDATE answers SET option = ?, reviewed = 1 "
        "WHERE question_number = ? AND student_id = ("
        "  SELECT id FROM students WHERE id = ? AND batch_id = ?"
        ")",
        (option, question_number, student_id, batch_id),
    )
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    return jsonify({"ok": True, "option": option})


@batch_bp.get("/image/<int:student_id>/<kind>")
def student_image(student_id, kind):
    if kind not in ("name", "id"):
        abort(404)
    column = "name_image" if kind == "name" else "id_image"
    db = get_db()
    row = db.execute(
        f"SELECT {column} AS img FROM students WHERE id = ?", (student_id,)
    ).fetchone()
    if row is None or row["img"] is None:
        abort(404)
    return send_file(io.BytesIO(row["img"]), mimetype="image/png")


@batch_bp.get("/batch/<int:batch_id>/student/<int:student_id>/answer_image/<int:question_number>")
def answer_image(batch_id, student_id, question_number):
    db = get_db()
    row = db.execute(
        "SELECT s.canonical_image AS img, b.dpi AS dpi "
        "FROM students s JOIN batches b ON b.id = s.batch_id "
        "WHERE s.id = ? AND s.batch_id = ?",
        (student_id, batch_id),
    ).fetchone()
    if row is None or row["img"] is None:
        abort(404)

    canonical = cv2.imdecode(np.frombuffer(row["img"], dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    col = (question_number - 1) // layout.N_ROWS
    r = (question_number - 1) % layout.N_ROWS
    crop = preprocess.crop_answer_row_image(canonical, col, r, dpi=row["dpi"])
    png_bytes = cv2.imencode(".png", crop)[1].tobytes()
    return send_file(io.BytesIO(png_bytes), mimetype="image/png")


@batch_bp.get("/batch/<int:batch_id>/export.csv")
def export_csv(batch_id):
    db = get_db()
    rows = db.execute(
        "SELECT s.student_id_confirmed AS student_id, a.question_number, a.option "
        "FROM answers a JOIN students s ON s.id = a.student_id "
        "WHERE s.batch_id = ? ORDER BY s.id, a.question_number",
        (batch_id,),
    ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["student_id", "question_number", "answer"])
    for row in rows:
        writer.writerow([
            row["student_id"],
            row["question_number"],
            row["option"] if row["option"] is not None else "",
        ])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=batch_{batch_id}_answers.csv"},
    )
