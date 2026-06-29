import os
from datetime import timedelta
import logging
logger = logging.getLogger(__name__)

import re
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from .models import AskedQuestion, Streak, PracticeDay, VideoRecording, VoiceRecording, InterviewAnswer
from .ai import generate_ai_question, evaluate_answer, generate_correct_answer_with_explanation
from .ai import generate_resume_based_question
from datetime import date
from .ai import generate_hr_question


def login_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('login_success')
        return render(request, 'login.html', {'error': 'Invalid username or password'})
    return render(request, 'login.html')


def register_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')

        if password != confirm_password:
            return render(request, 'register.html', {'error': 'Passwords do not match'})

        try:
            validate_email(email)
        except ValidationError:
            return render(request, 'register.html', {'error': 'Invalid email'})

        if User.objects.filter(username=username).exists():
            return render(request, 'register.html', {'error': 'Username already exists'})

        if User.objects.filter(email=email).exists():
            return render(request, 'register.html', {'error': 'Email already registered'})

        User.objects.create_user(username=username, email=email, password=password)
        return redirect('register_success')

    return render(request, 'register.html')


@login_required(login_url='login')
def dashboard(request):
    streak, _ = Streak.objects.get_or_create(user=request.user)
    return render(request, 'dashboard.html',{
      "current_streak": streak.current_streak,
      "longest_streak": streak.longest_streak,
   })  
    


def logout_view(request):
    logout(request)
    return redirect('login')


def login_success_view(request):
    return render(request, 'login_success.html')


def register_success_view(request):
    return render(request, 'register_success.html')


def home_view(request):
    return redirect('login')


# ---------------- SKILLS & SETUP ----------------

@login_required
def skills_view(request):
    return render(request, 'skills.html')


@login_required
def setup_view(request):
    skills = request.GET.get("skills", "")
    skills_list = skills.split(",") if skills else []

    if request.method == "POST":
        level = request.POST.get("level")
        mode = request.POST.get("mode")   # chat / voice / video

        request.session["level"] = level
        request.session["mode"] = mode
        request.session["skills"] = skills_list

        first_skill = skills_list[0] if skills_list else "Python"

        # 🔥 Redirect based on selected mode
        if mode == "chat":
            return redirect(f"/chat-interview/?skills={first_skill}&level={level}")
        elif mode == "voice":
            return redirect("/voice/")
        elif mode == "video":
            return redirect("/video/")
        else:
            return redirect(f"/chat-interview/?skills={first_skill}&level={level}")

    return render(request, "setup.html", {"skills": skills_list})

    # ---------------- CHAT INTERVIEW ----------------

@login_required
def chat_interview_view(request):
    skill = request.GET.get("skills")
    level = request.GET.get("level", "beginner")

    # 🔥 GET TIMER VALUES FROM URL
    timer_enabled = request.GET.get("timer", "off")
    time_limit = request.GET.get("time_limit", 60)

    # 🔥 CLEAR PREVIOUS QUESTIONS
    AskedQuestion.objects.filter(
        user=request.user,
        skill=skill,
        level=level
    ).delete()

    context = {
        "skills": skill,
        "level": level,
        "timer_enabled": timer_enabled,   # ✅ ADD THIS
        "time_limit": time_limit          # ✅ ADD THIS
    }

    return render(request, "chat_interview.html", context)


# ---------------- NEXT QUESTION API ----------------

