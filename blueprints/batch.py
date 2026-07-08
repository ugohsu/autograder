import csv
import io
import zipfile

import cv2
import numpy as np
from flask import Blueprint, Response, abort, jsonify, render_template, request, send_file

from blueprints.answer_key import (
    TOTAL_QUESTIONS,
    get_graded_keys,
    is_fully_graded,
    is_fully_grouped,
    load_full_answer_keys,
    max_score,
    score_answers,
)
from helpers import OPTION_SYMBOLS, get_db
from pipeline import handwriting_sheet, layout, preprocess

batch_bp = Blueprint("batch", __name__)


def effective_question_count(batch):
    """この試験で有効な設問数（Q1〜この番号まで）。未設定なら全問（TOTAL_QUESTIONS）。"""
    n = batch["active_question_count"]
    return n if n is not None else TOTAL_QUESTIONS


@batch_bp.get("/batch/<int:batch_id>")
def view_batch(batch_id):
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)
    active_count = effective_question_count(batch)

    students = db.execute(
        "SELECT id, page_index, student_id_read, student_id_confirmed, name_confirmed, error, "
        "name_image IS NOT NULL AS has_name_image, id_image IS NOT NULL AS has_id_image "
        "FROM students WHERE batch_id = ? ORDER BY page_index",
        (batch_id,),
    ).fetchall()

    rows = db.execute(
        "SELECT s.id AS student_id, a.question_number, a.option, a.is_ambiguous, a.reviewed "
        "FROM answers a JOIN students s ON s.id = a.student_id "
        "WHERE s.batch_id = ? AND a.question_number <= ? ORDER BY s.id, a.question_number",
        (batch_id, active_count),
    ).fetchall()

    per_student_rows = {}
    for row in rows:
        per_student_rows.setdefault(row["student_id"], []).append(row)

    graded = {q: v for q, v in get_graded_keys(db, batch_id).items() if q <= active_count}
    batch_max_score = max_score(graded)

    key_rows = load_full_answer_keys(db, batch_id, active_count)
    totals_csv_available = is_fully_graded(key_rows, active_count)
    group_totals_csv_available = totals_csv_available and is_fully_grouped(key_rows, active_count)

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
        active_question_count=active_count, total_questions=TOTAL_QUESTIONS,
        totals_csv_available=totals_csv_available,
        group_totals_csv_available=group_totals_csv_available,
    )


