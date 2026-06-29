from django.contrib import admin
from django.urls import path
from interview import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.main_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
]






