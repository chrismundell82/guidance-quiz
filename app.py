import os
import random
import json
import smtplib
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from flask import Flask, render_template, request, jsonify, session
import pandas as pd

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "guidance-quiz-secret-2024")

EXCEL_PATH = os.path.join(os.path.dirname(__file__), "Guidance_Notes_-_Quiz_Questions.xlsx")

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

    session["last_result"] = {
        "score": correct_count,
        "total": total,
        "pct": pct,
        "verdict": verdict,
        "message": message,
        "image": image,
        "difficulty": DIFFICULTY_LABELS.get(difficulty, difficulty)
    }

    return jsonify({
        "score": correct_count,
        "total": total,
        "pct": pct,
        "verdict": verdict,
        "message": message,
        "image": image,
        "difficulty": DIFFICULTY_LABELS.get(difficulty, difficulty),
        "results": results
    })


@app.route("/api/send-certificate", methods=["POST"])
def send_certificate():
    data = request.json
    email = data.get("email", "").strip()
    name = data.get("name", "Engineer").strip()

    result = session.get("last_result")
    if not result or not email:
        return jsonify({"error": "Missing data"}), 400

    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    from_email = os.environ.get("FROM_EMAIL", smtp_user)

    if not smtp_host or not smtp_user:
        return jsonify({"error": "Email not configured on server"}), 500

    # Build HTML email
    verdict_phrases = {
        "outstanding": "a certified Guidance God",
        "satisfactory": "showing satisfactory guidance awareness",
        "poor": "in urgent need of guidance note revision"
    }
    phrase = verdict_phrases.get(result["verdict"], "")

    html_body = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; background: #f5f5f5; padding: 20px;">
      <div style="background: #002147; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
        <h1 style="color: #fff; font-size: 22px; margin: 0;">AtkinsRéalis Guidance Notes Quiz</h1>
        <p style="color: #ccc; margin: 5px 0 0;">Official(ish) Certificate of Achievement</p>
      </div>
      <div style="background: #fff; padding: 30px; border-radius: 0 0 8px 8px; border: 1px solid #ddd;">
        <h2 style="color: #002147;">Dear {name},</h2>
        <p style="font-size: 16px;">This is to certify that you completed the <strong>{result['difficulty']}</strong> level quiz and scored:</p>
        <div style="text-align: center; background: #f0f4f8; border-radius: 8px; padding: 20px; margin: 20px 0;">
          <span style="font-size: 48px; font-weight: bold; color: #002147;">{result['pct']}%</span>
          <p style="font-size: 18px; color: #555; margin: 5px 0;">{result['score']} out of {result['total']} correct</p>
        </div>
        <p style="font-size: 16px; color: #444;">{result['message']}</p>
        <p style="font-size: 14px; color: #888; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">
          AtkinsRéalis Bridges & Structures Guidance Team<br>
          <em>This certificate carries absolutely no professional accreditation whatsoever. But we think it looks nice.</em>
        </p>
      </div>
    </body></html>
    """

    try:
        msg = MIMEMultipart("related")
        msg["Subject"] = f"Your AtkinsRéalis Guidance Quiz Certificate — {result['pct']}%!"
        msg["From"] = from_email
        msg["To"] = email

        msg_alt = MIMEMultipart("alternative")
        msg.attach(msg_alt)
        msg_alt.attach(MIMEText(html_body, "html"))

        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, email, msg.as_string())
        server.quit()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
