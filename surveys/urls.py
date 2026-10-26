from django.urls import path

from surveys.views import NextQuestionView

app_name = 'surveys'

urlpatterns = [
    path(
        'surveys/<int:survey_id>/next-question/',
        NextQuestionView.as_view(),
        name='next-question',
    ),
]
