import os

import markdown as markdown_lib
from flask import Blueprint, abort, current_app, jsonify, render_template, request, url_for

from helpers import get_db

roster_bp = Blueprint("roster_import", __name__)


# ---------- 入力値の検証（answer_key.py の _clean_item と同じ考え方） ----------

def _clean_str(value):
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _clean_seq(value):
    if value in (None, ""):
        return None, "seq は必須です"
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None, "整数で入力してください"
    if n < 1:
        return None, "1以上で入力してください"
    return n, None


def _clean_item(item):
    errors = []
    seq, err = _clean_seq(item.get("seq"))
    if err:
        errors.append("seq: " + err)
    cleaned = {
        "seq": seq,
        "name": _clean_str(item.get("name")),
        "student_id": _clean_str(item.get("student_id")),
    }
    return cleaned, errors


# ---------- バッチインポート（AIが読み取った氏名・学籍番号JSONの取り込み） ----------

@roster_bp.get("/batch/<int:batch_id>/roster_import")
def import_page(batch_id):
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)
    return render_template("roster_import.html", batch=batch)


@roster_bp.post("/batch/<int:batch_id>/roster_import/preview")
def import_preview(batch_id):
    db = get_db()
    batch = db.execute("SELECT id FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    items = payload.get("roster")
    if not isinstance(items, list):
        return jsonify({"error": "roster は配列である必要があります"}), 400

    student_rows = db.execute(
        "SELECT id, page_index, name_confirmed, student_id_confirmed, student_id_read "
        "FROM students WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()
    by_seq = {r["page_index"] + 1: r for r in student_rows}

    seen = {}
    rows = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            rows.append({
                "index": i, "input": item, "cleaned": None,
                "comment": None, "confidence": None,
                "errors": ["オブジェクトである必要があります"], "valid": False,
                "existing": None, "no_change": False, "default_checked": False,
            })
            continue

        cleaned, errors = _clean_item(item)
        seq = cleaned["seq"]

        if seq is not None:
            if seq in seen:
                dup_msg = f"通し番号 {seq} が他の行と重複しています"
                errors.append(dup_msg)
                prev = rows[seen[seq]]
                if dup_msg not in prev["errors"]:
                    prev["errors"].append(dup_msg)
                prev["valid"] = False
                prev["default_checked"] = False
            seen[seq] = i

        student = by_seq.get(seq) if seq is not None else None
        if seq is not None and student is None:
            errors.append(f"通し番号 {seq} に該当する受験生が見つかりません")

        cur_existing = None
        mark_student_id = None
        if student is not None:
            cur_existing = {"name": student["name_confirmed"], "student_id": student["student_id_confirmed"]}
            mark_student_id = student["student_id_read"]
        no_change = cur_existing is not None and all(
            cur_existing.get(f) == cleaned[f] for f in ("name", "student_id")
        )

        rows.append({
            "index": i,
            "input": item,
            "cleaned": cleaned,
            "comment": item.get("_comment"),
            "confidence": item.get("_confidence"),
            "errors": errors,
            "valid": len(errors) == 0,
            "existing": cur_existing,
            "no_change": no_change,
            "default_checked": len(errors) == 0 and not no_change,
            # マークシート（OMR）で読み取られた学籍番号。AIが読み取った学籍番号と食い違う場合に
            # フロント側で警告表示・採用ボタンを出すために渡す。
            "mark_student_id": mark_student_id,
        })

    return jsonify({"rows": rows})


@roster_bp.post("/batch/<int:batch_id>/roster_import/commit")
def import_commit(batch_id):
    db = get_db()
    batch = db.execute("SELECT id FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return jsonify({"error": "インポートする項目がありません"}), 400

    applied = 0
    for item in items:
        cleaned, errors = _clean_item(item)
        if errors or cleaned["seq"] is None:
            return jsonify({"error": f"{item.get('seq')!r} 番の項目が不正です: {'; '.join(errors)}"}), 400

        page_index = cleaned["seq"] - 1
        cur = db.execute(
            "UPDATE students SET name_confirmed = ?, student_id_confirmed = ? "
            "WHERE batch_id = ? AND page_index = ?",
            (cleaned["name"], cleaned["student_id"], batch_id, page_index),
        )
        if cur.rowcount == 0:
            return jsonify({"error": f"通し番号 {cleaned['seq']} に該当する受験生が見つかりません"}), 400
        applied += 1
    db.commit()
    return jsonify({"ok": True, "applied": applied})


# ---------- AI向け仕様書（スタイル付き表示） ----------

@roster_bp.get("/docs/roster_import_spec")
def spec_page():
    path = os.path.join(current_app.static_folder, "docs", "roster_import_spec.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    spec_html = markdown_lib.markdown(text, extensions=["tables", "fenced_code"])
    return render_template(
        "ai_import_spec.html", spec_html=spec_html,
        spec_title="名簿（氏名・学籍番号）AIインポート仕様書",
        spec_download_url=url_for("static", filename="docs/roster_import_spec.md"),
    )