@batch_bp.get("/batch/<int:batch_id>/student/<int:student_id>")
def student_detail(batch_id, student_id):
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    student = db.execute(
        "SELECT id, page_index, student_id_read, student_id_confirmed, name_confirmed, error, "
        "name_image IS NOT NULL AS has_name_image, id_image IS NOT NULL AS has_id_image, "
        "canonical_image IS NOT NULL AS has_canonical "
        "FROM students WHERE id = ? AND batch_id = ?",
        (student_id, batch_id),
    ).fetchone()
    if batch is None or student is None:
        abort(404)
    active_count = effective_question_count(batch)

    ordered_ids = [
        r["id"] for r in db.execute(
            "SELECT id FROM students WHERE batch_id = ? ORDER BY page_index", (batch_id,)
        ).fetchall()
    ]
    idx = ordered_ids.index(student_id)
    prev_student_id = ordered_ids[idx - 1] if idx > 0 else None
    next_student_id = ordered_ids[idx + 1] if idx < len(ordered_ids) - 1 else None

    rows = db.execute(
        "SELECT question_number, option, raw_marked_options, is_ambiguous, reviewed "
        "FROM answers WHERE student_id = ? ORDER BY question_number",
        (student_id,),
    ).fetchall()

    graded = {q: v for q, v in get_graded_keys(db, batch_id).items() if q <= active_count}
    score, correct_count = score_answers(graded, [r for r in rows if r["question_number"] <= active_count])
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
            "is_active": qnum <= active_count,
            "is_graded": key is not None,
            "is_correct": (key is not None and row["option"] == key[0]),
            "correct_symbol": OPTION_SYMBOLS[key[0] - 1] if key is not None else None,
            "points": key[1] if key is not None else None,
        })

    return render_template(
        "student_detail.html", batch=batch, student=student, questions=questions,
        option_symbols=OPTION_SYMBOLS, is_graded=bool(graded),
        score=score, correct_count=correct_count, batch_max_score=batch_max_score,
        active_question_count=active_count,
        prev_student_id=prev_student_id, next_student_id=next_student_id,
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


@batch_bp.post("/batch/<int:batch_id>/active_question_count")
def update_active_question_count(batch_id):
    payload = request.get_json(silent=True) or {}
    raw_value = payload.get("active_question_count")
    if raw_value in (None, ""):
        value = None
    else:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return jsonify({"error": "整数で入力してください"}), 400
        if not (1 <= value <= TOTAL_QUESTIONS):
            return jsonify({"error": f"1〜{TOTAL_QUESTIONS}で入力してください"}), 400

    db = get_db()
    cur = db.execute(
        "UPDATE batches SET active_question_count = ? WHERE id = ?", (value, batch_id)
    )
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    return jsonify({"ok": True, "active_question_count": value})


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


@batch_bp.post("/batch/<int:batch_id>/student/<int:student_id>/name")
def update_student_name(batch_id, student_id):
    payload = request.get_json(silent=True) or {}
    new_name = str(payload.get("name", "")).strip()
    db = get_db()
    cur = db.execute(
        "UPDATE students SET name_confirmed = ? WHERE id = ? AND batch_id = ?",
        (new_name, student_id, batch_id),
    )
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    return jsonify({"ok": True, "name": new_name})


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


@batch_bp.get("/batch/<int:batch_id>/handwriting_images.zip")
def handwriting_images_zip(batch_id):
    """氏名・学籍番号の手書き画像一覧をチャット型AIへの書き起こし依頼用にPNGへまとめ、
    人数が多い場合は複数ページに分割してZIPで一括ダウンロードできるようにする。"""
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)

    students = db.execute(
        "SELECT page_index, name_image, id_image FROM students WHERE batch_id = ? ORDER BY page_index",
        (batch_id,),
    ).fetchall()
    if not students:
        return jsonify({"error": "この試験には学生データがありません"}), 400

    def decode(blob):
        if blob is None:
            return None
        return cv2.imdecode(np.frombuffer(blob, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)

    rows = [
        {
            "seq": s["page_index"] + 1,
            "name_image": decode(s["name_image"]),
            "id_image": decode(s["id_image"]),
        }
        for s in students
    ]

    pages = handwriting_sheet.build_pages(rows)

    zip_basename = f"batch_{batch_id}_handwriting"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(0, len(rows), handwriting_sheet.DEFAULT_PER_PAGE):
            chunk = rows[i:i + handwriting_sheet.DEFAULT_PER_PAGE]
            start_seq, end_seq = chunk[0]["seq"], chunk[-1]["seq"]
            page_bytes = pages[i // handwriting_sheet.DEFAULT_PER_PAGE]
            zf.writestr(f"{zip_basename}/{zip_basename}_no{start_seq:03d}-{end_seq:03d}.png", page_bytes)
    buf.seek(0)

    return send_file(
        buf, mimetype="application/zip", as_attachment=True,
        download_name=f"{zip_basename}.zip",
    )


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
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)
    active_count = effective_question_count(batch)
    graded = {q: v for q, v in get_graded_keys(db, batch_id).items() if q <= active_count}

    rows = db.execute(
        "SELECT s.student_id_confirmed AS student_id, a.question_number, a.option "
        "FROM answers a JOIN students s ON s.id = a.student_id "
        "WHERE s.batch_id = ? AND a.question_number <= ? ORDER BY s.id, a.question_number",
        (batch_id, active_count),
    ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["student_id", "question_number", "answer"]
    if graded:
        header.append("score")
    writer.writerow(header)
    for row in rows:
        line = [
            row["student_id"],
            row["question_number"],
            row["option"] if row["option"] is not None else "",
        ]
        if graded:
            key = graded.get(row["question_number"])
            if key is None:
                line.append("")
            else:
                correct_option, points = key
                line.append(points if row["option"] == correct_option else 0)
        writer.writerow(line)

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=batch_{batch_id}_answers.csv"},
    )


@batch_bp.get("/batch/<int:batch_id>/export_totals.csv")
def export_totals_csv(batch_id):
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)
    active_count = effective_question_count(batch)

    key_rows = load_full_answer_keys(db, batch_id, active_count)
    if not is_fully_graded(key_rows, active_count):
        return jsonify({
            "error": "有効範囲の全設問に正答が設定されていないため、このフォーマットはダウンロードできません"
        }), 400
    graded = {
        q: (r["correct_option"], r["points"] if r["points"] is not None else 1.0)
        for q, r in key_rows.items()
    }

    students = db.execute(
        "SELECT id, student_id_confirmed FROM students WHERE batch_id = ? ORDER BY id",
        (batch_id,),
    ).fetchall()
    rows = db.execute(
        "SELECT s.id AS student_id, a.question_number, a.option "
        "FROM answers a JOIN students s ON s.id = a.student_id "
        "WHERE s.batch_id = ? AND a.question_number <= ?",
        (batch_id, active_count),
    ).fetchall()
    per_student_rows = {}
    for row in rows:
        per_student_rows.setdefault(row["student_id"], []).append(row)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["student_id", "total_score"])
    for s in students:
        score, _ = score_answers(graded, per_student_rows.get(s["id"], []))
        writer.writerow([s["student_id_confirmed"] or "", score])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=batch_{batch_id}_totals.csv"},
    )


