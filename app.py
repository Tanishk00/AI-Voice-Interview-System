# ----------------------------------------
# AI Voice Interview System - Backend API
# ----------------------------------------

from flask import Flask, request, jsonify, make_response, render_template, abort
from flask import send_from_directory
import re
import fitz
import json
import sqlite3
from flask_cors import CORS
import os
from dotenv import load_dotenv
from datetime import datetime
import smtplib
from email.message import EmailMessage
from ai_evaluator import generate_interview_questions, evaluate_interview

load_dotenv()
RESUME_EMAIL_CACHE = {}
USER_INFO_CACHE = {}

app = Flask(__name__,template_folder="templates")
CORS(app)

# Register JSON parser for Jinja templates
@app.template_filter("fromjson")
def fromjson_filter(value):
    try:
        return json.loads(value)
    except Exception:
        return []


UPLOAD_FOLDER ="uploads"
os.makedirs(UPLOAD_FOLDER,exist_ok=True)
app.config["UPLOAD_FOLDER"]=UPLOAD_FOLDER

# -------------------------------
# Email Validation Configuration
# -------------------------------

DISPOSABLE_EMAIL_DOMAINS = {
    "tempmail.com",
    "10minutemail.com",
    "guerrillamail.com",
    "mailinator.com",
    "yopmail.com",
    "throwawaymail.com",
    "fakeinbox.com",
    "getnada.com",
    "temp-mail.org",
    "trashmail.com"
}

ALLOWED_EMAIL_DOMAINS = {
    "gmail.com"
}


# --------------------------------------------------------------
# Utility: Database connections and scorecard formatter function
# --------------------------------------------------------------

def get_db_connection():
    conn = sqlite3.connect("interview.db")
    conn.row_factory = sqlite3.Row
    return conn


def format_detailed_evaluation(feedback: str) -> str:
    lines = [l.strip() for l in feedback.splitlines() if l.strip()]

    cleaned_lines = []
    skip_patterns = [
        r"^none$",
        r"evaluation of candidate interview",
        r"overall score",
        r"communication\s*:",
        r"confidence\s*:",
        r"technical knowledge\s*:",
        r"grammar\s*:",
        r"answer quality\s*:"
    ]

    for line in lines:
        # Remove markdown ###
        line = re.sub(r"#+\s*", "", line)
        # Remove **bold**
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)

        # Skip only unwanted lines
        if any(re.search(pat, line, re.I) for pat in skip_patterns):
            continue

        cleaned_lines.append(line)

    # Build HTML while keeping SAME email styling
    html = ""

    for line in cleaned_lines:

        lower_line = line.lower()

        # Section Headings
        if lower_line.startswith(("summary", "strength", "areas", "recommend")):
            html += f"<h4 style='margin-top:16px; color:#0f172a;'>{line}</h4>"

        # Bullet Points (if line starts with dash)
        elif line.startswith("-"):
            html += (
                f"<p style='color:#334155; "
                f"margin-left:18px; "
                f"line-height:1.6; "
                f"font-size:14px; "
                f"margin-top:4px;'>"
                f"• {line[1:].strip()}</p>"
            )

        # Normal Paragraph
        else:
            html += (
                f"<p style='color:#334155; "
                f"line-height:1.6; "
                f"font-size:14px; "
                f"margin:4px 0;'>"
                f"{line}</p>"
            )

    return html







# ----------------------------------------------------------
# Utility : Extract text from PDF (Backend-only heavy task)
# ----------------------------------------------------------

def extract_text_from_pdf(file):
    text = ""
    try:
        pdf_bytes = file.read()
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        print("Error extracting PDF text:", str(e))
    return text


def truncate_text(text, max_chars):
    if not text:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n[Content truncated for processing]"
    return text

# -------------------------------
# Email Validation Utilities
# -------------------------------

