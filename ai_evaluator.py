# ai_evaluator.py
# ----------------------------------------
# OpenAI Chat Completion Wrapper
# Token-safe & Production-ready
# ----------------------------------------

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ----------------------------------------
# OpenAI Client Initialization
# ----------------------------------------
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("❌ OPENAI_API_KEY not found in environment variables")

client = OpenAI(api_key=api_key.strip())
print("✅ OpenAI Client initialized successfully")


# ----------------------------------------
# Utility: Safe text limiter
# ----------------------------------------
def truncate_text(text, max_chars=4000):
    if not text:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n[Text truncated for token safety]"
    return text


# ----------------------------------------
# STEP 1: Resume / JD Summarization
# ----------------------------------------
def summarize_profile(resume_text: str, job_desc: str) -> str:
    """
    Compress resume & job description into a short structured profile
    """

    resume_text = truncate_text(resume_text, 3000)
    job_desc = truncate_text(job_desc, 2000)

    prompt = f"""
You are an expert technical recruiter.

Summarize the candidate profile using the information below.

Resume:
{resume_text if resume_text else "Not provided"}

Job Description:
{job_desc if job_desc else "Not provided"}

Create a concise summary including:
- Key skills
- Experience level
- Domain / role
- Important tools or technologies

Output format:
- Skills:
- Experience:
- Domain:
- Tools:
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You summarize candidate profiles for interviews."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=400
        )

        summary = response.choices[0].message.content.strip()
        print("✅ Profile summarized successfully")
        return summary

    except Exception as e:
        print(f"🔥 ERROR during summarization: {str(e)}")
        raise


# ----------------------------------------
# STEP 2: Generate Interview Questions
# ----------------------------------------
def generate_interview_questions(prompt: str) -> str:
    """
    Generate 5 interview questions using summarized profile
    """

    try:
        print("\n📡 Generating interview questions...")

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert HR interviewer. "
                        "Generate concise, role-specific interview questions."
                    )
                },
                {
                    "role": "user",
                    "content": truncate_text(prompt, 3500)
                }
            ],
            temperature=0.6,
            max_tokens=500
        )

        questions = response.choices[0].message.content.strip()
        print("✅ Questions generated successfully")
        return questions

    except Exception as e:
        print(f"🔥 ERROR generating questions: {str(e)}")
        raise


# ----------------------------------------
# STEP 3: Evaluate Interview Answers
# ----------------------------------------
def evaluate_interview(prompt: str) -> str:
    """
    Evaluate interview transcript and return structured feedback
    """

    try:
        print("\n📡 Evaluating interview responses...")

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert interview evaluator. "
                        "Score candidates professionally and fairly."
                    )
                },
                {
                    "role": "user",
                    "content": truncate_text(prompt, 6000)
                }
            ],
            temperature=0.4,
            max_tokens=900
        )

        evaluation = response.choices[0].message.content.strip()
        print("✅ Interview evaluation completed")
        return evaluation

    except Exception as e:
        print(f"🔥 ERROR during evaluation: {str(e)}")
        raise


# ----------------------------------------
# Test API Connectivity
# ----------------------------------------
def test_connection():
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": "Reply with: API connection successful"}
            ],
            max_tokens=20
        )

        print("✅ API Test:", response.choices[0].message.content.strip())
        return True

    except Exception as e:
        print("❌ API Test Failed:", str(e))
        return False


# ----------------------------------------
# Local Test
# ----------------------------------------
if __name__ == "__main__":
    print("\n==============================")
    print("Testing OpenAI API Connection")
    print("==============================")
    test_connection()
