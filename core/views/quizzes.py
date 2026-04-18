"""
Quiz-related views.
"""
import json
from zoneinfo import ZoneInfo

from django.db.models import Avg, Sum
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    CourseSection,
    Enrollment,
    Notification,
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizChoice,
    QuizQuestion,
    User,
    WeeklyModule,
)
from core.serializers import (
    QuizAnswerGradeSerializer,
    QuizAnswerInputSerializer,
    QuizQuestionBulkSerializer,
    QuizQuestionWriteSerializer,
    QuizQuestionStudentSerializer,
    QuizSerializer,
)
from core.views.common import (
    _sync_student_activity_items,
    _sync_course_section_students_activity_items,
    _notify_students_for_course_section,
)

PHT_TZ = ZoneInfo("Asia/Manila")


def _parse_multi_select_choice_ids(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in parsed:
        choice_id = str(item)
        if choice_id in seen:
            continue
        seen.add(choice_id)
        result.append(choice_id)
    return result


def _to_pht(dt):
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, PHT_TZ)
    return timezone.localtime(dt, PHT_TZ)


def _quiz_window_error(quiz: Quiz) -> str | None:
    now = _to_pht(timezone.now())
    open_at = _to_pht(quiz.open_at)
    close_at = _to_pht(quiz.close_at)
    if open_at and now < open_at:
        return "Quiz is not yet open."
    if close_at and now > close_at:
        return "Quiz is already closed."
    return None


def _notify_teacher_quiz_submission(attempt: QuizAttempt):
    teacher = attempt.quiz.course_section.teacher
    if not teacher:
        return
    Notification.objects.create(
        recipient=teacher,
        type=Notification.NotificationType.NEW_QUIZ,
        title=f"Quiz Submission: {attempt.quiz.title}",
        body=f"{attempt.student.full_name} submitted attempt #{attempt.attempt_number}.",
        course_section=attempt.quiz.course_section,
        quiz=attempt.quiz,
    )