@csrf_exempt
@login_required
def get_next_question(request):
    if request.method == "POST":
        skill = request.POST.get("skill")
        level = request.POST.get("level")
        prev_answer = request.POST.get("answer", "")
        prev_question = request.POST.get("prev_question", "")
        limit = request.POST.get("limit")
        mode = request.POST.get("mode", "normal")

        # 1) Evaluate previous answer
        if prev_answer and prev_question:
            eval_result = evaluate_answer(skill, prev_question, prev_answer)
            score = eval_result.get("score", 0)
            strengths = eval_result.get("strengths", "")
            weaknesses = eval_result.get("weaknesses", "")
            suggestion = eval_result.get("suggestion", "")

            feedback = f"Strengths: {strengths}\nWeaknesses: {weaknesses}\nSuggestion: {suggestion}"

            correct_answer = ""
            explanation = ""

            if score < 3:
                ca_text = generate_correct_answer_with_explanation(skill, prev_question)
                for line in ca_text.splitlines():
                    if line.lower().startswith("correct answer"):
                        correct_answer = line.split(":", 1)[-1].strip()
                    elif line.lower().startswith("explanation"):
                        explanation = line.split(":", 1)[-1].strip()

            InterviewAnswer.objects.create(
                user=request.user,
                skill=skill,
                level=level,
                question_text=prev_question,
                user_answer=prev_answer,
                score=score,
                feedback=feedback,
                correct_answer=correct_answer,
                explanation=explanation
            )
            
        # 2) Count asked questions BEFORE generating next one
        asked_count = AskedQuestion.objects.filter(
             user=request.user, skill=skill, level=level
        ).count()
        # 3) Daily limit check + streak update (🔥 FIXED)

        if limit:
            try:
               limit = int(limit)

               if asked_count >= limit:
                  if mode == "streak":
                     mark_today_practice_completed(request.user)

                  return JsonResponse({
                      "done": True,
                      "streak":mode == "streak"})

            except:
                pass
        # 3) Avoid repeats
        asked = AskedQuestion.objects.filter(
            user=request.user, skill=skill, level=level
        ).values_list("question_text", flat=True)

        # 4) Generate next question
        question = generate_ai_question(skill, level, prev_answer, list(asked))

        AskedQuestion.objects.create(
            user=request.user,
            skill=skill,
            level=level,
            question_text=question
        )

        return JsonResponse({"question": question})

    return JsonResponse({"error": "Invalid request"}, status=400)


                            # ---------------- SUMMARY ----------------

@login_required
def interview_summary(request):
    answers = InterviewAnswer.objects.filter(user=request.user).order_by("created_at")
    return render(request, "interview_summary.html", {"answers": answers})


# ---------------- OTHER PAGES ----------------

@login_required
def result_view(request):
    return render(request, "result.html")

@login_required
def video_practice(request):

    skills = request.GET.get("skills", "")
    level = request.GET.get("level", "beginner")
    timer = request.GET.get("timer", "off")
    time_limit = request.GET.get("time_limit", "60")

    # session safety
    if "question_source" not in request.session:
        request.session["question_source"] = "skills"

    context = {
        "skills": skills,
        "level": level,
        "timer": timer,
        "time_limit": time_limit
    }

    return render(request, 'video.html', context)

@login_required
def voice_analysis(request):
    skill = request.GET.get("skills")
    level = request.GET.get("level", "beginner")

    # 🔥 IMPORTANT
    timer_enabled = request.GET.get("timer", "off")
    time_limit = request.GET.get("time_limit", 60)

    return render(request, 'voice.html', {
        "skills": skill,
        "level": level,
        "timer_enabled": timer_enabled,
        "time_limit": time_limit
    })

@login_required
def performance(request):
    context = {
        "score": 78,
        "confidence": 72,
        "clarity": 81,
        "communication": 75,
        "feedback": [
            "Good clarity in most answers.",
            "Try to reduce filler words.",
            "Maintain eye contact during video responses.",
        ]
    }
    return render(request, 'performance.html', context)


# ---------------- RESUME BASED ----------------

@login_required
def resume_upload(request):
    if request.method == "POST" and request.FILES.get("resume"):
        resume_file = request.FILES["resume"]
        level = request.POST.get("level", "beginner")
        interview_type = request.POST.get("interview_type", "resume")
        mode = request.POST.get("mode", "chat")  # 🔥 chat / voice / video

        upload_dir = os.path.join(settings.MEDIA_ROOT, "resumes")
        os.makedirs(upload_dir, exist_ok=True)

        fs = FileSystemStorage(location=upload_dir)
        filename = fs.save(resume_file.name, resume_file)

        request.session["resume_path"] = os.path.join(upload_dir, filename)
        request.session["resume_q_count"] = 0
        request.session["resume_active"] = True
        request.session["resume_level"] = level
        request.session["resume_type"] = interview_type
        request.session["resume_mode"] = mode  # 🔥 save mode
        request.session["question_source"] = "resume"   # 🔥 resume-based questions
        request.session["input_mode"] = mode            # chat / voice / video
        # 🔀 Redirect based on selected mode
        if mode == "chat":
            return redirect("resume_chat_interview")
        elif mode == "voice":
            return redirect("voice_analysis")     # existing voice page
        elif mode == "video":
            return redirect("video_practice")    # existing video page
        else:
            return redirect("resume_chat_interview")

    return render(request, "resume_upload.html")


