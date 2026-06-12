import os
import random
import json
import urllib.request
import urllib.error
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

    resend_key = os.environ.get("RESEND_API_KEY", "")
    from_email = os.environ.get("FROM_EMAIL", "onboarding@resend.dev")

    if not resend_key:
        return jsonify({"error": "Email not configured on server"}), 500

    verdict_titles = {
        "outstanding": "🏆 Guidance God Tier",
        "satisfactory": "👍 Adequately Guided",
        "poor": "📚 Guidance Note Apprentice"
    }
    title = verdict_titles.get(result["verdict"], "Quiz Complete")

    html_body = f"""
    <html><body style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; background: #f4f6f9; padding: 20px;">
      <div style="background: #002147; padding: 24px 28px; text-align: center; border-radius: 10px 10px 0 0;">
        <h1 style="color: #ffffff; font-size: 20px; margin: 0; letter-spacing: 1px;">AtkinsRéalis</h1>
        <p style="color: rgba(255,255,255,0.7); margin: 6px 0 0; font-size: 13px;">Bridges &amp; Structures · Guidance Notes Quiz</p>
      </div>
      <div style="background: #ffffff; padding: 32px 28px; border-radius: 0 0 10px 10px; border: 1px solid #e0e4ea; border-top: none;">
        <p style="font-size: 13px; color: #E4002B; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; margin: 0 0 10px;">{title}</p>
        <h2 style="color: #002147; font-size: 22px; margin: 0 0 20px;">Dear {name},</h2>
        <p style="font-size: 15px; color: #444; line-height: 1.6;">
          This is to certify that you completed the <strong>{result['difficulty']}</strong> level quiz with the following result:
        </p>
        <div style="text-align: center; background: #f0f4f8; border-radius: 10px; padding: 24px; margin: 24px 0;">
          <div style="font-size: 60px; font-weight: 700; color: #002147; line-height: 1;">{result['pct']}%</div>
          <div style="font-size: 17px; color: #555; margin-top: 8px;">{result['score']} out of {result['total']} correct</div>
        </div>
        <p style="font-size: 15px; color: #444; line-height: 1.6; font-style: italic;">"{result['message']}"</p>
        <div style="margin-top: 32px; padding-top: 20px; border-top: 1px solid #eee;">
          <p style="font-size: 13px; color: #999; line-height: 1.6; margin: 0;">
            AtkinsRéalis Bridges &amp; Structures Guidance Team<br>
            <em>This certificate carries absolutely no professional accreditation whatsoever.<br>
            But it does prove you had 10 minutes to spare, which is something.</em>
          </p>
        </div>
      </div>
    </body></html>
    """

    payload = json.dumps({
        "from": "AtkinsRéalis Guidance Quiz <onboarding@resend.dev>",
        "to": [email],
        "subject": f"Your Guidance Notes Quiz Certificate — {result['pct']}% ({result['difficulty']})",
        "html": html_body
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {resend_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 202):
                return jsonify({"success": True})
            else:
                return jsonify({"error": f"SendGrid returned {resp.status}"}), 500
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        return jsonify({"error": f"SendGrid error {e.code}: {body}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
