import os

import markdown as markdown_lib
from flask import Blueprint, abort, current_app, jsonify, render_template, request

from helpers import OPTION_SYMBOLS, get_db
from pipeline import layout

answer_key_bp = Blueprint("answer_key", __name__)

TOTAL_QUESTIONS = layout.N_COLS * layout.N_ROWS


# ---------- 採点ロジック（batch.py からも参照される） ----------

def get_graded_keys(db, batch_id):
    """正答が確定している設問だけを対象に {question_number: (correct_option, points)} を返す。"""
    rows = db.execute(
        "SELECT question_number, correct_option, points FROM answer_keys "
        "WHERE batch_id = ? AND correct_option IS NOT NULL",
        (batch_id,),
    ).fetchall()
    return {
        r["question_number"]: (r["correct_option"], r["points"] if r["points"] is not None else 1.0)
        for r in rows
    }


def max_score(graded):
    return sum(pts for _, pts in graded.values())


def score_answers(graded, answer_rows):
    """answer_rows: question_number/option を持つ行の列（1人の学生ぶん）。"""
    score = 0.0
    correct = 0
    for row in answer_rows:
        qnum = row["question_number"]
        if qnum in graded:
            correct_option, pts = graded[qnum]
            if row["option"] == correct_option:
                score += pts
                correct += 1
    return score, correct


# ---------- 入力値の検証 ----------

def _clean_int(value, lo=None, hi=None):
    if value in (None, ""):
        return None, None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None, "整数で入力してください"
    if lo is not None and n < lo:
        return None, f"{lo}以上で入力してください"
    if hi is not None and n > hi:
        return None, f"{hi}以下で入力してください"
    return n, None


def _clean_float(value, lo=None):
    if value in (None, ""):
        return None, None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None, "数値で入力してください"
    if lo is not None and n < lo:
        return None, f"{lo}以上で入力してください"
    return n, None


def _clean_str(value):
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _clean_item(item):
    """batch_import由来・手編集由来どちらでも使う共通クリーニング。戻り値: (cleaned_dict, errors)"""
    errors = []

    qnum, err = _clean_int(item.get("question_number"), lo=1, hi=TOTAL_QUESTIONS)
    if err:
        errors.append("question_number: " + err)
    elif qnum is None:
        errors.append("question_number は必須です")

    correct_option, err = _clean_int(item.get("correct_option"), lo=1, hi=len(OPTION_SYMBOLS))
    if err:
        errors.append("correct_option: " + err)

    points, err = _clean_float(item.get("points"), lo=0)
    if err:
        errors.append("points: " + err)

    group_number, err = _clean_int(item.get("group_number"), lo=1)
    if err:
        errors.append("group_number: " + err)

    cleaned = {
        "question_number": qnum,
        "correct_option": correct_option,
        "points": points,
        "group_number": group_number,
        "explanation": _clean_str(item.get("explanation")),
        "memo": _clean_str(item.get("memo")),
    }
    return cleaned, errors


# ---------- 解答作成（正答・配点）編集画面 ----------

