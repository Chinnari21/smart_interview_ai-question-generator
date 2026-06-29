from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class AskedQuestion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    skill = models.CharField(max_length=100)
    level = models.CharField(max_length=50)
    question_text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.skill} - {self.level}"


class PracticeDay(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField(default=timezone.now)
    questions_attempted = models.IntegerField(default=0)

    class Meta:
        unique_together = ("user", "date")

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.questions_attempted} questions"
class PracticeDay(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    completed = models.BooleanField(default=False)

class Meta:
    unique_together = ("user", "date")

    def __str__(self):
        return f"{self.user.username} - {self.date} - {self.completed}"


class Streak(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    current_streak = models.IntegerField(default=0)
    longest_streak = models.IntegerField(default=0)
    last_practice_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.current_streak} days"
class VideoRecording(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    question_text = models.TextField()
    file = models.FileField(upload_to="recordings/")
    created_at = models.DateTimeField(auto_now_add=True)
    is_private = models.BooleanField(default=True)

    # Mock AI feedback (demo)
    confidence = models.IntegerField(default=70)
    speech_speed = models.IntegerField(default=65)
    pauses = models.IntegerField(default=60)

    def __str__(self):
        return f"{self.user.username} - {self.created_at}"
class VoiceRecording(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    file = models.FileField(upload_to='voice_recordings/')
    clarity = models.IntegerField(default=0)
    speech_speed = models.IntegerField(default=0)
    confidence = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
 # interview/models.py
class InterviewAnswer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    skill = models.CharField(max_length=100)
    level = models.CharField(max_length=50)
    question_text = models.TextField()
    user_answer = models.TextField()
    score = models.IntegerField()
    feedback = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    correct_answer = models.TextField(blank=True, null=True)
    explanation = models.TextField(blank=True, null=True) 
from django.db import models

class Recording(models.Model):
    video = models.FileField(upload_to='videos/')
    created_at = models.DateTimeField(auto_now_add=True)
class Feedback(models.Model):
    rating = models.IntegerField()
    feedback_text = models.TextField()
    doubt = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Rating: {self.rating}"   