import os
import tempfile

import cv2

from flask import Blueprint, redirect, render_template, request, url_for

from helpers import get_db
from pipeline import preprocess

upload_bp = Blueprint("upload", __name__)

DEFAULT_DPI = 300


def _encode_png(gray_img):
    if gray_img is None or gray_img.size == 0:
        return None
    return cv2.imencode(".png", gray_img)[1].tobytes()


@upload_bp.get("/")
def index():
    db = get_db()
    batches = db.execute(
        "SELECT id, original_filename, uploaded_at, note, active_question_count, "
        "(SELECT COUNT(*) FROM students WHERE students.batch_id = batches.id) AS student_count "
        "FROM batches ORDER BY uploaded_at DESC"
    ).fetchall()
    return render_template("upload.html", batches=batches)


@upload_bp.post("/upload")
def do_upload():
    file = request.files.get("pdf")
    if not file or file.filename == "":
        return redirect(url_for("upload.index"))
    note = request.form.get("note", "").strip()

    fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        file.save(tmp_path)
        results = preprocess.process_pdf(tmp_path, dpi=DEFAULT_DPI)
    finally:
        os.unlink(tmp_path)

    db = get_db()
    cur = db.execute(
        "INSERT INTO batches (original_filename, dpi, note) VALUES (?, ?, ?)",
        (file.filename, DEFAULT_DPI, note),
    )
    batch_id = cur.lastrowid

    for r in results:
        name_bytes = _encode_png(r.get("name_image"))
        id_bytes = _encode_png(r.get("id_image"))
        canonical_bytes = _encode_png(r.get("canonical"))
        student_id_read = r.get("student_id")
        cur = db.execute(
            "INSERT INTO students "
            "(batch_id, page_index, student_id_read, student_id_confirmed, name_image, id_image, "
            "canonical_image, error) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id, r["page_index"], student_id_read, student_id_read,
                name_bytes, id_bytes, canonical_bytes, r.get("error"),
            ),
        )
        student_row_id = cur.lastrowid
        for qnum, info in r.get("answers", {}).items():
            opt = info.get("option")
            raw_marked = info.get("raw_marked", [])
            raw_marked_str = ",".join(str(i + 1) for i in raw_marked) if raw_marked else None
            db.execute(
                "INSERT INTO answers (student_id, question_number, option, raw_marked_options, is_ambiguous) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    student_row_id, qnum,
                    (opt + 1) if opt is not None else None,
                    raw_marked_str,
                    1 if info.get("is_ambiguous") else 0,
                ),
            )
    db.commit()

    return redirect(url_for("batch.view_batch", batch_id=batch_id))