@login_required
def resume_chat_interview(request):
    return render(request, "resume_interview.html")


# ---------------- ROLE BASED ----------------

@login_required
def role_select(request):
    if request.method == "POST":
        return redirect('real_interview')
    return render(request, 'role_select.html')


@login_required
def real_interview_view(request):
    request.session["question_source"] = "hr"   # HR-based
    return render(request, 'real_interview.html')


# ---------------- STREAK ----------------

@login_required
def streak_view(request):
    streak_obj, _ = Streak.objects.get_or_create(user=request.user)
    return render(request, "streak.html", {
"current_streak": streak_obj.current_streak,
"longest_streak": streak_obj.longest_streak,
})


# ---------------- VIDEO RECORDINGS ----------------

@csrf_exempt
@login_required
def upload_recording(request):
    if request.method == "POST" and request.FILES.get("video"):
        vr = VideoRecording.objects.create(
            user=request.user,
            file=request.FILES["video"],
            confidence=75,
            speech_speed=68,
            pauses=62,
        )
        return JsonResponse({"ok": True, "url": vr.file.url})
    return JsonResponse({"ok": False, "error": "No video received"}, status=400)


@login_required
def my_recordings(request):
    recordings = VideoRecording.objects.filter(user=request.user).order_by('-created_at')
    return render(request, "my_recordings.html", {"recordings": recordings})


@login_required
def delete_recording(request, rid):
    rec = get_object_or_404(VideoRecording, id=rid, user=request.user)
    rec.file.delete(save=False)
    rec.delete()
    return redirect('my_recordings')


# ---------------- VOICE RECORDINGS ----------------

@csrf_exempt
@login_required
def upload_voice(request):
    if request.method == "POST" and request.FILES.get("audio"):
        vr = VoiceRecording.objects.create(
            user=request.user,
            file=request.FILES["audio"],
            clarity=70,
            speech_speed=65,
            confidence=75,
        )
        return JsonResponse({"ok": True, "url": vr.file.url})
    return JsonResponse({"ok": False, "error": "No audio received"}, status=400)


@login_required
def my_voice_recordings(request):
    recordings = VoiceRecording.objects.filter(user=request.user).order_by('-created_at')
    return render(request, "my_voice_recordings.html", {"recordings": recordings})


@login_required
def delete_voice_recording(request, rid):
    r = get_object_or_404(VoiceRecording, id=rid, user=request.user)
    r.file.delete(save=False)
    r.delete()
    return redirect("my_voice_recordings")
def mark_today_practice_completed(user):
    logger.warning("🔥 mark_today_practice_completed CALLED for user=%s", user.username)
    today = date.today()
    yesterday = today - timedelta(days=1)

    # PracticeDay update/create
    practice, created = PracticeDay.objects.get_or_create(
        user=user,
        date=today,
        defaults={"completed": True}
    )

    # If already completed today, do nothing
    if not created and practice.completed:
        return

    practice.completed = True
    practice.save()

    # Get or create streak
    streak, _ = Streak.objects.get_or_create(user=user)

    # Check yesterday completion
    yesterday_done = PracticeDay.objects.filter(
        user=user, date=yesterday, completed=True
    ).exists()

    if yesterday_done:
        streak.current_streak += 1
    else:
        streak.current_streak = 1

    # Update longest streak
    if streak.current_streak > streak.longest_streak:
        streak.longest_streak = streak.current_streak

    streak.last_completed_date = today
    streak.save()
