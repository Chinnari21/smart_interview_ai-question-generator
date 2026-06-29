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

# ---------------- AUTH ----------------

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

    # 🔥 VERY IMPORTANT FIX
    AskedQuestion.objects.filter(
       user=request.user,
       skill=skill,
        level=level
    ).delete()

    context = {
       "skills": skill,
       "level": level
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

            feedback = (
                f"{strengths}||{weaknesses}||{suggestion}"
            ),

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
    # 🔥 Ensure question source flows into video mode too
    if "question_source" not in request.session:
        request.session["question_source"] = "skills"  # default

    return render(request, 'video.html')


@login_required
def voice_analysis(request):
    return render(request, 'voice.html')


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
def performance_view(request):
    return render(request, "performance.html")

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