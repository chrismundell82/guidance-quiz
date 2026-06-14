import os
import random
import json
import psycopg2
import psycopg2.extras
from datetime import datetime
from io import BytesIO
from flask import Flask, render_template, request, jsonify, session, send_file
import pandas as pd

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "guidance-quiz-secret-2024")

EXCEL_PATH = os.path.join(os.path.dirname(__file__), "Guidance_Notes_-_Quiz_Questions.xlsx")
DB_URL = os.environ.get("DATABASE_URL", "")

# Scoring multipliers
DIFF_MULTIPLIER = {"guardian": 1.0, "champion": 1.5, "god": 2.0}
COUNT_MULTIPLIER = {10: 0.8, 20: 1.0, 30: 1.15}
MAX_HOF_ENTRIES = 100


def get_db():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def init_db():
    if not DB_URL:
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hall_of_fame (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        score_pct INTEGER NOT NULL,
                        correct INTEGER NOT NULL,
                        total INTEGER NOT NULL,
                        difficulty TEXT NOT NULL,
                        hof_score REAL NOT NULL,
                        submitted_at TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS questions (
                        id SERIAL PRIMARY KEY,
                        difficulty TEXT NOT NULL,
                        ref TEXT,
                        question TEXT NOT NULL,
                        option_a TEXT NOT NULL,
                        option_b TEXT NOT NULL,
                        option_c TEXT,
                        option_d TEXT,
                        correct_answer CHAR(1) NOT NULL
                    )
                """)
            conn.commit()
        # Seed from Excel if table is empty
        migrate_from_excel()
    except Exception as e:
        print(f"DB init warning: {e}")


def calculate_hof_score(pct, total, difficulty):
    diff_mult = DIFF_MULTIPLIER.get(difficulty, 1.0)
    count_mult = COUNT_MULTIPLIER.get(total, 1.0)
    if total not in COUNT_MULTIPLIER:
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


def migrate_from_excel():
    """Import questions from Excel into DB if questions table is empty."""
    if not DB_URL or not os.path.exists(EXCEL_PATH):
        return
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM questions")
                if cur.fetchone()["count"] > 0:
                    return  # Already seeded

            df = pd.read_excel(EXCEL_PATH, sheet_name="Questions")
            df.columns = df.columns.str.strip()

            # Reverse map: "Guidance Guardian" -> "guardian" etc
            reverse_map = {v: k for k, v in DIFFICULTY_MAP.items()}

            inserted = 0
            with conn.cursor() as cur:
                for _, row in df.iterrows():
                    question_text = str(row.get("Question", "")).strip()
                    if not question_text or question_text.lower() == "nan":
                        continue

                    difficulty_raw = str(row.get("Difficulty", "")).strip()
                    diff_key = reverse_map.get(difficulty_raw)
                    if not diff_key:
                        continue  # Skip rows with unrecognised difficulty

                    answer_raw = str(row.get("Answer", "A")).strip()
                    correct = answer_raw[0].upper() if answer_raw and answer_raw[0].upper() in "ABCD" else "A"

                    opt_a = str(row.get("A", "")).strip()
                    opt_b = str(row.get("B", "")).strip()
                    opt_c = str(row.get("C", "")).strip() or None
                    opt_d = str(row.get("D", "")).strip() or None

                    if not opt_a or not opt_b:
                        continue  # Need at least two options

                    # Clean up "nan" strings
                    if opt_c == "nan": opt_c = None
                    if opt_d == "nan": opt_d = None

                    ref = str(row.get("Ref", "")).strip()
                    if ref == "nan": ref = None

                    cur.execute("""
                        INSERT INTO questions (difficulty, ref, question, option_a, option_b, option_c, option_d, correct_answer)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (diff_key, ref, question_text, opt_a, opt_b, opt_c, opt_d, correct))
                    inserted += 1

            conn.commit()
            print(f"Migrated {inserted} questions from Excel to DB")
    except Exception as e:
        print(f"Migration error: {e}")


