# app.py
# ----------------------------------------
# AI Voice Interview System - Backend API
# ----------------------------------------

from flask import Flask, request, jsonify, make_response
from flask import send_from_directory

from flask_cors import CORS
import os
from dotenv import load_dotenv
from datetime import datetime
import smtplib
from email.message import EmailMessage
from ai_evaluator import generate_interview_questions, evaluate_interview

load_dotenv()

app = Flask(__name__)
CORS(app)


# -------------------------------
# Utility: Limit text size
# -------------------------------
def truncate_text(text, max_chars):
    if not text:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n[Content truncated for processing]"
    return text


@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

@app.route("/")
def serve_frontend():
    return send_from_directory('.', 'index.html')

# -------------------------------
# Health Check
# -------------------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "api_key": "configured" if os.getenv("OPENAI_API_KEY") else "missing"
    })


# -------------------------------
# Generate Interview Questions
# -------------------------------
@app.route("/generate-questions", methods=["POST", "OPTIONS"])
def generate_questions():
    if request.method == "OPTIONS":
        return make_response("", 200)

    try:
        print("\n================ /generate-questions HIT ================")
        data = request.get_json()
        resume = truncate_text(data.get("resume", ""), 3000)
        job_description = truncate_text(data.get("job_description", ""), 2000)
        print("📄 Resume chars:", len(resume))
        print("💼 JD chars:", len(job_description))

        prompt = f"""
You are an expert HR interviewer.
Usinng the candidate profile below,
Generate EXACTLY 5 interview questions based on:

Resume:
{resume if resume else "Not provided"}

Job Description:
{job_description if job_description else "Not provided"}

Rules:
- Questions must be role-specific
- Avoid repeating resume lines
- Mix HR + Technical + Problem solving
- Output only numbered questions (1-5)
"""

        questions_text = generate_interview_questions(prompt)

        # Clean and parse questions
        lines = [l.strip() for l in questions_text.split("\n") if l.strip()]
        questions = [l.lstrip("0123456789.-) ").strip() for l in lines if len(l) > 10]
        
        # Fallback Safety
        if len(questions) != 5:
            questions = [
                "Tell me about yourself and uour Professional background .",
                "Which skills from your resume are most relevant to this role ?",
                "Explain a technical concept you know well.",
                "Describe a challenging problem you solved.",
                "What are your strengths and areas for improvement ?"
            ]

        print("✅ FINAL QUESTIONS:", questions)
        return jsonify({"success": True, "questions": questions})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# -------------------------------
# Evaluate Interview Answers
# -------------------------------
@app.route("/evaluate", methods=["POST", "OPTIONS"])
def evaluate():
    if request.method == "OPTIONS":
        return make_response("", 200)

    try:
        print("\n================ /evaluate HIT ================")
        data = request.get_json()
        answers = data.get("answers", [])

        transcript = ""
        for i, ans in enumerate(answers, start=1):
            transcript += f"""
Question {i}: {ans['question']}
Answer: {ans['answer']}
Word Count: {ans['word_count']}
---
"""

        transcript = truncate_text(transcript, 6000)

        prompt = f"""
You are an expert interview evaluator.

Evaluate the interview transcript below and score the candidate.

Transcript:
{transcript}

Provide:
- Overall Score (0-10)
- Communication(0-10)
- Confidence (0-10)
- Technical Knowledge(0-10)
- Grammar(0-10)
- Answer Quality(0-10)
- Summary (2 -3 lines)
- Strengths (3 points)
- Areas for Improvement (3 points)
- Recommendations (3 actionalble steps)

Use clear headings  and  bullet points.
"""

        feedback = evaluate_interview(prompt)

        return jsonify({
            "success": True,
            "evaluation": {"raw_feedback": feedback}
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/send-scorecard',methods=["POST"])
def send_scorecard():
    data=request.get_json()
    name = data.get("name")
    email=data.get("email")
    scorecard=data.get("scorecard")

    if not name or not email or not scorecard:
        return jsonify({"error":"Missing data"}),400
    msg = EmailMessage()
    msg['Subject'] = 'Your AI Interview Scorecard'
    msg['From'] = os.getenv("EMAIL_USER")
    msg['To'] = email

    msg.set_content(f"""
Hi {name},

Thank you for completing the AI Interview.

Here is your scorecard:

{scorecard}

Best regards,
AI Interview System
""")
    with smtplib.SMTP_SSL('smtp.gmail.com',465) as smtp:
        smtp.login(
            os.getenv("EMAIL_USER"),
            os.getenv("EMAIL_APP_PASSWORD")
        )
        smtp.send_message(msg)

        return jsonify({"success":True,"message": "Scorecard enailed successfully "})   
    
    
# -------------------------------
# Run Server
# -------------------------------
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
