import os
import random
import json
import sqlite3
from datetime import datetime
from io import BytesIO
from flask import Flask, render_template, request, jsonify, session, send_file
import pandas as pd

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "guidance-quiz-secret-2024")

EXCEL_PATH = os.path.join(os.path.dirname(__file__), "Guidance_Notes_-_Quiz_Questions.xlsx")
DB_PATH = os.environ.get("DASHBOARD_DB", os.path.join(os.path.dirname(__file__), "hof.db"))

# Scoring multipliers
DIFF_MULTIPLIER = {"guardian": 1.0, "champion": 1.5, "god": 2.0}
COUNT_MULTIPLIER = {10: 0.8, 20: 1.0, 30: 1.15}
MAX_HOF_ENTRIES = 100  # store top 100, display top 20


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hall_of_fame (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                score_pct INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                total INTEGER NOT NULL,
                difficulty TEXT NOT NULL,
                hof_score REAL NOT NULL,
                submitted_at TEXT NOT NULL
            )
        """)
        conn.commit()


def calculate_hof_score(pct, total, difficulty):
    diff_mult = DIFF_MULTIPLIER.get(difficulty, 1.0)
    # Find nearest count multiplier key
    count_mult = COUNT_MULTIPLIER.get(total, 1.0)
    if total not in COUNT_MULTIPLIER:
        # Interpolate for edge cases
        if total <= 10:
            count_mult = 0.8
        elif total <= 20:
            count_mult = 0.8 + (total - 10) / 10 * 0.2
        else:
            count_mult = 1.0 + (total - 20) / 10 * 0.15
    return round(pct * diff_mult * count_mult, 1)


init_db()

DIFFICULTY_MAP = {
    "guardian": "Guidance Guardian",
    "champion": "Guidance Champion",
    "god": "Guidance God"
}

DIFFICULTY_LABELS = {
    "guardian": "Guidance Guardian",
    "champion": "Guidance Champion",
    "god": "Guidance God"
}


def load_questions(difficulty_key):
    df = pd.read_excel(EXCEL_PATH, sheet_name="Questions")
    df.columns = df.columns.str.strip()
    difficulty_name = DIFFICULTY_MAP[difficulty_key]
    filtered = df[df["Difficulty"] == difficulty_name]

    questions = []
    for _, row in filtered.iterrows():
        options = []
        for col in ["A", "B", "C", "D"]:
            val = row.get(col)
            if pd.notna(val) and str(val).strip():
                options.append({"key": col, "text": str(val).strip()})

        answer_raw = str(row.get("Answer", "")).strip()
        # Answer is like "A - True" or "B - False..." — extract just the letter
        correct_letter = answer_raw[0] if answer_raw else "A"

        question_text = str(row.get("Question", "")).strip()
        if not question_text or not options:
            continue

        questions.append({
            "question": question_text,
            "options": options,
            "correct": correct_letter,
            "ref": str(row.get("Ref", ""))
        })

    return questions


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/start", methods=["POST"])
def start_quiz():
    data = request.json
    difficulty = data.get("difficulty", "guardian")
    count = int(data.get("count", 10))

    questions = load_questions(difficulty)
    random.shuffle(questions)
    selected = questions[:min(count, len(questions))]

    session["questions"] = selected
    session["difficulty"] = difficulty
    session["count"] = count

    # Strip correct answers before sending to client
    client_questions = []
    for i, q in enumerate(selected):
        client_questions.append({
            "id": i,
            "question": q["question"],
            "options": q["options"]
        })

    return jsonify({"questions": client_questions, "total": len(selected)})


@app.route("/api/submit", methods=["POST"])
def submit_quiz():
    data = request.json
    answers = data.get("answers", {})  # {question_id: selected_letter}

    questions = session.get("questions", [])
    difficulty = session.get("difficulty", "guardian")

    if not questions:
        return jsonify({"error": "No active quiz session"}), 400

    correct_count = 0
    results = []
    for i, q in enumerate(questions):
        user_ans = answers.get(str(i), "")
        is_correct = user_ans == q["correct"]
        if is_correct:
            correct_count += 1
        results.append({
            "question": q["question"],
            "options": q["options"],
            "correct": q["correct"],
            "user": user_ans,
            "is_correct": is_correct
        })

    total = len(questions)
    pct = round((correct_count / total) * 100) if total > 0 else 0

    if pct >= 80:
        verdict = "outstanding"
        message = "Outstanding! You absolute legend. Chris Hendy himself would be proud. Consider yourself a true Guidance God in the making! 🏆"
        image = "happy.jpg"
    elif pct >= 50:
        verdict = "satisfactory"
        message = "Not bad! You clearly read the guidance notes... at least some of them. Room for improvement, but we won't report you to the bridges team. 😏"
        image = "satisfied.jpg"
    else:
        verdict = "poor"
        message = "Oh dear. Have you actually read ANY guidance notes? The bridges are judging you right now. Back to the books! 📚"
        image = "angry.jpg"

    # Calculate Hall of Fame score
    hof_score = calculate_hof_score(pct, total, difficulty)

    session["last_result"] = {
        "score": correct_count,
        "total": total,
        "pct": pct,
        "verdict": verdict,
        "message": message,
        "image": image,
        "difficulty": DIFFICULTY_LABELS.get(difficulty, difficulty),
        "difficulty_key": difficulty,
        "hof_score": hof_score
    }

    return jsonify({
        "score": correct_count,
        "total": total,
        "pct": pct,
        "verdict": verdict,
        "message": message,
        "image": image,
        "difficulty": DIFFICULTY_LABELS.get(difficulty, difficulty),
        "hof_score": hof_score,
        "results": results
    })





@app.route("/api/hof-submit", methods=["POST"])
def hof_submit():
    data = request.json
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Please enter your name!"}), 400
    if len(name) > 50:
        return jsonify({"error": "Name too long — we're making a leaderboard, not a novel."}), 400

    result = session.get("last_result")
    if not result:
        return jsonify({"error": "No quiz result found — complete the quiz first!"}), 400

    hof_score = result.get("hof_score", 0)
    difficulty = result.get("difficulty_key", "guardian")

    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO hall_of_fame (name, score_pct, correct, total, difficulty, hof_score, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                result["pct"],
                result["score"],
                result["total"],
                result["difficulty"],
                hof_score,
                datetime.utcnow().strftime("%Y-%m-%d %H:%M")
            ))
            conn.commit()

            # Get this entry's rank
            rank = conn.execute("""
                SELECT COUNT(*) + 1 as rank FROM hall_of_fame
                WHERE hof_score > ?
            """, (hof_score,)).fetchone()["rank"]

        return jsonify({"success": True, "rank": rank, "hof_score": hof_score})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/hof", methods=["GET"])
def hof_get():
    try:
        with get_db() as conn:
            rows = conn.execute("""
                SELECT name, score_pct, correct, total, difficulty, hof_score, submitted_at
                FROM hall_of_fame
                ORDER BY hof_score DESC
                LIMIT 20
            """).fetchall()
            total_entries = conn.execute("SELECT COUNT(*) as c FROM hall_of_fame").fetchone()["c"]

        entries = [dict(r) for r in rows]
        return jsonify({"entries": entries, "total": total_entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download-certificate", methods=["POST"])
def download_certificate():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Image as RLImage
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    data = request.json
    name = data.get("name", "Engineer").strip() or "Engineer"

    result = session.get("last_result")
    if not result:
        return jsonify({"error": "No quiz result found — please complete the quiz first"}), 400

    # Colours
    NAVY   = colors.HexColor("#192D38")
    RED    = colors.HexColor("#3F32F1")
    GOLD   = colors.HexColor("#B9FF00")
    LGREY  = colors.HexColor("#F4F6F9")
    MGREY  = colors.HexColor("#666B73")
    WHITE  = colors.white

    verdict_data = {
        "outstanding": {
            "title": "🏆  GUIDANCE GOD TIER",
            "subtitle": "Outstanding Performance",
            "colour": colors.HexColor("#B9FF00"),
            "text_colour": colors.HexColor("#3a6600"),
            "flavour": "You absolute legend. Chris Hendy himself would shed a single proud tear.\nConsider yourself a fully certified Guidance God — the bridges bow before you."
        },
        "satisfactory": {
            "title": "👍  ADEQUATELY GUIDED",
            "subtitle": "Satisfactory Performance",
            "colour": colors.HexColor("#3F32F1"),
            "text_colour": colors.HexColor("#3F32F1"),
            "flavour": "You've clearly opened at least a few guidance notes in your time.\nNot bad at all — just don't let it go to your head. The bridges are watching."
        },
        "poor": {
            "title": "📚  GUIDANCE NOTE APPRENTICE",
            "subtitle": "Needs Improvement",
            "colour": colors.HexColor("#c0392b"),
            "text_colour": colors.HexColor("#c0392b"),
            "flavour": "Oh dear. The guidance notes are disappointed in you.\nBut every legend has to start somewhere — back to the archives!"
        }
    }
    vd = verdict_data.get(result["verdict"], verdict_data["satisfactory"])

    buf = BytesIO()
    W, H = A4  # 595 x 842 pts

    c = canvas.Canvas(buf, pagesize=A4)

    # --- Navy header band ---
    c.setFillColor(NAVY)
    c.rect(0, H - 110*mm, W, 110*mm, fill=1, stroke=0)

    # Header text - use logo image
    logo_path = os.path.join(os.path.dirname(__file__), "static", "images", "logo_white.png")
    if os.path.exists(logo_path):
        logo_w = 55*mm
        logo_h = 7.5*mm
        c.drawImage(logo_path, W/2 - logo_w/2, H - 34*mm, width=logo_w, height=logo_h,
                    preserveAspectRatio=True, mask="auto")
    else:
        c.setFillColor(WHITE)
        c.setFont("Helvetica-Bold", 26)
        c.drawCentredString(W/2, H - 32*mm, "AtkinsRealis")
    c.setFont("Helvetica", 13)
    c.setFillColor(colors.HexColor("#C4DCE7"))
    c.drawCentredString(W/2, H - 44*mm, "Bridges & Structures  ·  Guidance Notes Quiz")

    # Red accent line
    c.setStrokeColor(colors.HexColor("#3F32F1"))
    c.setLineWidth(3)
    c.line(40*mm, H - 52*mm, W - 40*mm, H - 52*mm)

    # CERTIFICATE OF title
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 32)
    c.drawCentredString(W/2, H - 70*mm, "CERTIFICATE OF ACHIEVEMENT")
    c.setFont("Helvetica", 12)
    c.setFillColor(colors.HexColor("#C4DCE7"))
    c.drawCentredString(W/2, H - 80*mm, "(Official-ish)")

    # --- Body ---
    body_top = H - 120*mm

    # "This certifies that"
    c.setFillColor(MGREY)
    c.setFont("Helvetica", 13)
    c.drawCentredString(W/2, body_top, "This certifies that")

    # Name
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(W/2, body_top - 16*mm, name)

    # Underline name
    name_width = c.stringWidth(name, "Helvetica-Bold", 30)
    c.setStrokeColor(colors.HexColor("#3F32F1"))
    c.setLineWidth(1.5)
    c.line(W/2 - name_width/2, body_top - 18*mm, W/2 + name_width/2, body_top - 18*mm)

    # "has completed"
    c.setFillColor(MGREY)
    c.setFont("Helvetica", 13)
    c.drawCentredString(W/2, body_top - 27*mm, "has completed the")

    # Difficulty
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(W/2, body_top - 36*mm, result["difficulty"] + " Quiz")

    # Score box
    box_y = body_top - 68*mm
    box_w = 80*mm
    box_h = 28*mm
    box_x = W/2 - box_w/2

    c.setFillColor(LGREY)
    c.roundRect(box_x, box_y, box_w, box_h, 4*mm, fill=1, stroke=0)

    c.setFillColor(vd["text_colour"])
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(W/2, box_y + 16*mm, f"{result['pct']}%")
    c.setFillColor(MGREY)
    c.setFont("Helvetica", 11)
    c.drawCentredString(W/2, box_y + 7*mm, f"{result['score']} out of {result['total']} correct")

    # Verdict title
    c.setFillColor(vd["text_colour"])
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(W/2, box_y - 10*mm, vd["title"])

    # Flavour text — split on \n
    c.setFillColor(MGREY)
    c.setFont("Helvetica-Oblique", 11)
    lines = vd["flavour"].split("\n")
    for i, line in enumerate(lines):
        c.drawCentredString(W/2, box_y - 20*mm - i*6*mm, line)

    # Result image
    img_map = {
        "happy.jpg": "happy",
        "satisfied.jpg": "satisfied",
        "angry.jpg": "angry"
    }
    img_path = os.path.join(os.path.dirname(__file__), "static", "images", result["image"])
    if os.path.exists(img_path):
        img_size = 28*mm
        img_x = W/2 - img_size/2
        img_y = box_y - 58*mm
        c.drawImage(img_path, img_x, img_y, width=img_size, height=img_size,
                    preserveAspectRatio=True, mask="auto")

    # --- Footer band ---
    c.setFillColor(NAVY)
    c.rect(0, 0, W, 22*mm, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#C4DCE7"))
    c.setFont("Helvetica", 9)
    c.drawCentredString(W/2, 13*mm, "AtkinsRealis Bridges & Structures Guidance Team")
    c.setFillColor(colors.HexColor("#6688aa"))
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(W/2, 7*mm,
        "This certificate carries absolutely no professional accreditation whatsoever. But we think it looks nice.")

    c.save()
    buf.seek(0)

    safe_name = "".join(c2 for c2 in name if c2.isalnum() or c2 in (" ", "-", "_")).strip() or "Engineer"
    filename = f"GuidanceQuiz_Certificate_{safe_name.replace(' ', '_')}.pdf"

    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