def _send_quiz_grade_notification(attempt: QuizAttempt):
    """Send push notification when quiz grading is complete."""
    from core.push_notifications import send_push_notification_to_users

    try:
        quiz = attempt.quiz
        student = attempt.student

        Notification.objects.create(
            recipient=student,
            type=Notification.NotificationType.GRADE_RELEASED,
            title=f"Quiz Graded: {quiz.title}",
            body=f"Your quiz '{quiz.title}' has been graded. Score: {attempt.score}/{attempt.max_score}",
            course_section=quiz.course_section,
            quiz=quiz,
        )

        data = {
            "type": "grade_released",
            "quiz_id": str(quiz.id),
            "course_section_id": str(quiz.course_section_id),
        }

        send_push_notification_to_users(
            user_ids=[str(student.id)],
            title=f"Quiz Graded: {quiz.title}",
            body=f"Your quiz has been graded. Score: {attempt.score}/{attempt.max_score}",
            data=data,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to send quiz grade notification: {e}")


class QuizTakeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _get_time_remaining(self, attempt: QuizAttempt):
        quiz = attempt.quiz
        if not quiz.time_limit_minutes:
            return None
        elapsed = (timezone.now() - attempt.started_at).total_seconds()
        remaining = int((quiz.time_limit_minutes * 60) - elapsed)
        return max(remaining, 0)

    def _auto_finalize_attempt(self, attempt: QuizAttempt):
        if attempt.is_submitted:
            return attempt

        questions = {
            str(q.id): q
            for q in QuizQuestion.objects.filter(quiz=attempt.quiz).prefetch_related("choices")
        }
        answers_by_qid = {str(a.question_id): a for a in QuizAnswer.objects.filter(attempt=attempt)}
        max_score = sum(float(q.points) for q in questions.values())
        total_score = 0.0
        pending_manual = False

        for qid, question in questions.items():
            ans = answers_by_qid.get(qid)
            if not ans:
                if question.question_type == QuizQuestion.QuestionType.ESSAY:
                    pending_manual = True
                    QuizAnswer.objects.create(
                        attempt=attempt,
                        question=question,
                        needs_manual_grading=True,
                    )
                continue

            if question.question_type in [QuizQuestion.QuestionType.MULTIPLE_CHOICE, QuizQuestion.QuestionType.TRUE_FALSE]:
                is_correct = bool(ans.selected_choice and ans.selected_choice.is_correct)
                points_awarded = float(question.points) if is_correct else 0.0
                ans.is_correct = is_correct
                ans.points_awarded = points_awarded
                ans.needs_manual_grading = False
                ans.graded_at = timezone.now()
                ans.save(update_fields=["is_correct", "points_awarded", "needs_manual_grading", "graded_at"])
                total_score += points_awarded
            elif question.question_type == QuizQuestion.QuestionType.IDENTIFICATION:
                # Compare text answer against correct_answer and alternate_answers
                student_answer = (ans.text_answer or "").strip()
                correct_answers = [(question.correct_answer or "").strip()] + [
                    str(answer).strip()
                    for answer in (question.alternate_answers or [])
                    if str(answer).strip()
                ]
                if not question.case_sensitive:
                    student_answer = student_answer.lower()
                    correct_answers = [a.lower() for a in correct_answers]
                is_correct = student_answer in correct_answers
                points_awarded = float(question.points) if is_correct else 0.0
                ans.is_correct = is_correct
                ans.points_awarded = points_awarded
                ans.needs_manual_grading = False
                ans.graded_at = timezone.now()
                ans.save(update_fields=["is_correct", "points_awarded", "needs_manual_grading", "graded_at"])
                total_score += points_awarded
            elif question.question_type == QuizQuestion.QuestionType.MULTI_SELECT:
                selected_ids = set(_parse_multi_select_choice_ids(ans.text_answer))
                correct_ids = {
                    str(choice.id)
                    for choice in question.choices.all()
                    if choice.is_correct
                }
                correct_selected = len(selected_ids & correct_ids)
                union_ids = selected_ids | correct_ids
                ratio = (correct_selected / len(union_ids)) if union_ids else 0.0
                is_correct = bool(correct_ids) and selected_ids == correct_ids
                points_awarded = float(question.points) * ratio
                ans.is_correct = is_correct
                ans.points_awarded = points_awarded
                ans.needs_manual_grading = False
                ans.graded_at = timezone.now()
                ans.save(update_fields=["is_correct", "points_awarded", "needs_manual_grading", "graded_at"])
                total_score += points_awarded
            else:  # ESSAY
                pending_manual = True
                ans.needs_manual_grading = True
                ans.is_correct = None
                ans.points_awarded = None
                ans.save(update_fields=["needs_manual_grading", "is_correct", "points_awarded"])

        attempt.is_submitted = True
        attempt.submitted_at = timezone.now()
        attempt.max_score = max_score
        attempt.score = total_score
        attempt.pending_manual_grading = pending_manual
        attempt.save(update_fields=["is_submitted", "submitted_at", "max_score", "score", "pending_manual_grading"])
        _sync_student_activity_items(attempt.student)
        _notify_teacher_quiz_submission(attempt)
        if not pending_manual:
            _send_quiz_grade_notification(attempt)
        return attempt

    def get(self, request, pk):
        if request.user.role != User.Role.STUDENT:
            return Response({"detail": "Only students can take quizzes."}, status=status.HTTP_403_FORBIDDEN)

        quiz = Quiz.objects.select_related("course_section").filter(id=pk).first()
        if not quiz:
            return Response({"detail": "Quiz not found."}, status=status.HTTP_404_NOT_FOUND)

        enrolled = Enrollment.objects.filter(course_section=quiz.course_section, student=request.user, is_active=True).exists()
        if not enrolled:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if not quiz.is_published:
            return Response({"detail": "Quiz is not available."}, status=status.HTTP_403_FORBIDDEN)
        window_error = _quiz_window_error(quiz)
        if window_error:
            return Response({"detail": window_error}, status=status.HTTP_403_FORBIDDEN)

        # No-resume policy: any open attempt is auto-submitted when student re-enters.
        open_attempts = list(
            QuizAttempt.objects.filter(quiz=quiz, student=request.user, is_submitted=False)
            .order_by("-attempt_number")
        )
        for open_attempt in open_attempts:
            self._auto_finalize_attempt(open_attempt)

        submitted_count = QuizAttempt.objects.filter(quiz=quiz, student=request.user, is_submitted=True).count()
        if submitted_count >= quiz.attempt_limit:
            return Response({"detail": "Attempt limit reached."}, status=status.HTTP_400_BAD_REQUEST)

        attempt = QuizAttempt.objects.create(
            quiz=quiz,
            student=request.user,
            attempt_number=submitted_count + 1,
            is_submitted=False,
        )

        remaining = self._get_time_remaining(attempt)
        if remaining is not None and remaining <= 0:
            self._auto_finalize_attempt(attempt)
            return Response({"detail": "Quiz time has ended and your attempt was auto-submitted."}, status=status.HTTP_400_BAD_REQUEST)

        questions = QuizQuestion.objects.filter(quiz=quiz).prefetch_related("choices").order_by("sort_order")
        existing_answers = QuizAnswer.objects.filter(attempt=attempt).select_related("question")
        answers_payload = []
        for a in existing_answers:
            payload = {
                "question_id": str(a.question_id),
                "selected_choice_id": str(a.selected_choice_id) if a.selected_choice_id else None,
                "text_answer": a.text_answer,
            }
            if a.question.question_type == QuizQuestion.QuestionType.MULTI_SELECT:
                payload["selected_choice_ids"] = _parse_multi_select_choice_ids(a.text_answer)
            answers_payload.append(
                payload
            )
        return Response(
            {
                "quiz": QuizSerializer(quiz).data,
                "questions": QuizQuestionStudentSerializer(questions, many=True).data,
                "attempt_id": str(attempt.id),
                "attempt_number": attempt.attempt_number,
                "time_remaining_seconds": remaining,
                "answers": answers_payload,
            }
        )


class QuizSubmitAttemptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != User.Role.STUDENT:
            return Response({"detail": "Only students can submit quizzes."}, status=status.HTTP_403_FORBIDDEN)

        quiz = Quiz.objects.select_related("course_section").filter(id=pk).first()
        if not quiz:
            return Response({"detail": "Quiz not found."}, status=status.HTTP_404_NOT_FOUND)

        enrolled = Enrollment.objects.filter(course_section=quiz.course_section, student=request.user, is_active=True).exists()
        if not enrolled:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if not quiz.is_published:
            return Response({"detail": "Quiz is not available."}, status=status.HTTP_403_FORBIDDEN)
        window_error = _quiz_window_error(quiz)
        if window_error:
            return Response({"detail": window_error}, status=status.HTTP_403_FORBIDDEN)

        submitted_attempts = QuizAttempt.objects.filter(quiz=quiz, student=request.user, is_submitted=True).count()
        if submitted_attempts >= quiz.attempt_limit:
            return Response({"detail": "Attempt limit reached."}, status=status.HTTP_400_BAD_REQUEST)

        attempt_id = request.data.get("attempt_id")
        attempt = None
        if attempt_id:
            attempt = QuizAttempt.objects.filter(
                id=attempt_id,
                quiz=quiz,
                student=request.user,
                is_submitted=False,
            ).first()

        if not attempt:
            attempt = (
                QuizAttempt.objects.filter(quiz=quiz, student=request.user, is_submitted=False)
                .order_by("-attempt_number")
                .first()
            )
        if not attempt:
            attempt = QuizAttempt.objects.create(
                quiz=quiz,
                student=request.user,
                attempt_number=submitted_attempts + 1,
                is_submitted=False,
            )

        answers_data = request.data.get("answers", [])
        serializer = QuizAnswerInputSerializer(data=answers_data, many=True)
        serializer.is_valid(raise_exception=True)
        answers_in = serializer.validated_data

        remaining = None
        if quiz.time_limit_minutes:
            elapsed = (timezone.now() - attempt.started_at).total_seconds()
            remaining = int((quiz.time_limit_minutes * 60) - elapsed)
        if remaining is not None and remaining <= 0:
            finalized = QuizTakeView()._auto_finalize_attempt(attempt)
            return Response(
                {
                    "detail": "Quiz time has ended and your attempt was auto-submitted.",
                    "attempt_id": str(finalized.id),
                    "score": float(finalized.score) if finalized.score is not None else None,
                    "max_score": float(finalized.max_score) if finalized.max_score is not None else None,
                    "pending_manual_grading": finalized.pending_manual_grading,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        questions = {str(q.id): q for q in QuizQuestion.objects.filter(quiz=quiz)}
        for item in answers_in:
            qid = str(item["question_id"])
            question = questions.get(qid)
            if not question:
                continue
            if question.question_type == QuizQuestion.QuestionType.MULTI_SELECT:
                selected_ids = item.get("selected_choice_ids") or []
                if not selected_ids and item.get("selected_choice_id"):
                    selected_ids = [item["selected_choice_id"]]
                valid_ids = [
                    str(choice_id)
                    for choice_id in QuizChoice.objects.filter(
                        id__in=selected_ids,
                        question=question,
                    ).values_list("id", flat=True)
                ]
                QuizAnswer.objects.update_or_create(
                    attempt=attempt,
                    question=question,
                    defaults={
                        "selected_choice": None,
                        "text_answer": json.dumps(valid_ids),
                    },
                )
                continue

            selected_choice = None
            if item.get("selected_choice_id"):
                selected_choice = QuizChoice.objects.filter(id=item["selected_choice_id"], question=question).first()
            QuizAnswer.objects.update_or_create(
                attempt=attempt,
                question=question,
                defaults={
                    "selected_choice": selected_choice,
                    "text_answer": item.get("text_answer"),
                },
            )

        finalized = QuizTakeView()._auto_finalize_attempt(attempt)
        _sync_student_activity_items(request.user)

        return Response(
            {
                "attempt_id": str(finalized.id),
                "score": float(finalized.score) if finalized.score is not None else None,
                "max_score": float(finalized.max_score) if finalized.max_score is not None else None,
                "pending_manual_grading": finalized.pending_manual_grading,
            }
        )


class QuizSaveProgressView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != User.Role.STUDENT:
            return Response({"detail": "Only students can save quiz progress."}, status=status.HTTP_403_FORBIDDEN)

        quiz = Quiz.objects.select_related("course_section").filter(id=pk).first()
        if not quiz:
            return Response({"detail": "Quiz not found."}, status=status.HTTP_404_NOT_FOUND)
        enrolled = Enrollment.objects.filter(course_section=quiz.course_section, student=request.user, is_active=True).exists()
        if not enrolled:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if not quiz.is_published:
            return Response({"detail": "Quiz is not available."}, status=status.HTTP_403_FORBIDDEN)
        window_error = _quiz_window_error(quiz)
        if window_error:
            return Response({"detail": window_error}, status=status.HTTP_403_FORBIDDEN)

        attempt_id = request.data.get("attempt_id")
        attempt = QuizAttempt.objects.filter(id=attempt_id, quiz=quiz, student=request.user, is_submitted=False).first() if attempt_id else None
        if not attempt:
            return Response({"detail": "Open attempt not found."}, status=status.HTTP_404_NOT_FOUND)

        if quiz.time_limit_minutes:
            elapsed = (timezone.now() - attempt.started_at).total_seconds()
            if int((quiz.time_limit_minutes * 60) - elapsed) <= 0:
                finalized = QuizTakeView()._auto_finalize_attempt(attempt)
                return Response(
                    {
                        "detail": "Quiz time has ended and your attempt was auto-submitted.",
                        "attempt_id": str(finalized.id),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        answers_data = request.data.get("answers", [])
        serializer = QuizAnswerInputSerializer(data=answers_data, many=True)
        serializer.is_valid(raise_exception=True)
        answers_in = serializer.validated_data
        questions = {str(q.id): q for q in QuizQuestion.objects.filter(quiz=quiz)}

        for item in answers_in:
            qid = str(item["question_id"])
            question = questions.get(qid)
            if not question:
                continue
            if question.question_type == QuizQuestion.QuestionType.MULTI_SELECT:
                selected_ids = item.get("selected_choice_ids") or []
                if not selected_ids and item.get("selected_choice_id"):
                    selected_ids = [item["selected_choice_id"]]
                valid_ids = [
                    str(choice_id)
                    for choice_id in QuizChoice.objects.filter(
                        id__in=selected_ids,
                        question=question,
                    ).values_list("id", flat=True)
                ]
                QuizAnswer.objects.update_or_create(
                    attempt=attempt,
                    question=question,
                    defaults={
                        "selected_choice": None,
                        "text_answer": json.dumps(valid_ids),
                    },
                )
                continue

            selected_choice = None
            if item.get("selected_choice_id"):
                selected_choice = QuizChoice.objects.filter(id=item["selected_choice_id"], question=question).first()
            QuizAnswer.objects.update_or_create(
                attempt=attempt,
                question=question,
                defaults={
                    "selected_choice": selected_choice,
                    "text_answer": item.get("text_answer"),
                },
            )

        return Response({"ok": True, "attempt_id": str(attempt.id)})


class QuizMyLatestAttemptView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        if request.user.role != User.Role.STUDENT:
            return Response({"detail": "Only students can view this endpoint."}, status=status.HTTP_403_FORBIDDEN)

        quiz = Quiz.objects.select_related("course_section").filter(id=pk).first()
        if not quiz:
            return Response({"detail": "Quiz not found."}, status=status.HTTP_404_NOT_FOUND)
        enrolled = Enrollment.objects.filter(
            course_section=quiz.course_section,
            student=request.user,
            is_active=True,
        ).exists()
        if not enrolled:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if not quiz.is_published:
            return Response({"detail": "Quiz not found."}, status=status.HTTP_404_NOT_FOUND)

        attempts_used = QuizAttempt.objects.filter(quiz_id=pk, student=request.user, is_submitted=True).count()
        attempt = QuizAttempt.objects.filter(quiz_id=pk, student=request.user, is_submitted=True).order_by("-attempt_number").first()

        graded_attempts = QuizAttempt.objects.filter(quiz_id=pk, is_submitted=True, pending_manual_grading=False, score__isnull=False)
        total = graded_attempts.count()
        avg_score = graded_attempts.aggregate(avg=Avg("score"))["avg"]
        low_score = None
        high_score = None
        if total > 0:
            scores = [float(s.score) for s in graded_attempts if s.score is not None]
            if scores:
                low_score = min(scores)
                high_score = max(scores)
        rank = None
        percentile = None
        if attempt and total > 0 and attempt.score is not None:
            better_or_equal = graded_attempts.filter(score__gte=attempt.score).count()
            rank = better_or_equal
            below_or_equal = graded_attempts.filter(score__lte=attempt.score).count()
            percentile = (below_or_equal / total) * 100

        all_my_attempts = QuizAttempt.objects.filter(
            quiz_id=pk,
            student=request.user,
            is_submitted=True,
        ).order_by("-attempt_number")
        attempts_payload = []
        for a in all_my_attempts:
            duration_seconds = None
            if a.started_at and a.submitted_at:
                duration_seconds = int((a.submitted_at - a.started_at).total_seconds())
            attempts_payload.append(
                {
                    "attempt_number": a.attempt_number,
                    "score": float(a.score) if a.score is not None else None,
                    "max_score": float(a.max_score) if a.max_score is not None else None,
                    "pending_manual_grading": a.pending_manual_grading,
                    "submitted_at": a.submitted_at,
                    "duration_seconds": duration_seconds,
                }
            )

        return Response(
            {
                "attempt_id": str(attempt.id) if attempt else None,
                "score": float(attempt.score) if attempt and attempt.score is not None else None,
                "max_score": float(attempt.max_score) if attempt and attempt.max_score is not None else None,
                "pending_manual_grading": attempt.pending_manual_grading if attempt else False,
                "attempt_number": attempt.attempt_number if attempt else 0,
                "attempts_used": attempts_used,
                "attempt_limit": quiz.attempt_limit,
                "attempts_remaining": max(quiz.attempt_limit - attempts_used, 0),
                "class_stats": {
                    "graded_count": total,
                    "average_score": float(avg_score) if avg_score is not None else None,
                    "lowest_score": low_score,
                    "highest_score": high_score,
                    "rank": rank,
                    "percentile": round(percentile, 2) if percentile is not None else None,
                },
                "attempts": attempts_payload,
            }
        )


class QuizGradingListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        quiz = Quiz.objects.select_related("course_section").filter(id=pk).first()
        if not quiz:
            return Response({"detail": "Quiz not found."}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role == User.Role.TEACHER and quiz.course_section.teacher_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role not in [User.Role.TEACHER, User.Role.ADMIN]:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        attempts = QuizAttempt.objects.filter(quiz=quiz, is_submitted=True).select_related("student").order_by("-submitted_at")
        payload = []
        for a in attempts:
            row = {
                "quiz_id": str(quiz.id),
                "attempt_id": str(a.id),
                "student_id": str(a.student_id),
                "student_name": a.student.full_name,
                "score": float(a.score) if a.score is not None else None,
                "max_score": float(a.max_score) if a.max_score is not None else None,
                "pending_manual_grading": a.pending_manual_grading,
                "submitted_at": a.submitted_at,
                "answers": [],
            }
            answers = QuizAnswer.objects.filter(attempt=a).select_related("question", "selected_choice").prefetch_related("question__choices")
            for ans in answers:
                selected_choice_ids = []
                selected_choice_texts = []
                if ans.question.question_type == QuizQuestion.QuestionType.MULTI_SELECT:
                    selected_choice_ids = _parse_multi_select_choice_ids(ans.text_answer)
                    selected_ids_set = set(selected_choice_ids)
                    selected_choice_texts = [
                        choice.choice_text
                        for choice in ans.question.choices.all()
                        if str(choice.id) in selected_ids_set
                    ]
                row["answers"].append(
                    {
                        "answer_id": str(ans.id),
                        "question_id": str(ans.question_id),
                        "question_text": ans.question.question_text,
                        "question_type": ans.question.question_type,
                        "points": float(ans.question.points),
                        "selected_choice_id": str(ans.selected_choice_id) if ans.selected_choice_id else None,
                        "selected_choice_ids": selected_choice_ids,
                        "selected_choice_texts": selected_choice_texts,
                        "selected_choice_text": (
                            ", ".join(selected_choice_texts)
                            if selected_choice_texts
                            else (ans.selected_choice.choice_text if ans.selected_choice else None)
                        ),
                        "text_answer": ans.text_answer,
                        "is_correct": ans.is_correct,
                        "points_awarded": float(ans.points_awarded) if ans.points_awarded is not None else None,
                        "needs_manual_grading": ans.needs_manual_grading,
                    }
                )
            payload.append(row)
        return Response(payload)


class QuizAnswerGradeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        answer = QuizAnswer.objects.select_related("attempt__quiz__course_section", "question").filter(id=pk).first()
        if not answer:
            return Response({"detail": "Answer not found."}, status=status.HTTP_404_NOT_FOUND)

        course_section = answer.attempt.quiz.course_section
        if request.user.role == User.Role.TEACHER and course_section.teacher_id != request.user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        if request.user.role not in [User.Role.TEACHER, User.Role.ADMIN]:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        # Check if this was previously pending manual grading
        was_pending = answer.needs_manual_grading

        serializer = QuizAnswerGradeSerializer(answer, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        graded = serializer.save(
            needs_manual_grading=False,
            graded_at=timezone.now(),
            graded_by=request.user,
        )

        attempt = graded.attempt
        points_total = 0.0
        pending = False
        for ans in QuizAnswer.objects.filter(attempt=attempt):
            if ans.needs_manual_grading:
                pending = True
            if ans.points_awarded is not None:
                points_total += float(ans.points_awarded)
        attempt.score = points_total
        attempt.pending_manual_grading = pending
        attempt.save(update_fields=["score", "pending_manual_grading"])

        # Send notification when grading is complete (no more pending)
        if was_pending and not pending:
            self._send_quiz_grade_notification(attempt)

        return Response(
            {
                "attempt_id": str(attempt.id),
                "score": float(attempt.score) if attempt.score is not None else None,
                "pending_manual_grading": attempt.pending_manual_grading,
            }
        )

    def _send_quiz_grade_notification(self, attempt: QuizAttempt):
        _send_quiz_grade_notification(attempt)


class QuizQuestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _ensure_teacher_access(self, request, quiz: Quiz):
        if request.user.role == User.Role.ADMIN:
            return None
        if request.user.role == User.Role.TEACHER and quiz.course_section.teacher_id == request.user.id:
            return None
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    def _ensure_quiz_editable(self, quiz: Quiz):
        if quiz.is_published:
            return Response(
                {"detail": "Questions can only be edited while the quiz is unpublished."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def get(self, request, pk):
        quiz = Quiz.objects.select_related("course_section").filter(id=pk).first()
        if not quiz:
            return Response({"detail": "Quiz not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = self._ensure_teacher_access(request, quiz)
        if denied:
            return denied
        qs = QuizQuestion.objects.filter(quiz=quiz).prefetch_related("choices").order_by("sort_order")
        return Response(QuizQuestionWriteSerializer(qs, many=True).data)

    def post(self, request, pk):
        quiz = Quiz.objects.select_related("course_section").filter(id=pk).first()
        if not quiz:
            return Response({"detail": "Quiz not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = self._ensure_teacher_access(request, quiz)
        if denied:
            return denied
        quiz_locked = self._ensure_quiz_editable(quiz)
        if quiz_locked:
            return quiz_locked
        payload = dict(request.data)
        payload["quiz_id"] = str(quiz.id)
        serializer = QuizQuestionWriteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        question = serializer.save()
        return Response(QuizQuestionWriteSerializer(question).data, status=status.HTTP_201_CREATED)


class QuizQuestionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _resolve_question(self, pk):
        return QuizQuestion.objects.select_related("quiz__course_section").filter(id=pk).first()

    def _ensure_teacher_access(self, request, question: QuizQuestion):
        if request.user.role == User.Role.ADMIN:
            return None
        if request.user.role == User.Role.TEACHER and question.quiz.course_section.teacher_id == request.user.id:
            return None
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    def _ensure_question_editable(self, question: QuizQuestion):
        if question.quiz.is_published:
            return Response(
                {"detail": "Questions can only be edited while the quiz is unpublished."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def patch(self, request, pk):
        question = self._resolve_question(pk)
        if not question:
            return Response({"detail": "Question not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = self._ensure_teacher_access(request, question)
        if denied:
            return denied
        question_locked = self._ensure_question_editable(question)
        if question_locked:
            return question_locked
        payload = dict(request.data)
        payload["quiz_id"] = str(question.quiz_id)
        serializer = QuizQuestionWriteSerializer(question, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(QuizQuestionWriteSerializer(question).data)

    def delete(self, request, pk):
        question = self._resolve_question(pk)
        if not question:
            return Response({"detail": "Question not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = self._ensure_teacher_access(request, question)
        if denied:
            return denied
        question_locked = self._ensure_question_editable(question)
        if question_locked:
            return question_locked
        question.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class QuizQuickCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if user.role not in [User.Role.TEACHER, User.Role.ADMIN]:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        course_section_id = request.data.get("course_section_id")
        title = request.data.get("title")
        questions = request.data.get("questions") or []
        weekly_module_id = request.data.get("weekly_module_id")
        if not course_section_id or not title:
            return Response({"detail": "course_section_id and title are required."}, status=status.HTTP_400_BAD_REQUEST)

        course_section = CourseSection.objects.filter(id=course_section_id).first()
        if not course_section:
            return Response({"detail": "Course section not found."}, status=status.HTTP_404_NOT_FOUND)
        if user.role == User.Role.TEACHER and course_section.teacher_id != user.id:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        weekly_module = None
        if weekly_module_id:
            weekly_module = WeeklyModule.objects.filter(id=weekly_module_id, course_section=course_section).first()
            if not weekly_module:
                return Response({"detail": "Selected week/topic is invalid for this course section."}, status=status.HTTP_400_BAD_REQUEST)

        def to_int(value, default):
            if value in [None, ""]:
                return default
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def to_bool(value, default):
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "1", "yes", "on"}:
                    return True
                if lowered in {"false", "0", "no", "off"}:
                    return False
            return bool(value)

        score_selection_policy = request.data.get("score_selection_policy", Quiz.ScorePolicy.HIGHEST)
        if score_selection_policy not in [Quiz.ScorePolicy.HIGHEST, Quiz.ScorePolicy.LATEST]:
            score_selection_policy = Quiz.ScorePolicy.HIGHEST

        quiz = Quiz.objects.create(
            course_section=course_section,
            weekly_module=weekly_module,
            title=title,
            instructions=request.data.get("instructions"),
            time_limit_minutes=to_int(request.data.get("time_limit_minutes"), None),
            attempt_limit=to_int(request.data.get("attempt_limit"), 1),
            score_selection_policy=score_selection_policy,
            open_at=request.data.get("open_at") or None,
            close_at=request.data.get("close_at") or None,
            is_published=to_bool(request.data.get("is_published"), False),
            shuffle_questions=to_bool(request.data.get("shuffle_questions"), False),
            shuffle_choices=to_bool(request.data.get("shuffle_choices"), False),
            show_results=to_bool(request.data.get("show_results"), True),
        )
        if quiz.is_published:
            _notify_students_for_course_section(
                course_section=quiz.course_section,
                notif_type=Notification.NotificationType.NEW_QUIZ,
                title=f"New Quiz: {quiz.title}",
                body=f"A new quiz was posted in {quiz.course_section.course.title}.",
                quiz=quiz,
            )

        created_questions = []
        for idx, q in enumerate(questions):
            question_type = q.get("question_type", QuizQuestion.QuestionType.MULTIPLE_CHOICE)
            is_identification = question_type == QuizQuestion.QuestionType.IDENTIFICATION

            alternate_answers_raw = q.get("alternate_answers") or []
            normalized_alternate_answers = []
            if isinstance(alternate_answers_raw, list):
                normalized_alternate_answers = [
                    str(answer).strip()
                    for answer in alternate_answers_raw
                    if str(answer).strip()
                ]

            q_payload = {
                "quiz_id": str(quiz.id),
                "question_text": q.get("question_text"),
                "question_type": question_type,
                "points": q.get("points", 1),
                "sort_order": q.get("sort_order", idx),
                "choices": q.get("choices", []),
                "correct_answer": (q.get("correct_answer") or "").strip() if is_identification else "",
                "alternate_answers": normalized_alternate_answers if is_identification else [],
                "case_sensitive": bool(q.get("case_sensitive", False)) if is_identification else False,
            }
            s = QuizQuestionWriteSerializer(data=q_payload)
            s.is_valid(raise_exception=True)
            created_questions.append(s.save())

        _sync_course_section_students_activity_items(quiz.course_section)

        return Response(
            {
                "quiz": QuizSerializer(quiz).data,
                "questions": QuizQuestionWriteSerializer(created_questions, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class QuizQuestionsBulkView(APIView):
    """Bulk create, update, and delete questions for a quiz."""
    permission_classes = [permissions.IsAuthenticated]

    def _ensure_teacher_access(self, request, quiz: Quiz):
        """Same permission check pattern as existing quiz views."""
        if request.user.role == User.Role.ADMIN:
            return None
        if request.user.role == User.Role.TEACHER and quiz.course_section.teacher_id == request.user.id:
            return None
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

    def _ensure_quiz_editable(self, quiz: Quiz):
        if quiz.is_published:
            return Response(
                {"detail": "Questions can only be edited while the quiz is unpublished."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def post(self, request, pk):
        """
        Bulk upsert questions for a quiz.
        - Questions with no id or non-existent id → create new
        - Questions with existing id → update
        - Existing questions not in the array → delete
        """
        quiz = Quiz.objects.select_related("course_section").filter(id=pk).first()
        if not quiz:
            return Response({"detail": "Quiz not found."}, status=status.HTTP_404_NOT_FOUND)

        denied = self._ensure_teacher_access(request, quiz)
        if denied:
            return denied
        quiz_locked = self._ensure_quiz_editable(quiz)
        if quiz_locked:
            return quiz_locked

        questions_data = request.data.get("questions", [])
        serializer = QuizQuestionBulkSerializer(data={"questions": questions_data})
        serializer.is_valid(raise_exception=True)

        existing_ids = set(QuizQuestion.objects.filter(quiz=quiz).values_list("id", flat=True))
        submitted_ids = set()
        created_questions = []
        updated_questions = []

        for idx, q_data in enumerate(questions_data):
            q_payload = dict(q_data)
            q_payload["quiz_id"] = str(quiz.id)
            q_payload["sort_order"] = q_data.get("sort_order", idx)

            question_id = q_data.get("id")
            if question_id:
                # Update existing
                question = QuizQuestion.objects.filter(id=question_id, quiz=quiz).first()
                if question:
                    submitted_ids.add(str(question.id))
                    s = QuizQuestionWriteSerializer(question, data=q_payload, partial=True)
                    s.is_valid(raise_exception=True)
                    updated_questions.append(s.save())
            else:
                # Create new
                s = QuizQuestionWriteSerializer(data=q_payload)
                s.is_valid(raise_exception=True)
                question = s.save()
                submitted_ids.add(str(question.id))
                created_questions.append(question)

        # Delete questions not in the array
        to_delete = existing_ids - submitted_ids
        if to_delete:
            QuizQuestion.objects.filter(id__in=to_delete).delete()

        # Note: Quiz doesn't have a points field - total points is computed
        # from the sum of question points on the fly in the frontend

        all_questions = QuizQuestion.objects.filter(quiz=quiz).order_by("sort_order")
        return Response(QuizQuestionWriteSerializer(all_questions, many=True).data)


__all__ = [
    'QuizTakeView',
    'QuizSubmitAttemptView',
    'QuizSaveProgressView',
    'QuizMyLatestAttemptView',
    'QuizGradingListView',
    'QuizAnswerGradeView',
    'QuizQuestionsView',
    'QuizQuestionDetailView',
    'QuizQuickCreateView',
    'QuizQuestionsBulkView',
]
