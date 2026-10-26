from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from surveys.models import Survey, SurveyAttempt
from surveys.serializers import QuestionSerializer


class NextQuestionView(APIView):
    """Возвращает следующий вопрос."""

    permission_classes = [IsAuthenticated]

    def get(self, request, survey_id):
        survey = get_object_or_404(
            Survey.objects.select_related('actual_version'),
            pk=survey_id,
            deleted_at__isnull=True,
            actual_version__isnull=False,
        )
        attempt = (
            SurveyAttempt.objects.select_related('survey_version')
            .filter(
                survey=survey,
                user=request.user,
                status=SurveyAttempt.STATUS_IN_PROGRESS,
            )
            .first()
        )

        version = attempt.survey_version if attempt else survey.actual_version
        last_order = attempt.last_answered_order if attempt else 0

        question = (
            version.questions.filter(order__gt=last_order)
            .prefetch_related('choices')
            .order_by('order')
            .first()
        )
        if question is None:
            return Response({'detail': 'Опрос пройден'})

        return Response(QuestionSerializer(question).data)
