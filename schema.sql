-- active_question_count: この試験で実際に使った設問数（Q1〜この番号までが対象）。
-- NULL は「未設定＝全問（TOTAL_QUESTIONS）が対象」を意味する。設問の解答選択・
-- 採点集計・CSV出力はこの範囲を超えた設問を無視する。
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    dpi INTEGER NOT NULL,
    note TEXT,
    active_question_count INTEGER
);

CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    page_index INTEGER NOT NULL,
    student_id_read TEXT,
    student_id_confirmed TEXT,
    name_confirmed TEXT,
    name_image BLOB,
    id_image BLOB,
    canonical_image BLOB,
    error TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_students_batch ON students(batch_id);

-- option: 1-5 (最終的に採用された選択肢)。NULL は無回答（未マーク、または複数マーク／
-- 際どい塗りで採点者が未確定のまま）。raw_marked_options はスキャンで実際に検出された
-- 全マーク欄（カンマ区切り、例 "1,3"）で、複数検出時・しきい値付近の際どい検出時は
-- is_ambiguous=1 とし、option は自動では決めずNULLのままにする（採点者が確認して選び
-- 直す）。reviewed は「採点者がこの設問を確認済みか」を option とは独立に持つフラグ。
-- option を選び直した場合はもちろん、画像を見て「やはり無効・無回答で正しい」と判断した
-- 場合（option は NULL のまま）にも reviewed=1 にできるようにするためのもの
-- （option が NULL のままだと「未確認」なのか「確認の結果、無回答/無効と判断した」のか
-- 区別できないため）。将来の採点機能追加時は answer_keys(batch_id, question_number,
-- correct_option) のようなテーブルを足し、ここに JOIN するだけで済むように正規化してある。
CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    option INTEGER,
    raw_marked_options TEXT,
    is_ambiguous INTEGER NOT NULL DEFAULT 0,
    reviewed INTEGER NOT NULL DEFAULT 0,
    UNIQUE(student_id, question_number)
);
CREATE INDEX IF NOT EXISTS idx_answers_student ON answers(student_id);

-- 正答キー。1バッチ（1回の試験）につき、実際に使った設問番号ぶんだけ行があればよい
-- （80問すべてを使うとは限らないため）。correct_option がNULLの行（配点や大問番号だけ
-- 決まっていて正答が未確定、など）も許容し、採点時はcorrect_optionがNULLでない行だけを
-- 対象にする。points がNULLの場合は1点として扱う（採点側で解釈する）。
CREATE TABLE IF NOT EXISTS answer_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    question_number INTEGER NOT NULL,
    correct_option INTEGER,
    points REAL,
    group_number INTEGER,
    explanation TEXT,
    memo TEXT,
    UNIQUE(batch_id, question_number)
);
CREATE INDEX IF NOT EXISTS idx_answer_keys_batch ON answer_keys(batch_id);

-- 解答用紙（スキャン前の配布物）ごとの試験情報。スキャン後の batches とは独立
-- （配布時点ではまだ batch は存在しないため）。すべての項目が任意入力。
CREATE TABLE IF NOT EXISTS answer_sheets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_name TEXT,
    exam_date TEXT,
    teacher_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