@batch_bp.get("/batch/<int:batch_id>/export_group_totals.csv")
def export_group_totals_csv(batch_id):
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)
    active_count = effective_question_count(batch)

    key_rows = load_full_answer_keys(db, batch_id, active_count)
    if not (is_fully_graded(key_rows, active_count) and is_fully_grouped(key_rows, active_count)):
        return jsonify({
            "error": "有効範囲の全設問に正答・大問が設定されていないため、このフォーマットはダウンロードできません"
        }), 400

    groups = sorted({key_rows[q]["group_number"] for q in range(1, active_count + 1)})
    qnum_to_group = {q: key_rows[q]["group_number"] for q in range(1, active_count + 1)}
    qnum_to_key = {
        q: (key_rows[q]["correct_option"], key_rows[q]["points"] if key_rows[q]["points"] is not None else 1.0)
        for q in range(1, active_count + 1)
    }

    students = db.execute(
        "SELECT id, student_id_confirmed FROM students WHERE batch_id = ? ORDER BY id",
        (batch_id,),
    ).fetchall()
    rows = db.execute(
        "SELECT s.id AS student_id, a.question_number, a.option "
        "FROM answers a JOIN students s ON s.id = a.student_id "
        "WHERE s.batch_id = ? AND a.question_number <= ?",
        (batch_id, active_count),
    ).fetchall()
    per_student_rows = {}
    for row in rows:
        per_student_rows.setdefault(row["student_id"], []).append(row)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["student_id"] + [f"group_{g}" for g in groups] + ["total_score"])
    for s in students:
        group_scores = {g: 0.0 for g in groups}
        for r in per_student_rows.get(s["id"], []):
            correct_option, points = qnum_to_key[r["question_number"]]
            if r["option"] == correct_option:
                group_scores[qnum_to_group[r["question_number"]]] += points
        writer.writerow(
            [s["student_id_confirmed"] or ""] + [group_scores[g] for g in groups] + [sum(group_scores.values())]
        )

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=batch_{batch_id}_group_totals.csv"},
    )