@csrf_exempt
@login_required
def complete_today_practice(request):
    today = date.today()
    yesterday = today - timedelta(days=1)

    practice, _ = PracticeDay.objects.get_or_create(user=request.user, date=today)
    practice.completed = True
    practice.save()

    streak, _ = Streak.objects.get_or_create(user=request.user)

    yesterday_done = PracticeDay.objects.filter(
        user=request.user, date=yesterday, completed=True
    ).exists()

    if yesterday_done:
        streak.current_streak += 1
    else:
        streak.current_streak = 1

    streak.longest_streak = max(streak.longest_streak, streak.current_streak)
    streak.last_completed_date = today
    streak.save()

    return JsonResponse({"ok": True, "current_streak": streak.current_streak})
import pdfplumber
from docx import Document

def extract_resume_text(file_path):
    text = ""
    if file_path.endswith(".pdf"):
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    elif file_path.endswith(".docx"):
        doc = Document(file_path)
        for p in doc.paragraphs:
            text += p.text + "\n"
    return text
@csrf_exempt
@login_required
def get_next_resume_question(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid request"}, status=400)

    prev_answer = request.POST.get("answer", "")
    prev_question = request.POST.get("prev_question", "")

    resume_path = request.session.get("resume_path")
    if not resume_path:
        return JsonResponse({"error": "Resume not found"}, status=400)

    resume_text = extract_resume_text(resume_path)

    # ✅ Evaluate previous answer
    if prev_question:
        eval_result = evaluate_answer("resume", prev_question, prev_answer)

        feedback = {
            "score": eval_result.get("score", 0),
            "strengths": eval_result.get("strengths", eval_result.get("feedback", "Good attempt")),
            "weaknesses": eval_result.get("weaknesses", "Could add more concrete examples."),
            "suggestion": eval_result.get("suggestion", "Try mentioning tools, impact, and outcomes.")
        }

        ca_text = generate_correct_answer_with_explanation("resume", prev_question)

        answer_part = ""
        explanation_part = ""
        for line in ca_text.splitlines():
            if line.lower().startswith("correct answer"):
                answer_part = line.split(":", 1)[-1].strip()
            elif line.lower().startswith("explanation"):
                explanation_part = line.split(":", 1)[-1].strip()

        # 🔥 Combine full feedback text
        full_feedback_text = (
            f"Strengths: {feedback['strengths']}\n"
            f"Weaknesses: {feedback['weaknesses']}\n"
            f"Suggestion: {feedback['suggestion']}"
        )

        InterviewAnswer.objects.create(
            user=request.user,
            skill="resume",
            level=request.session.get("resume_level", "beginner"),
            question_text=prev_question,
            user_answer=prev_answer,
            score=feedback["score"],
            feedback=full_feedback_text,   # ✅ full feedback saved
            correct_answer=answer_part,
            explanation=explanation_part
        )

    # ✅ End after 5 questions (keep your existing logic)
    if request.session.get("resume_q_count", 0) >= 5 and prev_question:
        request.session["resume_active"] = False
        return JsonResponse({
            "end": True,
            "message": "Interview completed. You can view results when you want."
      })

    asked = AskedQuestion.objects.filter(
        user=request.user, skill="resume"
    ).values_list("question_text", flat=True)

    interview_type = request.session.get("resume_type", "resume")
    level = request.session.get("resume_level", "beginner")

    if interview_type == "hr":
        question = generate_hr_question(prev_answer, list(asked), difficulty=level)
    else:
        question = generate_resume_based_question(
            resume_text,
            prev_answer,
            list(asked),
            difficulty=level
        )

    AskedQuestion.objects.create(
        user=request.user,
        skill="resume",
        level=level,
        question_text=question
    )

    request.session["resume_q_count"] = request.session.get("resume_q_count", 0) + 1

    return JsonResponse({
       "question": question,
       "end": False
    })
@login_required
def resume_interview_results(request):
    results = InterviewAnswer.objects.filter(user=request.user, skill="resume").order_by("-created_at")
    return render(request, "resume_result.html", {"results": results})
# 🔥 COMMON QUESTION GENERATOR (for voice/chat/video)
def get_next_question_common(request, source="skills"):
    prev_answer = request.POST.get("answer", "")
    prev_question = request.POST.get("prev_question", "")

    asked = AskedQuestion.objects.filter(user=request.user).values_list("question_text", flat=True)

    if source == "resume":
        resume_path = request.session.get("resume_path")
        resume_text = extract_resume_text(resume_path)
        level = request.session.get("resume_level", "beginner")

        question = generate_resume_based_question(
            resume_text, prev_answer, list(asked), difficulty=level
        )
        skill = "resume"

    elif source == "hr":
        level = request.session.get("resume_level", "beginner")
        question = generate_hr_question(prev_answer, list(asked), difficulty=level)
        skill = "hr"

    else:
        skill = request.session.get("skill", "python")
        level = request.session.get("level", "beginner")
        question = generate_ai_question(skill, level, prev_answer, list(asked))

    AskedQuestion.objects.create(
        user=request.user,
        skill=skill,
        level=level,
        question_text=question
    )

    return question

@login_required
def voice_next_question(request):
    source = request.session.get("question_source", "skills")  # resume / skills
    question = get_next_question_common(request, source)
    return JsonResponse({"question": question})
@login_required
def video_next_question(request):
    source = request.session.get("question_source", "skills")
    question = get_next_question_common(request, source)
    return JsonResponse({"question": question})
@csrf_exempt
@login_required
def set_question_source(request):
    request.session["question_source"] = request.POST.get("source", "skills")
    return JsonResponse({"status": "ok"})
@csrf_exempt
@login_required
def voice_next_resume_question(request):
    prev_answer = request.POST.get("answer", "")
    prev_question = request.POST.get("prev_question", "")

    resume_path = request.session.get("resume_path")
    resume_text = extract_resume_text(resume_path)
    level = request.session.get("resume_level", "beginner")

    asked = AskedQuestion.objects.filter(user=request.user, skill="resume").values_list("question_text", flat=True)

    question = generate_resume_based_question(
        resume_text,
        prev_answer,
        list(asked),
        difficulty=level
    )

    AskedQuestion.objects.create(
        user=request.user,
        skill="resume",
        level=level,
        question_text=question
    )

    return JsonResponse({"question": question})


@login_required
def get_performance_data(request):
    answers = InterviewAnswer.objects.filter(user=request.user).order_by("-created_at")[:5]

    texts = " ".join([a.answer_text for a in answers if a.answer_text])

    if not texts:
        return JsonResponse({
           "overall": 0,
           "confidence": 0,
           "clarity": 0,
           "communication": 0,
           "feedback": ["No answers found. Practice to see results."]
    })

    result = evaluate_performance_ai(texts)

    return JsonResponse(result)


def register(request):
    if request.method == "POST":
        password = request.POST.get("password")
        confirm = request.POST.get("confirm_password")

        pattern = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$'
        if not re.match(pattern, password):
            return render(request, "register.html", {
               "error": "Password must contain Uppercase, Lowercase, Number, Special Character and 8+ length"
           })

        if password != confirm:
           return render(request, "register.html", {
              "error": "Passwords do not match"
          })

        # ✅ USER SAVE (IMPORTANT - add this!)
        username = request.POST.get("username")
        email = request.POST.get("email")

        User.objects.create_user(
            username=username,
            email=email,
            password=password
        )

        # 👉 success page ki redirect
        return redirect("register_success")

    return render(request, "register.html")
def forgot_password(request):
    if request.method == "POST":
        email = request.POST.get("email")

        if User.objects.filter(email=email).exists():
            request.session['reset_email'] = email
            return redirect('/reset-password/')
        else:
            return render(request, 'forgot_password.html', {"error": "Email not found"})

    return render(request, 'forgot_password.html')


def reset_password(request):
    if request.method == "POST":
        password = request.POST.get("password")
        confirm = request.POST.get("confirm_password")
        email = request.session.get('reset_email')

        if password != confirm:
            return render(request, 'reset_password.html', {"error": "Passwords do not match"})

        user = User.objects.get(email=email)
        user.set_password(password)
        user.save()

        return redirect('/login/')

    return render(request, 'reset_password.html')
@login_required
def streak_complete_view(request):
    return render(request, "streak_complete.html")

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import os

@csrf_exempt
def upload_video(request):
    print("🔥 Upload API called")

    if request.method == "POST":
        video = request.FILES.get('video')

        if video:
            print("✅ Video received")

            # media folder create if not exists
            os.makedirs("media", exist_ok=True)

            file_path = os.path.join("media", video.name)

            with open(file_path, 'wb+') as f:
                for chunk in video.chunks():
                    f.write(chunk)

            return JsonResponse({'status': 'success'})

        else:
            print("❌ No video file")

    return JsonResponse({'status': 'error'})
from django.http import JsonResponse
from .models import Recording

from .models import Recording

def upload_video(request):
    if request.method == "POST":
        video = request.FILES.get('video')

        if video:
            Recording.objects.create(video=video)   # 🔥 MUST
            print("Saved to DB")
            return JsonResponse({"status": "success"})

    return JsonResponse({"status": "error"})
def my_recordings(request):
    from .models import Recording
    recordings = Recording.objects.all().order_by('-created_at')

    return render(request, 'my_recordings.html', {'recordings': recordings})
from django.shortcuts import redirect, get_object_or_404
from .models import Recording   # ✅ correct model
from django.shortcuts import get_object_or_404, redirect
from .models import Recording

def delete_recording(request, id):
    obj = get_object_or_404(Recording, id=id)
    obj.delete()
    return redirect('my_recordings')
from django.http import JsonResponse
from .models import Feedback
import json

def save_feedback(request):
    if request.method == "POST":
        data = json.loads(request.body)

        rating = data.get("rating")
        feedback_text = data.get("feedback")
        doubt = data.get("doubt")

        Feedback.objects.create(
            rating=rating,
            feedback_text=feedback_text,
            doubt=doubt
        )

        return JsonResponse({"status": "success"})
from django.db.models import Avg

avg_rating = Feedback.objects.aggregate(Avg('rating'))['rating__avg']
context = {
    "avg_rating": avg_rating
}
from django.shortcuts import render
from django.db.models import Avg, Count
from .models import Feedback



def voice_next_question(request):

    skills = request.GET.get("skills", "")
    level = request.GET.get("level", "beginner")

    print("🔥 skills:", skills)
    print("🔥 level:", level)

    try:
        question = generate_ai_question(skills, level)
        print("✅ AI question:", question)
    except Exception as e:
        print("❌ AI ERROR:", e)
        question = "Error generating question"

    return JsonResponse({"question": question})
@login_required
@login_required
def coding_interview(request):
    return render(request, "coding_interview.html")

from .ai import generate_coding_question, evaluate_coding_answer

def coding_question(request):
    skills = request.GET.get("skills", "").strip()
    level = request.GET.get("level", "beginner").strip()

    skill_list = [s.strip() for s in skills.split(",") if s.strip()]
    main_skill = skill_list[0] if skill_list else "programming"

    print("🔥 SKILL:", main_skill)

    try:
        question = generate_coding_question(main_skill, level)

    except Exception as e:
        print("❌ ERROR:", e)
        question = f"Write a {level} level program using {main_skill}"

    return JsonResponse({"question": question})
csrf_exempt

def evaluate_code(request):
    import json
    data = json.loads(request.body)

    question = data.get("question")
    code = data.get("code")
    skill = data.get("skill")

    solution = evaluate_coding_answer(skill, question, code)

    return JsonResponse({
         "solution": solution
   })       
def start_interview(request):
    if request.method == "POST":
        data = json.loads(request.body)
        role = data.get("role")

        # ✅ Save role in session
        request.session['selected_role'] = role

        return JsonResponse({"status": "success"})
from django.shortcuts import render
from django.http import JsonResponse
from .ai import generate_questions


def role_select(request):
    return render(request, 'role_select.html')


def real_interview(request):
    return render(request, 'real_interview.html')


def get_questions(request):

    role = request.GET.get('role', 'Python Developer')

    print("🔥 ROLE:", role)

    questions = generate_questions(role)

    print("🔥 QUESTIONS:", questions)

    return JsonResponse({
       "questions": questions
    })
import json
from django.http import JsonResponse
from .ai import evaluate_answer, generate_correct_answer_with_explanation

def evaluate_answer_view(request):
    data = json.loads(request.body)

    question = data.get("question")
    answer = data.get("answer")
    role = data.get("role")

    result = evaluate_answer(role, question, answer)
    correct = generate_correct_answer_with_explanation(role, question)

    return JsonResponse({
       "score": result["score"],
       "feedback": result["suggestion"],
       "correct": correct
    })
import subprocess
import tempfile
import json
from django.http import JsonResponse

def run_code(request):
    import subprocess, tempfile, json
    from django.http import JsonResponse

    data = json.loads(request.body)
    code = data.get("code")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
            f.write(code.encode())
            filename = f.name

        result = subprocess.run(
            ["python", filename],
            capture_output=True,
            text=True,
            timeout=5
        )

        return JsonResponse({
           "stdout": result.stdout,
            "stderr": result.stderr
       })

    except Exception as e:
        return JsonResponse({
            "stdout": "",
            "stderr": str(e)
       })
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import subprocess
import tempfile

from .ai import generate_test_cases


from .ai import generate_test_cases, generate_solution

@csrf_exempt
def evaluate_code(request):

    import json, subprocess, tempfile
    from django.http import JsonResponse

    data = json.loads(request.body)

    code = data.get("code", "")
    question = data.get("question", "")

    # 🔥 1. Generate test cases
    raw = generate_test_cases(question)

    test_cases = []
    try:
        for block in raw.split("Input:")[1:]:
            parts = block.strip().split("Output:")
            inp = parts[0].strip()
            out = parts[1].strip()

            test_cases.append({
                "input": inp,
                "output": out
           })
    except:
       pass

    # fallback
    if not test_cases:
        test_cases = [
            {"input": "2 3", "output": "5"}
        ]

    results = []

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
            f.write(code.encode())
            filename = f.name

        for i, test in enumerate(test_cases):

            result = subprocess.run(
                ["python", filename],
                input=test["input"],
                capture_output=True,
                text=True,
                timeout=5
            )

            output = result.stdout.strip()

            if output == test["output"]:
                results.append(f"Test {i+1}: ✅ Passed")
            else:
                results.append(
                    f"Test {i+1}: ❌ Failed (Expected {test['output']}, Got {output})"
                )

    except Exception as e:
        results.append(f"Error: {str(e)}")

    # 🔥 2. GENERATE CORRECT SOLUTION (IMPORTANT)
    solution = generate_solution(question)

    return JsonResponse({
        "result": "\n".join(results),
        "solution": solution   # ✅ ADD THIS
   })
from django.db.models import Avg

def result_view(request):
    avg_rating = Feedback.objects.aggregate(avg=Avg('rating'))['avg'] or 0

    return render(request, "result.html", {
      "avg_rating": round(avg_rating, 1)
   })
from django.shortcuts import render
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count
from .models import Feedback

User = get_user_model()

def feedback_insights(request):

    total_users = User.objects.count()
    total = Feedback.objects.count()

    avg_rating = Feedback.objects.aggregate(avg=Avg('rating'))['avg'] or 0

    # Rating distribution
    labels = ["1", "2", "3", "4", "5"]
    counts = [0,0,0,0,0]

    rating_data = Feedback.objects.values('rating').annotate(c=Count('rating'))

    for r in rating_data:
        counts[r['rating'] - 1] = r['c']

    # Top feedback
    top_feedback = Feedback.objects.all()[:5]

    # Status logic
    if avg_rating >= 4:
        status = "Excellent 🚀"
        insight = "Users love the system!"
    elif avg_rating >= 3:
        status = "Good 👍"
        insight = "System is good but needs improvements"
    else:
        status = "Needs Improvement ⚠️"
        insight = "Improve features and performance"

    print("DEBUG USERS:", total_users)  # MUST print

    return render(request, "feedback_dashboard.html", {
        "total_users": total_users,
        "total": total,
        "avg_rating": round(avg_rating,1),
        "labels": labels,
        "counts": counts,
        "top_feedback": top_feedback,
        "status": status,
        "insight": insight
    })