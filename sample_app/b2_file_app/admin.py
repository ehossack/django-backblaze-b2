from django.contrib import admin

from .models import ModelWithFiles


@admin.register(ModelWithFiles)
class ModelWithFilesAdmin(admin.ModelAdmin):
    pass
