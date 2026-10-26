import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class Survey(models.Model):
    """Опрос."""

    title = models.CharField(max_length=255)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='surveys',
        db_index=False,  # покрыт индексом (author, created_at)
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    actual_version = models.ForeignKey(
        'SurveyVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )

    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(
                fields=['author', '-created_at'],
                name='survey_author_created_idx'
            ),
        ]

    def __str__(self):
        return self.title


class SurveyVersion(models.Model):
    """Версия опроса."""

    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PUBLISHED, 'Published'),
    ]

    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='versions',
        db_index=False  # покрыт uniq_survey_version_number
    )
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    questions_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['survey', 'number']
        constraints = [
            # Ограничение что номер версии уникален в рамках опроса.
            models.UniqueConstraint(
                fields=['survey', 'number'], name='uniq_survey_version_number'
            ),
            # Ограничение что у опроса может быть только один черновик.
            models.UniqueConstraint(
                fields=['survey'],
                condition=Q(status='draft'),
                name='uniq_survey_single_draft',
            ),
            # Проверка опубликованная версия заполнена целиком
            models.CheckConstraint(
                condition=Q(status='draft')
                | Q(
                    status='published',
                    published_at__isnull=False,
                    questions_count__gt=0
                ),
                name='published_version_is_complete',
            ),
        ]


class Question(models.Model):
    """Вопрос в рамках версии опроса."""

    version = models.ForeignKey(
        SurveyVersion,
        on_delete=models.CASCADE,
        related_name='questions',
        db_index=False,  # покрыт uniq_question_order_in_version
    )
    lineage = models.UUIDField(default=uuid.uuid4, editable=False)
    text = models.CharField(max_length=500)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']
        constraints = [
            # Порядковый номер вопроса уникален в рамках версии.
            models.UniqueConstraint(
                fields=['version', 'order'],
                name='uniq_question_order_in_version',
            ),
        ]
        indexes = [
            models.Index(fields=['lineage'], name='question_lineage_idx'),
        ]

    def __str__(self):
        return self.text


class Choice(models.Model):
    """Вариант ответа на вопрос конкретной версии."""

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='choices',
        db_index=False,  # покрыт uniq_choice_order
    )
    lineage = models.UUIDField(default=uuid.uuid4, editable=False)
    text = models.CharField(max_length=255)
    order = models.PositiveIntegerField()
    is_custom = models.BooleanField(default=False, verbose_name='Свой ответ')

    class Meta:
        ordering = ['order']
        constraints = [
            # Порядковый номер варианта уникален в рамках вопроса.
            models.UniqueConstraint(
                fields=['question', 'order'],
                name='uniq_choice_order'
            ),
            # У вопроса может быть только один вариант своего оивета».
            models.UniqueConstraint(
                fields=['question'],
                condition=Q(is_custom=True),
                name='uniq_custom_choice_per_question',
            ),
        ]

    def __str__(self):
        return self.text


class SurveyAttempt(models.Model):
    """Одно прохождение опроса пользователем."""

    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_COMPLETED = 'completed'
    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, 'In progress'),
        (STATUS_COMPLETED, 'Completed'),
    ]
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name='attempts',
        db_index=False,
    )
    survey_version = models.ForeignKey(
        SurveyVersion,
        on_delete=models.RESTRICT,
        related_name='attempts',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='survey_attempts',
        db_index=False,  # покрыт индексом (user, survey)
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_IN_PROGRESS
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    last_answered_order = models.PositiveIntegerField(default=0)
    answered_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            # У пользователя только одно активное прохождение опроса.
            models.UniqueConstraint(
                fields=['survey', 'user'],
                condition=Q(status='in_progress'),
                name='uniq_active_attempt_per_user',
            ),
            # finished_at заполнен только у завершённого прохождения
            models.CheckConstraint(
                condition=Q(status='in_progress', finished_at__isnull=True)
                | Q(status='completed', finished_at__isnull=False),
                name='attempt_finished_at_matches_status',
            ),
            # Проверка согласованности указателя и счётчика прогресса
            models.CheckConstraint(
                condition=Q(answered_count=0, last_answered_order=0)
                | Q(answered_count__gt=0, last_answered_order__gt=0),
                name='attempt_progress_consistent',
            ),
        ]
        indexes = [
            models.Index(
                fields=['user', 'survey'],
                name='attempt_user_survey_idx'
            ),
        ]


class Answer(models.Model):
    """Ответ пользователя на вопрос в рамках попытки"""

    pk = models.CompositePrimaryKey('attempt_id', 'question_id')
    attempt = models.ForeignKey(
        SurveyAttempt,
        on_delete=models.CASCADE,
        related_name='answers',
        db_index=False,
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_index=False,
        related_name='+',
    )
    selected_choice = models.ForeignKey(
        Choice,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_index=False,
        related_name='+',
    )
    custom_answer = models.CharField(
        blank=True,
        default='',
        max_length=2000,
        verbose_name='Собственный ответ'
    )
    answered_at = models.DateTimeField(auto_now_add=True)


# Статистика
class SurveyVersionStats(models.Model):
    version = models.OneToOneField(
        SurveyVersion,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name='stats'
    )
    started_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Сколько начали'
    )
    completed_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Сколько прошли'
    )
    total_duration_seconds = models.BigIntegerField(
        default=0,
        verbose_name='Суммарное время завершённых прохождений, сек'
    )


class QuestionStats(models.Model):
    question = models.OneToOneField(
        Question,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name='stats'
    )
    answers_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Сколько ответили'
    )


class ChoiceStats(models.Model):
    choice = models.OneToOneField(
        Choice,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name='stats'
    )
    votes_count = models.PositiveIntegerField(
        default=0,
        verbose_name='Сколько раз выбрали'
    )