def load_questions(difficulty_key):
    # Try DB first, fall back to Excel
    if DB_URL:
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT * FROM questions WHERE difficulty = %s
                    """, (difficulty_key,))
                    rows = cur.fetchall()
            
            questions = []
            for row in rows:
                options = [{"key": "A", "text": row["option_a"]},
                           {"key": "B", "text": row["option_b"]}]
                if row["option_c"]:
                    options.append({"key": "C", "text": row["option_c"]})
                if row["option_d"]:
                    options.append({"key": "D", "text": row["option_d"]})
                questions.append({
                    "question": row["question"],
                    "options": options,
                    "correct": row["correct_answer"],
                    "ref": row["ref"] or "",
                    "id": row["id"]
                })
            return questions
        except Exception as e:
            print(f"DB load_questions error: {e}")

    # Fallback: Excel
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

    OUTSTANDING_MESSAGES = [
        "Outstanding! You absolute legend. Chris Hendy himself would be proud. Consider yourself a true Guidance God in the making! 🏆",
        "Flawless. Are you sure you haven't just memorised the answers? We're watching you. Suspiciously well done.",
        "Top marks! The guidance notes have been read, digested, and apparently tattooed on your brain. Respect.",
        "Extraordinary. We're legally required to inform you that this result may cause insufferable smugness at team meetings.",
        "Perfect score territory. Your colleagues will hate you. Your bridges will love you.",
        "That's the kind of result that gets framed. Seriously, we made a certificate. Use it.",
        "Phenomenal. You've either studied very hard or cheated very cleverly. We choose to believe the former.",
        "You've peaked. This is it. Retirement would be understandable at this point.",
        "Chris Hendy has been notified. He's simultaneously proud and slightly threatened.",
        "Outstanding performance. The guidance notes are weeping tears of joy. Finally, someone read us.",
    ]
    SATISFACTORY_MESSAGES = [
        "Not bad! You clearly read the guidance notes... at least some of them. Room for improvement, but we won't report you to the bridges team. 😏",
        "Solid effort. You're somewhere between 'reads the abstract' and 'actually reads the document'. Progress.",
        "Respectable. Not legendary, but respectable. The bridges are cautiously optimistic about you.",
        "You passed! Which is more than can be said for some people. You know who you are.",
        "Decent score. You've clearly been in enough meetings where someone mentioned the guidance notes. It counts.",
        "Not bad at all. A little more revision and you'll be insufferably confident at your next technical review.",
        "Above average! The bar was on the floor, but you cleared it with style.",
        "Good effort. The guidance notes appreciate being partially remembered. It's more than they usually get.",
        "You're in the 'knows enough to be dangerous' zone. Which, frankly, is where most engineers live.",
        "Satisfactory! A word that has never excited anyone, but here we are. Well done, sort of.",
    ]
    POOR_MESSAGES = [
        "Oh dear. Have you actually read ANY guidance notes? The bridges are judging you right now. Back to the books! 📚",
        "Yikes. The guidance notes are not angry, just deeply disappointed. There's a difference.",
        "That score suggests a fascinating relationship with the concept of preparation. Bold strategy.",
        "The bridges have filed a formal complaint. They expected better from you.",
        "Chris Hendy is staring at this result in silence. That's somehow worse than shouting.",
        "Points for bravery in submitting that. Fewer points for, well, everything else.",
        "The guidance notes have been sitting there this whole time. Unopened, apparently. Sad.",
        "Back to square one! Or rather, back to page one. Of the guidance notes. All of them.",
        "We're not saying you guessed. But the statistical likelihood of this score without guessing is... interesting.",
        "There is nowhere to go but up from here. Silver linings and all that.",
    ]

    if pct >= 80:
        verdict = "outstanding"
        message = random.choice(OUTSTANDING_MESSAGES)
        image = "happy.jpg"
    elif pct >= 50:
        verdict = "satisfactory"
        message = random.choice(SATISFACTORY_MESSAGES)
        image = "satisfied.jpg"
    else:
        verdict = "poor"
        message = random.choice(POOR_MESSAGES)
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

    if not DB_URL:
        return jsonify({"error": "Database not configured"}), 500

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO hall_of_fame (name, score_pct, correct, total, difficulty, hof_score, submitted_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    name,
                    result["pct"],
                    result["score"],
                    result["total"],
                    result["difficulty"],
                    hof_score,
                    datetime.utcnow().strftime("%Y-%m-%d %H:%M")
                ))
                cur.execute("SELECT COUNT(*) FROM hall_of_fame WHERE hof_score > %s", (hof_score,))
                rank = cur.fetchone()["count"] + 1
            conn.commit()

        return jsonify({"success": True, "rank": rank, "hof_score": hof_score})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/hof", methods=["GET"])
def hof_get():
    if not DB_URL:
        return jsonify({"entries": [], "total": 0})

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT name, score_pct, correct, total, difficulty, hof_score, submitted_at
                    FROM hall_of_fame
                    ORDER BY hof_score DESC
                    LIMIT 20
                """)
                rows = cur.fetchall()
                cur.execute("SELECT COUNT(*) FROM hall_of_fame")
                total_entries = cur.fetchone()["count"]

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

    # Strip any emoji/non-latin chars that Helvetica can't render
    import re
    def pdf_safe(text):
        return re.sub(r'[^\x00-\x7F\u00C0-\u024F]', '', text).strip() or "Engineer"

    name = pdf_safe(name)

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

    OUTSTANDING_FLAVOURS = [
        "You absolute legend. Chris Hendy himself would shed a single proud tear.\nConsider yourself a fully certified Guidance God — the bridges bow before you.",
        "Flawless. Suspiciously flawless. We're watching you.\nBut also celebrating you. Mostly celebrating.",
        "Top marks. The guidance notes have never felt so appreciated.\nFrame this certificate. You've earned it.",
        "Peak performance achieved. Your colleagues will be insufferable about this.\nSo will you. That's fine.",
        "Outstanding. This score is going on the fridge.\nAnd the Hall of Fame. And possibly a press release.",
    ]
    SATISFACTORY_FLAVOURS = [
        "You've clearly opened at least a few guidance notes in your time.\nNot bad at all — just don't let it go to your head. The bridges are watching.",
        "Solid effort. Somewhere between 'skimmed it' and 'actually read it'.\nProgress. Slow, but progress.",
        "Above average. The bar was low, but you cleared it.\nWith style, we might add.",
        "Respectable score. The bridges are cautiously optimistic about you.\nDon't let them down.",
        "Not bad! A bit more revision and you'll be dangerously overconfident.\nWhich is the goal, really.",
    ]
    POOR_FLAVOURS = [
        "Oh dear. The guidance notes are disappointed in you.\nBut every legend has to start somewhere — back to the archives!",
        "The bridges have filed a formal complaint.\nWe suggest a thorough re-read before your next attempt.",
        "Yikes. Not angry, just deeply disappointed.\nThere is nowhere to go but up from here.",
        "Bold performance. Very bold.\nThe guidance notes will be here when you're ready to apologise to them.",
        "We're not saying you guessed. But statistically...\nAnyway. The archives are open. Just saying.",
    ]

    outstanding_flavour = random.choice(OUTSTANDING_FLAVOURS)
    satisfactory_flavour = random.choice(SATISFACTORY_FLAVOURS)
    poor_flavour = random.choice(POOR_FLAVOURS)

    verdict_data = {
        "outstanding": {
            "title": "*** GUIDANCE GOD TIER ***",
            "subtitle": "Outstanding Performance",
            "colour": colors.HexColor("#B9FF00"),
            "text_colour": colors.HexColor("#3a6600"),
            "flavour": outstanding_flavour
        },
        "satisfactory": {
            "title": "ADEQUATELY GUIDED",
            "subtitle": "Satisfactory Performance",
            "colour": colors.HexColor("#3F32F1"),
            "text_colour": colors.HexColor("#3F32F1"),
            "flavour": satisfactory_flavour
        },
        "poor": {
            "title": "GUIDANCE NOTE APPRENTICE",
            "subtitle": "Needs Improvement",
            "colour": colors.HexColor("#c0392b"),
            "text_colour": colors.HexColor("#c0392b"),
            "flavour": poor_flavour
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

    # Verdict title — below score box
    c.setFillColor(vd["text_colour"])
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(W/2, box_y - 12*mm, vd["title"])

    # Flavour text — split on \n
    c.setFillColor(MGREY)
    c.setFont("Helvetica-Oblique", 11)
    lines = vd["flavour"].split("\n")
    for i, line in enumerate(lines):
        c.drawCentredString(W/2, box_y - 22*mm - i*7*mm, line)

    # Result image — positioned below ALL text, above footer
    img_path = os.path.join(os.path.dirname(__file__), "static", "images", result["image"])
    if os.path.exists(img_path):
        img_size = 44*mm
        img_x = W/2 - img_size/2
        # Footer is 22mm tall, place image just above it with 8mm gap
        img_y = 22*mm + 8*mm
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


@app.route("/admin/clear-hof", methods=["POST"])
def admin_clear_hof():
    if not admin_required():
        return jsonify({"error": "Unauthorised"}), 401
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM hall_of_fame")
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/admin/export-questions")
def admin_export_questions():
    if not admin_required():
        from flask import redirect, url_for
        return redirect(url_for("admin"))
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM questions ORDER BY difficulty, id")
                rows = cur.fetchall()

        DIFF_DISPLAY = {"guardian": "Guidance Guardian", "champion": "Guidance Champion", "god": "Guidance God"}

        data = []
        for row in rows:
            data.append({
                "Difficulty": DIFF_DISPLAY.get(row["difficulty"], row["difficulty"]),
                "Ref": row["ref"] or "",
                "Question": row["question"],
                "A": row["option_a"],
                "B": row["option_b"],
                "C": row["option_c"] or "",
                "D": row["option_d"] or "",
                "Answer": row["correct_answer"]
            })

        df = pd.DataFrame(data, columns=["Difficulty", "Ref", "Question", "A", "B", "C", "D", "Answer"])

        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Questions", index=False)

            # Auto-size columns
            ws = writer.sheets["Questions"]
            for col in ws.columns:
                max_len = max((len(str(cell.value or "")) for cell in col), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 60)

        buf.seek(0)
        from datetime import date
        filename = f"GuidanceQuiz_Questions_{date.today().strftime('%Y-%m-%d')}.xlsx"
        return send_file(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=filename)
    except Exception as e:
        return f"<p>Export error: {e} <a href='/admin'>Back to admin</a></p>"


@app.route("/admin/migrate")
def admin_migrate():
    if not admin_required():
        from flask import redirect, url_for
        return redirect(url_for("admin"))
    try:
        # Force re-migrate by temporarily clearing and re-seeding
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM questions")
                count_before = cur.fetchone()["count"]
        
        if count_before > 0:
            return f"<p>Already have {count_before} questions in DB. <a href='/admin'>Back to admin</a></p>"
        
        migrate_from_excel()
        
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM questions")
                count_after = cur.fetchone()["count"]
        
        return f"<p>Migration complete! {count_after} questions imported. <a href='/admin'>Back to admin</a></p>"
    except Exception as e:
        return f"<p>Error: {e} <a href='/admin'>Back to admin</a></p>"


@app.route("/admin/force-migrate")
def admin_force_migrate():
    if not admin_required():
        from flask import redirect, url_for
        return redirect(url_for("admin"))
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM questions")
            conn.commit()
        migrate_from_excel()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM questions")
                count = cur.fetchone()["count"]
        return f"<p>Force migration complete! {count} questions imported. <a href='/admin'>Back to admin</a></p>"
    except Exception as e:
        return f"<p>Error: {e} <a href='/admin'>Back to admin</a></p>"


ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")


def admin_required():
    return session.get("admin_logged_in") is True


@app.route("/admin")
def admin():
    if not admin_required():
        return render_template("admin_login.html")
    return render_template("admin.html")


@app.route("/admin/login", methods=["POST"])
def admin_login():
    if request.form.get("password") == ADMIN_PASSWORD:
        session["admin_logged_in"] = True
        return redirect_to_admin()
    return render_template("admin_login.html", error="Wrong password. Nice try.")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    from flask import redirect, url_for
    return redirect(url_for("admin"))


def redirect_to_admin():
    from flask import redirect, url_for
    return redirect(url_for("admin"))


@app.route("/api/admin/questions", methods=["GET"])
def admin_get_questions():
    if not admin_required():
        return jsonify({"error": "Unauthorised"}), 401
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM questions ORDER BY difficulty, id")
                rows = cur.fetchall()
        return jsonify({"questions": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/questions", methods=["POST"])
def admin_add_question():
    if not admin_required():
        return jsonify({"error": "Unauthorised"}), 401
    data = request.json
    required = ["difficulty", "question", "option_a", "option_b", "correct_answer"]
    for f in required:
        if not data.get(f, "").strip():
            return jsonify({"error": f"Field '{f}' is required"}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO questions (difficulty, ref, question, option_a, option_b, option_c, option_d, correct_answer)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """, (
                    data["difficulty"].strip(),
                    data.get("ref", "").strip() or None,
                    data["question"].strip(),
                    data["option_a"].strip(),
                    data["option_b"].strip(),
                    data.get("option_c", "").strip() or None,
                    data.get("option_d", "").strip() or None,
                    data["correct_answer"].strip()[0].upper()
                ))
                new_id = cur.fetchone()["id"]
            conn.commit()
        return jsonify({"success": True, "id": new_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/questions/<int:qid>", methods=["PUT"])
def admin_update_question(qid):
    if not admin_required():
        return jsonify({"error": "Unauthorised"}), 401
    data = request.json
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE questions SET
                        difficulty = %s, ref = %s, question = %s,
                        option_a = %s, option_b = %s, option_c = %s,
                        option_d = %s, correct_answer = %s
                    WHERE id = %s
                """, (
                    data["difficulty"].strip(),
                    data.get("ref", "").strip() or None,
                    data["question"].strip(),
                    data["option_a"].strip(),
                    data["option_b"].strip(),
                    data.get("option_c", "").strip() or None,
                    data.get("option_d", "").strip() or None,
                    data["correct_answer"].strip()[0].upper(),
                    qid
                ))
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/questions/<int:qid>", methods=["DELETE"])
def admin_delete_question(qid):
    if not admin_required():
        return jsonify({"error": "Unauthorised"}), 401
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM questions WHERE id = %s", (qid,))
            conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
