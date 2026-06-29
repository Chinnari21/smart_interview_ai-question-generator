from django.urls import path
from . import views
from .views import chat_interview_view, get_next_question, interview_summary

urlpatterns = [
    path('', views.home_view, name='home'),

    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('register-success/', views.register_success_view, name='register_success'),
    path('login-success/', views.login_success_view, name='login_success'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),

    path('skills/', views.skills_view, name='skills'),
    path('setup/', views.setup_view, name='setup'),

    # Chat interview
    path('chat-interview/', views.chat_interview_view, name='chat_interview'),

    # Resume interview
    path('resume-upload/', views.resume_upload, name='resume_upload'),
    path('resume-interview/', views.resume_chat_interview, name='resume_chat_interview'),
    path('resume-interview/results/', views.resume_interview_results, name='resume_interview_results'),

    # Other features
    path('result/', views.result_view, name='result'),
    path('video/', views.video_practice, name='video_practice'),
    path('voice/', views.voice_analysis, name='voice_analysis'),
    path('performance/', views.performance, name='performance'),

    path('role-select/', views.role_select, name='role_select'),
    path('real-interview/', views.real_interview_view, name='real_interview'),

    path('streak/', views.streak_view, name='streak'),

    path('upload-video/', views.upload_recording, name='upload_recording'),
    path('my-recordings/', views.my_recordings, name='my_recordings'),
    path('delete-recording/<int:rid>/', views.delete_recording, name='delete_recording'),

    path('upload-voice/', views.upload_voice, name='upload_voice'),
    path('my-voice-recordings/', views.my_voice_recordings, name='my_voice_recordings'),
    path('delete-voice-recording/<int:rid>/', views.delete_voice_recording, name='delete_voice_recording'),

    # APIs
    path("api/next-question/", get_next_question, name="next_question"),
    path("api/complete-today/", views.complete_today_practice, name="complete_today"),
    path("api/next-resume-question/", views.get_next_resume_question, name="next_resume_question"),

    # 🔥 VOICE AI QUESTION API (ADD THIS)
    path("api/voice-next-question/", views.voice_next_question, name="voice_next_question"),

    # Summary
    path("interview-summary/", interview_summary, name="interview_summary"),
    path("api/video-next-question/", views.video_next_question, name="video_next_question"),
    # interview/urls.py

    path("performance/", views.performance_view, name="performance"),
    path("api/performance/", views.get_performance_data, name="get_performance_data"),
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/', views.reset_password, name='reset_password'),
    path("streak-complete/", views.streak_complete_view, name="streak_complete"),
]
