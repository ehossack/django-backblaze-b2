from django.contrib import admin
from sample_app.b2_file_app.models import ModelWithFiles


@admin.register(ModelWithFiles)
class ModelWithFilesAdmin(admin.ModelAdmin):
    pass
