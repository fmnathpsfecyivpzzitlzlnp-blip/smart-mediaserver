# blog/forms.py
from django import forms
from .models import ClockItem, Video
from django.contrib.auth.forms import UserCreationForm


class ClockItemForm(forms.ModelForm):
    class Meta:
        model = ClockItem
        # --- Добавляем новое поле в список fields ---
        fields = ['name', 'item_type', 'alarm_time', 'days_of_week', 'timer_duration', 'sound_file']
        widgets = {
            'alarm_time': forms.TimeInput(attrs={'type': 'time', 'step': '1'}),
            'timer_duration': forms.NumberInput(attrs={'placeholder': 'Длительность в секундах'}),
        }
# --- НОВАЯ ФОРМА РЕГИСТРАЦИИ ---
class CustomUserCreationForm(UserCreationForm):
    # Мы можем здесь добавить новые поля, если захотим
    class Meta(UserCreationForm.Meta):
        # model = User # Django подставит сам
        fields = ('username', 'email') # Какие поля показывать


class VideoUploadForm(forms.ModelForm):
    class Meta:
        model = Video
        # Мы просим пользователя ввести название, выбрать тип (Фильм/Урок) и сам файл
        fields = ['title', 'video_type', 'movie_path', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['movie_path'].label = "Файл видео"
        self.fields['movie_path'].help_text = "Поддерживаются mp4, mkv, avi. Файл будет отправлен на конвертацию."