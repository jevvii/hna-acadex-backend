"""
Quiz-related views.
"""
from django.db.models import Avg
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
    QuizQuestionWriteSerializer,
    QuizQuestionStudentSerializer,
    QuizSerializer,
)
from core.views.common import (
    _recompute_enrollment_grade,
    _recompute_course_section_grades,
    _sync_student_activity_items,
    _sync_course_section_students_activity_items,
    _notify_students_for_course_section,
)


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

        questions = {str(q.id): q for q in QuizQuestion.objects.filter(quiz=attempt.quiz)}
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
            else:
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
        enrollment = Enrollment.objects.filter(
            course_section=attempt.quiz.course_section,
            student=attempt.student,
            is_active=True,
        ).first()
        if enrollment:
            _recompute_enrollment_grade(enrollment)
        _sync_student_activity_items(attempt.student)
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

        submitted_count = QuizAttempt.objects.filter(quiz=quiz, student=request.user, is_submitted=True).count()
        if submitted_count >= quiz.attempt_limit:
            return Response({"detail": "Attempt limit reached."}, status=status.HTTP_400_BAD_REQUEST)

        open_attempt = (
            QuizAttempt.objects.filter(quiz=quiz, student=request.user, is_submitted=False)
            .order_by("-attempt_number")
            .first()
        )
        if open_attempt:
            attempt = open_attempt
        else:
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
        existing_answers = QuizAnswer.objects.filter(attempt=attempt)
        answers_payload = []
        for a in existing_answers:
            answers_payload.append(
                {
                    "question_id": str(a.question_id),
                    "selected_choice_id": str(a.selected_choice_id) if a.selected_choice_id else None,
                    "text_answer": a.text_answer,
                }
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

        quiz = Quiz.objects.filter(id=pk).first()
        if not quiz:
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
            answers = QuizAnswer.objects.filter(attempt=a).select_related("question", "selected_choice")
            for ans in answers:
                row["answers"].append(
                    {
                        "answer_id": str(ans.id),
                        "question_id": str(ans.question_id),
                        "question_text": ans.question.question_text,
                        "question_type": ans.question.question_type,
                        "points": float(ans.question.points),
                        "selected_choice_id": str(ans.selected_choice_id) if ans.selected_choice_id else None,
                        "selected_choice_text": ans.selected_choice.choice_text if ans.selected_choice else None,
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
        enrollment = Enrollment.objects.filter(
            course_section=attempt.quiz.course_section,
            student=attempt.student,
            is_active=True,
        ).first()
        if enrollment:
            _recompute_enrollment_grade(enrollment)

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
        """Send push notification when quiz grading is complete."""
        from core.push_notifications import send_push_notification_to_users

        try:
            quiz = attempt.quiz
            student = attempt.student

            # Create in-app notification
            Notification.objects.create(
                recipient=student,
                type=Notification.NotificationType.GRADE_RELEASED,
                title=f"Quiz Graded: {quiz.title}",
                body=f"Your quiz '{quiz.title}' has been graded. Score: {attempt.score}/{attempt.max_score}",
                course_section=quiz.course_section,
                quiz=quiz,
            )

            # Send push notification
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


class QuizQuestionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def _ensure_teacher_access(self, request, quiz: Quiz):
        if request.user.role == User.Role.ADMIN:
            return None
        if request.user.role == User.Role.TEACHER and quiz.course_section.teacher_id == request.user.id:
            return None
        return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

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
        payload = dict(request.data)
        payload["quiz_id"] = str(quiz.id)
        serializer = QuizQuestionWriteSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        question = serializer.save()
        _recompute_course_section_grades(quiz.course_section)
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

    def patch(self, request, pk):
        question = self._resolve_question(pk)
        if not question:
            return Response({"detail": "Question not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = self._ensure_teacher_access(request, question)
        if denied:
            return denied
        payload = dict(request.data)
        payload["quiz_id"] = str(question.quiz_id)
        serializer = QuizQuestionWriteSerializer(question, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        _recompute_course_section_grades(question.quiz.course_section)
        return Response(QuizQuestionWriteSerializer(question).data)

    def delete(self, request, pk):
        question = self._resolve_question(pk)
        if not question:
            return Response({"detail": "Question not found."}, status=status.HTTP_404_NOT_FOUND)
        denied = self._ensure_teacher_access(request, question)
        if denied:
            return denied
        course_section = question.quiz.course_section
        question.delete()
        _recompute_course_section_grades(course_section)
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

        quiz = Quiz.objects.create(
            course_section=course_section,
            weekly_module=weekly_module,
            title=title,
            instructions=request.data.get("instructions"),
            time_limit_minutes=to_int(request.data.get("time_limit_minutes"), None),
            attempt_limit=to_int(request.data.get("attempt_limit"), 1),
            open_at=request.data.get("open_at") or None,
            close_at=request.data.get("close_at") or None,
            is_published=request.data.get("is_published", True),
            shuffle_questions=request.data.get("shuffle_questions", False),
            shuffle_choices=request.data.get("shuffle_choices", False),
            show_results=request.data.get("show_results", True),
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
            q_payload = {
                "quiz_id": str(quiz.id),
                "question_text": q.get("question_text"),
                "question_type": q.get("question_type", QuizQuestion.QuestionType.MULTIPLE_CHOICE),
                "points": q.get("points", 1),
                "sort_order": q.get("sort_order", idx),
                "choices": q.get("choices", []),
            }
            s = QuizQuestionWriteSerializer(data=q_payload)
            s.is_valid(raise_exception=True)
            created_questions.append(s.save())

        _recompute_course_section_grades(quiz.course_section)
        _sync_course_section_students_activity_items(quiz.course_section)

        return Response(
            {
                "quiz": QuizSerializer(quiz).data,
                "questions": QuizQuestionWriteSerializer(created_questions, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


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
]