def is_valid_email_format(email: str) -> bool:
    """
    WHAT: Checks basic email format
    WHY: Prevents abc@gmail, abc@, @gmail.com
    HOW: Regex validation
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return re.match(pattern, email) is not None


def is_disposable_email(email: str) -> bool:
    """
    WHAT: Blocks temporary email providers
    WHY: Prevent fake users & token abuse
    HOW: Domain blacklist
    """
    domain = email.split("@")[-1].lower()
    return domain in DISPOSABLE_EMAIL_DOMAINS


def is_allowed_domain(email: str) -> bool:
    """
    WHAT: Allow only trusted email providers
    WHY: Authentication layer (Phase-1)
    HOW: Whitelist domains (gmail only)
    """
    domain = email.split("@")[-1].lower()
    return domain in ALLOWED_EMAIL_DOMAINS

# defining Function of Sending scorecard to the user email 
def send_email_safely(msg):
    try:
        print("📨 [EMAIL] Connecting to Gmail SMTP...")

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
            smtp.set_debuglevel(1)   # IMPORTANT for logs
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()

            smtp.login(
                os.getenv("EMAIL_USER"),
                os.getenv("EMAIL_APP_PASSWORD")
            )

            smtp.send_message(msg)

        print("✅ [EMAIL] Sent successfully")
        return True

    except Exception as e:
        print("❌ [EMAIL] Failed:", str(e))
        return False



@app.after_request
def after_request(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response


@app.route("/")
def serve_frontend():
    return render_template('index.html')


# -------------------------------
# Serve Uploaded Resumes (Admin Download)
# -------------------------------
@app.route("/uploads/<path:filename>")
def download_resume(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)



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

        user_name = request.form.get("name")
        user_email = request.form.get("email")
        
        #--------------------------------------------
        #   Email Authetication & Validation
        #--------------------------------------------

        if not user_email:
            return jsonify({
                "success":False,
                "error": "Email is required to start the interview."
            }), 400
        
        if not is_valid_email_format(user_email):
            return jsonify({
                "success":False,
                "error":"Please enter a valid email address."
            }), 400
        
        if is_disposable_email(user_email):
            return jsonify({
                "success":False,
                "error":"Temporary or disposable email addresses are not allowed."
            }),400
        
        if not is_allowed_domain(user_email):
            return jsonify({
                "success":False,
                "error":"Only Gmail accounts are allowed to start the interview."
            }),403
        
        if user_name and user_email:
            USER_INFO_CACHE["name"] = user_name
            USER_INFO_CACHE["email"] = user_email

        resume_file = request.files.get("resume")
        if not resume_file:
            return jsonify({"success": False, "error": "Resume file missing "}), 400
        
 
        filename=f"{user_email}_{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        resume_filename= filename
        resume_path= os.path.join(UPLOAD_FOLDER,resume_filename)

        resume_file.save(resume_path)

        with open(resume_path,"rb") as f:
          resume_text = extract_text_from_pdf(f)
          resume_text = truncate_text(resume_text, 3000)
        job_description = truncate_text(request.form.get("job_description", ""), 2000)

        print("RESUME RAW START -----")
        print(resume_text[:800])
        print("RESUME RAW END -----")

        resume_text = resume_text.replace("\u2013", "-").replace("\u2014", "-")
        resume_text = resume_text.replace("\xa0", " ")
        emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', resume_text)
        if emails:
            RESUME_EMAIL_CACHE["resume_email"] = emails[0]

        print("RESUME EMAIL :", RESUME_EMAIL_CACHE.get("resume_email"))

        resume_email = RESUME_EMAIL_CACHE.get("resume_email")
        if resume_email:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO candidates (resume_email, created_at)
                VALUES (?,?)
            """, (resume_email, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            conn.close()

        print("📄 Resume chars:", len(resume_text))
        print("💼 JD chars:", len(job_description))

        # ----------- EXPERIENCE LEVEL DETECTION ------------
        experience_level = "mid"
        jd_lower = job_description.lower()

        if re.search(r'fresher|0\s*[-]?\s*1\s*year|0\s*[-]?\s*2\s*years|intern', jd_lower):
            experience_level = "fresher"

        elif re.search(r'2\s*[-+]?\s*3\s*year|3\s*[-+]?\s*5\s*year', jd_lower):
            experience_level = "mid"

        elif re.search(r'5\s*[-+]?\s*7\s*year|senior|lead|architect', jd_lower):
            experience_level = "senior"

        print("🎯 Detected Experience Level:", experience_level)

        prompt = f"""
You are a professional real-world interviewer conducting a practical interview.

The candidate is a **{experience_level} level experience**.

Your task is to generate EXACTLY 5 interview questions
that follow a **real interview flow** and **controlled difficulty**.

Candidate Information:

Resume:
{resume_text if resume_text else "Not provided"}

Job Description:
{job_description if job_description else "Not provided"}
"""
        
        # Level Specific Instructions
        if experience_level=="fresher":
            level_instruction ="""
STRICT QUESTION STRUCTURE FOR FRESHER (0-1 Years):
1. Introduction: Ask about their introduction, academic background, and a specific project mentioned in their resume.
2-5. Core Concepts: Ask definitions and "how things work" regarding the tech stack in their resume. Complexity should be LOW to MEDIUM. Do not ask system design. Focus on fundamentals (e.g., OOPs, Basic SQL, Data Structures).
"""
        elif experience_level == "mid":
            level_instruction = """
STRICT QUESTION STRUCTURE FOR MID-LEVEL (2-4 Years):
1. Introduction: Ask about their previous role, why they want to switch, and a brief on their contribution to the last company.
2-5. Practical Application: Ask MEDIUM complexity questions. Focus on "Why did you choose this tech?", "What happens if...", and code flow. Focus on real-world scenarios, error handling, and optimization. Do not go deep into complex system architecture yet.
"""
        else: # Senior
            level_instruction = """
STRICT QUESTION STRUCTURE FOR SENIOR (5+ Years):
1. Introduction: Ask about their career progression, major projects that helped the client, and leadership experience.
2-5. Architecture & Design: Ask MEDIUM-HIGH complexity questions. Focus on System Design (mid-level depth), Architecture decisions, Scalability, and impact on business. Ask "How the system works end-to-end".
"""

        final_prompt = prompt + level_instruction + """            


Difficulty Adjustment Rules:
- If experience level is "fresher": ask medium basic and learning-oriented questions
- If experience level is "mid": ask practical and project-depth questions
- If experience level is "senior": ask deeper technical questions but avoid system design unless explicitly required

OUTPUT RULES:
- Output ONLY numbered questions (1 to 5)
- Do not iclude answers.
-Make it sound like a human is asking.
- No explanations, no headings, no extra text
"""

       #---------- LIMIT CHECK OF USER EMAIL ----------
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM interview_results
            WHERE email=?
        """, (USER_INFO_CACHE.get("email"),))
        count = cursor.fetchone()["count"]
        conn.close()

        if count >= 2:
            return jsonify({
                "success": False,
                "error": "Interview limit exceeded . Please get subscription to continue."
            }), 403

        questions_text = generate_interview_questions(prompt)

        lines = [l.strip() for l in questions_text.split("\n") if l.strip()]
        questions = [l.lstrip("0123456789.-) ").strip() for l in lines if len(l) > 10]

        if len(questions) != 5:
            questions = [
                "Tell me about yourself and uour Professional background .",
                "Which skills from your resume are most relevant to this role ?",
                "Explain a technical concept you know well.",
                "Describe a challenging problem you solved.",
                "What are your strengths and areas for improvement ?"
            ]

        print("✅ FINAL QUESTIONS:", questions)
        return jsonify({"success": True, "questions": questions,"resume_filename":resume_filename})

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
        email_sent=False  # Default Value 
        print("\n================ /evaluate HIT ================")
        data = request.get_json()
        resume_path=data.get("resume_path")
        resume_filename = os.path.basename(resume_path) if resume_path else None 
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

Return the result STRICTLY in JSON format with the following structure:

{{
  "overall_score": number,
  "communication": number,
  "confidence": number,
  "technical_knowledge": number,
  "grammar": number,
  "answer_quality": number,
  "summary": "4-5 lines professional evaluation summary",
  
  "strengths": [
    "Detailed strength 1 (minimum 12 words)",
    "Detailed strength 2 (minimum 12 words)",
    "Detailed strength 3 (minimum 12 words)"
   ],

   "areas_for_improvement":[
     "Detailed improvement point 1 (minimum 15 words)",
     "Detailed improvement point 2 (minimum 15 words)",
     "Detailed improvement point 3 (minimum 15 words)",
     "Detailed improvement point 4 (minimum 15 words)"
   
   ],

   "recommendations":[
     "Actionable recommendation 1 (minimum 15 words)",
     "Actionable recommendation 2 (minimum 15 words)",
     "Actionable recommendation 3 (minimum 15 words)",
     "Actionable recommendation 4 (minimum 15 words)"
    ]

}}

IMPORTANT:
- Return only valid JSON
- Do not include markdown
- Do not include explanation outside JSON
"""

        feedback = evaluate_interview(prompt)

        # -------------------------------
        # Parse JSON Safely
        # -------------------------------
        try:
            evaluation_data = json.loads(feedback)
        except Exception as e:
            print("❌ JSON Parsing Error:", e)
            print("Raw Feedback:", feedback)
            return jsonify({
                "success": False,
                "error": "Invalid evaluation format from AI"
            }), 500
        
        # -------------------------------
        # Extract Scores
        # -------------------------------
        

        overall= evaluation_data.get("overall_score",0)
        communication = evaluation_data.get("communication",0)
        confidence = evaluation_data.get("confidence",0)
        technical = evaluation_data.get("technical_knowledge",0)
        grammar= evaluation_data.get("grammar",0)
        answer_quality=evaluation_data.get("answer_quality",0)


        name = USER_INFO_CACHE.get("name")
        email = USER_INFO_CACHE.get("email")
        resume_email = RESUME_EMAIL_CACHE.get("resume_email")

        # -------------------------------
        # Send Email
        # -------------------------------

        if name and email :
            msg = EmailMessage()
            msg['Subject'] = 'Your Interview Evaluation Scorecard'

            EMAIL_USER= os.getenv("EMAIL_USER")
            msg["From"]= f"AI Interview System <{EMAIL_USER}>"
            msg['To'] = email


            score_table_html = f"""
            <table width="100%" cellpadding="10" cellspacing="0"
                   style="border-collapse:collapse; margin:15px 0;">
                <tr style="background:#eef2ff;">
                    <th align="left" style="border:1px solid #e5e7eb;">Metric</th>
                    <th align="center" style="border:1px solid #e5e7eb;">Score</th>
                </tr>
                <tr><td style="border:1px solid #e5e7eb;">Overall Score</td><td align="center" style="border:1px solid #e5e7eb;"><b>{overall} / 10</b></td></tr>
                <tr><td style="border:1px solid #e5e7eb;">Communication</td><td align="center" style="border:1px solid #e5e7eb;">{communication} / 10</td></tr>
                <tr><td style="border:1px solid #e5e7eb;">Confidence</td><td align="center" style="border:1px solid #e5e7eb;">{confidence} / 10</td></tr>
                <tr><td style="border:1px solid #e5e7eb;">Technical Knowledge</td><td align="center" style="border:1px solid #e5e7eb;">{technical} / 10</td></tr>
                <tr><td style="border:1px solid #e5e7eb;">Grammar</td><td align="center" style="border:1px solid #e5e7eb;">{grammar} / 10</td></tr>
                <tr><td style="border:1px solid #e5e7eb;">Answer Quality</td><td align="center" style="border:1px solid #e5e7eb;">{answer_quality} / 10</td></tr>
            </table>
            """

            summary = evaluation_data.get("summary", "")
            strengths = evaluation_data.get("strengths", [])
            areas = evaluation_data.get("areas_for_improvement", [])
            recommendations = evaluation_data.get("recommendations", [])

           


            strengths_text = "\n".join([f"- {s}" for s in strengths])
            areas_text = "\n".join([f"- {a}" for a in areas])
            recommendations_text = "\n".join([f"- {r}" for r in recommendations])

            # Convert JSON into same old text style format
            formatted_text = f"""
Summary:
{summary}

Strengths:
{strengths_text}

Areas for Improvement:
{areas_text}

Recommendations:
{recommendations_text}
"""

            detailed_eval_html = format_detailed_evaluation(formatted_text)

            html_body=f"""
            <html>
            <body style="font-family:Arial,sans-serif; background : #f8fafc; padding:20px;">
                 <div style="max-width:600px; margin:auto ; background : #ffffff; padding:20px; border-radius:10px;">
                      <p>Hi <b>{name}</b>,</p>

                      <p> Thank you for completing the AI-based interview.</p>

                      <h3 style="color:4f46e5;">Interview Scorecard</h3>
                      {score_table_html}
                      
                      <h3>Detailed Evaluation</h3>
                      <div style="background:#f8fafc; padding:14px; border-radius:8px;">
                           {detailed_eval_html}
                      </div>
                      


                    <p> Best regards,<br><b> AI Interview Team</b></p>
                
                </div>
            </body>
            </html>
            """
            msg.set_content(
                "Your interview Scorecard is best viewed in an HTML-compatible email client."
            )
            msg.add_alternative(html_body,subtype="html")
            email_sent = send_email_safely(msg)

            submitted_questions=[a["question"] for a in answers]
            submitted_answers =[a["answer"] for a in answers]

            
            submitted_questions_json = json.dumps(submitted_questions)
            submitted_answers_json =json.dumps(submitted_answers)
            


            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO interview_results (name, email, resume_email, scorecard,submitted_questions,submitted_answers, resume_path ,created_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                name,
                email,
                resume_email,
                json.dumps(evaluation_data),  # Structured JSON
                submitted_questions_json,
                submitted_answers_json,
                resume_filename ,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            conn.close()

        return jsonify({
            "success": True,
            "email_sent":email_sent,
            "evaluation": evaluation_data
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/send-scorecard', methods=["POST"])
def send_scorecard():
    return jsonify({"success": True})

# -------------------------------------
# Admin Panel - View Interviewee Information
# -------------------------------------

@app.route("/admin/candidates")
def admin_candidates():
    admin_key = request.args.get("key")
    if admin_key != os.getenv("ADMIN_SECRET_KEY"):
        abort(403)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, resume_email, created_at
        FROM candidates
        ORDER BY created_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    return render_template("admin_candidates.html", candidates=rows)


@app.route("/admin")
def admin_panel():
    admin_key = request.args.get("key")
    if admin_key != os.getenv("ADMIN_SECRET_KEY"):
        abort(403)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, email, resume_email,scorecard, submitted_questions,submitted_answers,resume_path,created_at
        FROM interview_results
        ORDER BY created_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()

    return render_template("admin.html", results=rows)


# -------------------------------
# Run Server
# -------------------------------

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
