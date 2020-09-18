from django.urls import path

from django_backblaze_b2 import views

app_name = "django_b2_storage"
urlpatterns = [
    path("b2/<path:filename>", views.downloadPublicFile, name="b2-public"),
    path("b2l/<path:filename>", views.downloadLoggedInFile, name="b2-logged-in"),
    path("b2s/<path:filename>", views.downloadStaffFile, name="b2-staff"),
]