@answer_key_bp.get("/batch/<int:batch_id>/answer_key")
def edit_answer_key(batch_id):
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)

    rows = db.execute(
        "SELECT question_number, correct_option, points, group_number, explanation, memo "
        "FROM answer_keys WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()
    by_qnum = {r["question_number"]: r for r in rows}

    questions = []
    graded_count = 0
    total_points = 0.0
    for qnum in range(1, TOTAL_QUESTIONS + 1):
        r = by_qnum.get(qnum)
        correct_option = r["correct_option"] if r else None
        points = r["points"] if r else None
        if correct_option is not None:
            graded_count += 1
            total_points += points if points is not None else 1.0
        questions.append({
            "qnum": qnum,
            "correct_option": correct_option,
            "points": points,
            "group_number": r["group_number"] if r else None,
            "explanation": r["explanation"] if r else None,
            "memo": r["memo"] if r else None,
        })

    return render_template(
        "answer_key.html", batch=batch, questions=questions,
        option_symbols=OPTION_SYMBOLS, graded_count=graded_count, total_points=total_points,
    )


_EDITABLE_FIELDS = {
    "correct_option": lambda v: _clean_int(v, lo=1, hi=len(OPTION_SYMBOLS)),
    "points": lambda v: _clean_float(v, lo=0),
    "group_number": lambda v: _clean_int(v, lo=1),
    "explanation": lambda v: (_clean_str(v), None),
    "memo": lambda v: (_clean_str(v), None),
}


@answer_key_bp.post("/batch/<int:batch_id>/answer_key/<int:question_number>")
def update_answer_key(batch_id, question_number):
    if not (1 <= question_number <= TOTAL_QUESTIONS):
        abort(404)

    payload = request.get_json(silent=True) or {}
    field = payload.get("field")
    if field not in _EDITABLE_FIELDS:
        abort(400)
    cleaned, err = _EDITABLE_FIELDS[field](payload.get("value"))
    if err:
        return jsonify({"error": err}), 400

    db = get_db()
    batch = db.execute("SELECT id FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)

    existing = db.execute(
        "SELECT id FROM answer_keys WHERE batch_id = ? AND question_number = ?",
        (batch_id, question_number),
    ).fetchone()
    if existing:
        db.execute(f"UPDATE answer_keys SET {field} = ? WHERE id = ?", (cleaned, existing["id"]))
    else:
        db.execute(
            f"INSERT INTO answer_keys (batch_id, question_number, {field}) VALUES (?, ?, ?)",
            (batch_id, question_number, cleaned),
        )
    db.commit()
    return jsonify({"ok": True, "field": field, "value": cleaned})


# ---------- バッチインポート（AIが作成したJSONの取り込み） ----------

@answer_key_bp.get("/batch/<int:batch_id>/answer_key/import")
def import_page(batch_id):
    db = get_db()
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)
    return render_template("answer_key_import.html", batch=batch)


@answer_key_bp.post("/batch/<int:batch_id>/answer_key/import/preview")
def import_preview(batch_id):
    db = get_db()
    batch = db.execute("SELECT id FROM batches WHERE id = ?", (batch_id,)).fetchone()
    if batch is None:
        abort(404)

    payload = request.get_json(silent=True) or {}
    items = payload.get("answer_key")
    if not isinstance(items, list):
        return jsonify({"error": "answer_key は配列である必要があります"}), 400

    existing_rows = db.execute(
        "SELECT question_number, correct_option, points, group_number, explanation, memo "
        "FROM answer_keys WHERE batch_id = ?",
        (batch_id,),
    ).fetchall()
    existing = {r["question_number"]: dict(r) for r in existing_rows}

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
        qnum = cleaned["question_number"]

        if qnum is not None:
            if qnum in seen:
                dup_msg = f"設問番号 {qnum} が他の行と重複しています"
                errors.append(dup_msg)
                prev = rows[seen[qnum]]
                if dup_msg not in prev["errors"]:
                    prev["errors"].append(dup_msg)
                prev["valid"] = False
                prev["default_checked"] = False
            seen[qnum] = i

        cur_existing = existing.get(qnum) if qnum is not None else None
        no_change = cur_existing is not None and all(
            cur_existing.get(f) == cleaned[f]
            for f in ("correct_option", "points", "group_number", "explanation", "memo")
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
        })

    return jsonify({"rows": rows, "total_questions": TOTAL_QUESTIONS, "option_symbols": OPTION_SYMBOLS})


@answer_key_bp.post("/batch/<int:batch_id>/answer_key/import/commit")
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
        if errors or cleaned["question_number"] is None:
            return jsonify({"error": f"{item.get('question_number')!r} 番の項目が不正です: {'; '.join(errors)}"}), 400

        db.execute(
            "INSERT INTO answer_keys "
            "(batch_id, question_number, correct_option, points, group_number, explanation, memo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(batch_id, question_number) DO UPDATE SET "
            "correct_option = excluded.correct_option, points = excluded.points, "
            "group_number = excluded.group_number, explanation = excluded.explanation, memo = excluded.memo",
            (
                batch_id, cleaned["question_number"], cleaned["correct_option"], cleaned["points"],
                cleaned["group_number"], cleaned["explanation"], cleaned["memo"],
            ),
        )
        applied += 1
    db.commit()
    return jsonify({"ok": True, "applied": applied})


# ---------- AI向け仕様書（スタイル付き表示） ----------

@answer_key_bp.get("/docs/answer_key_import_spec")
def spec_page():
    path = os.path.join(current_app.static_folder, "docs", "answer_key_import_spec.md")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    spec_html = markdown_lib.markdown(text, extensions=["tables", "fenced_code"])
    return render_template("answer_key_spec.html", spec_html=spec_html)
