import os
import json
from groq import Groq

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ---------------- QUESTION GENERATION ----------------

def generate_ai_question(skill, level, prev_answer=None, asked_questions=None):
    asked_questions = asked_questions or []

    system_prompt = f"""
You are an AI technical interviewer.

Ask ONE interview question strictly related to the skill: "{skill}".
Difficulty level: {level}.

Rules:
- Ask only about the given skill
- Do NOT repeat previous questions
- Keep it short and clear
- Return ONLY the question text
"""

    user_prompt = f"""
Previous questions:
{asked_questions}

Previous answer:
{prev_answer}
"""

    chat = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
    )

    return chat.choices[0].message.content.strip()


# ---------------- ANSWER EVALUATION ----------------

def evaluate_answer(skill, question, answer, interview_type="resume"):
    system_prompt = f"""
You are an expert interviewer evaluating a candidate's answer.

Interview Type: {interview_type}
Skill: {skill}
Question: {question}

Give:
- score (0 to 5)
- strengths
- weaknesses
- suggestion

Return ONLY JSON:
{{
  "score": <number>,
  "strengths": "<text>",
  "weaknesses": "<text>",
  "suggestion": "<text>"
}}
"""

    user_prompt = f"Answer:\n{answer}"

    try:
        chat = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )

        raw = chat.choices[0].message.content.strip()

        # 🔥 CLEAN ```json BLOCK
        if raw.startswith("```"):
            raw = raw.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(raw)
        except Exception:
            print("❌ JSON ERROR:", raw)
            data = {}

        score = int(data.get("score", 0))
        score = max(0, min(score, 5))

        return {
            "score": score,
            "strengths": data.get("strengths", "").strip(),
            "weaknesses": data.get("weaknesses", "").strip(),
            "suggestion": data.get("suggestion", "").strip()
        }

    except Exception as e:
        print("❌ API ERROR:", e)
        return {
            "score": 0,
            "strengths": "",
            "weaknesses": "",
            "suggestion": ""
        }


        # ---------------- CORRECT ANSWER ----------------

def generate_correct_answer_with_explanation(skill, question):
    system_prompt = f"""
You are an expert.

Give:
Correct Answer (1-2 lines)
Explanation (2-3 lines)

Format:
Correct Answer: ...
Explanation: ...
"""
    user_prompt = f"Skill: {skill}\nQuestion: {question}"

    chat = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    return chat.choices[0].message.content.strip()


# ---------------- RESUME QUESTION ----------------

def generate_resume_based_question(resume_text, prev_answer=None, asked_questions=None, difficulty="beginner"):
    asked_questions = asked_questions or []

    system_prompt = f"""
You are an interviewer.

Difficulty: {difficulty}

Ask question based on resume.
Do NOT repeat.
Return ONLY question.
"""

    user_prompt = f"""
Resume:
{resume_text}

Previous:
{asked_questions}
"""

    chat = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )

    return chat.choices[0].message.content.strip()


# ---------------- HR QUESTION ----------------

def generate_hr_question(prev_answer=None, asked_questions=None, difficulty="beginner"):
    asked_questions = asked_questions or []

    system_prompt = f"""
You are an HR interviewer.

Difficulty: {difficulty}

Ask simple HR question.
Do NOT repeat.
Return ONLY question.
"""

    user_prompt = f"""
Previous:
{asked_questions}
"""

    chat = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.5,
    )

    return chat.choices[0].message.content.strip()


# ---------------- PERFORMANCE ----------------

def evaluate_performance_ai(all_answers_text: str):

    length = len(all_answers_text.split())

    confidence = min(100, max(40, length // 5))
    clarity = min(100, max(35, length // 6))
    communication = min(100, max(45, length // 4))

    overall = int((confidence + clarity + communication) / 3)

    feedback = []

    if clarity < 60:
        feedback.append("Improve clarity by structuring answers.")
    else:
        feedback.append("Good clarity.")

    if confidence < 60:
        feedback.append("Add more confidence.")
    else:
        feedback.append("Confidence is good.")

    if communication < 60:
        feedback.append("Improve communication.")
    else:
        feedback.append("Good communication.")

    return {
         "overall": overall,
        "confidence": confidence,
        "clarity": clarity,
        "communication": communication,
        "feedback": feedback
    }
# ---------------- CODING QUESTION ----------------

def generate_coding_question(skill, level):
    system_prompt = f"""
You are a coding interviewer.

Generate ONE coding problem.

Skill: {skill}
Difficulty: {level}

STRICT RULES:
- Must be a coding problem
- Must be related to {skill}
- Do NOT say "beginner question on python"
- Do NOT give generic text

FORMAT:

Problem:
<problem>

Example:
Input: ...
Output: ...
"""

    chat = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt}
        ],
        temperature=0.8,
    )

    return chat.choices[0].message.content.strip()
def evaluate_coding_answer(skill, question, code):

    system_prompt = f"""
You are a coding expert.

Your job is to provide ONLY the correct working code.

STRICT RULES:
- Do NOT explain anything
- Do NOT give feedback
- Do NOT add headings
- ONLY return correct code
- Code must be complete and working

Question:
{question}
"""

    chat = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt}
        ],
        temperature=0.2,
   )

    return chat.choices[0].message.content.strip()
from groq import Groq
import os

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def generate_questions(role):

    system_prompt = f"""
You are a strict interviewer.

Generate exactly 5 interview questions for {role}.

RULES:
- Only questions
- No headings
- No explanations
- No numbering
- Each line one question
"""

    chat = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt}
        ],
        temperature=1.0,
    )

    text = chat.choices[0].message.content.strip().split("\n")

    questions = []

    for q in text:
        q = q.strip()

        if not q:
            continue

        q = q.lstrip("1234567890. ").strip()
        questions.append(q)

    return questions[:5]
def generate_test_cases(question):
    prompt = f"""
Generate 3 test cases for this coding problem.

Rules:
- Only input and expected output
- Format strictly like this:

Input: <input>
Output: <output>

Question:
{question}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    return response.choices[0].message.content.strip()
def generate_solution(question):
    prompt = f"""
Give ONLY correct Python code for this problem.

Rules:
- No explanation
- Only code
- Must be correct and working

Question:
{question}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    return response.choices[0].message.content.strip()