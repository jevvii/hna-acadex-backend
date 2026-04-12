# Grading System Cleanup Checklist
# Complete these after React Native app migrates

## Fields to Remove (after RN migration)
- [ ] GradeEntry.is_published
- [ ] Enrollment.is_final_published

## Endpoints to Remove (after RN migration)
- [ ] GET /api/course-sections/{id}/grades/student/

## Models to Remove (after confirming no usage)
- [ ] AssignmentWeight (superseded by GradeWeightConfig)

## Functions to Clean Up
- [ ] _compute_enrollment_grade() -- remove auto-call wiring
      (already removed from triggers, keep function for diagnostics)
- [ ] _compute_period_score() in backfill command
      (replaced by compute_period_grade())

## Critical Backend Verification (Before Declaring Migration Complete)

The RN app does NOT call the deprecated `/grades/student/` endpoint.
Its grade data comes from:
1. `/api/courses/student/` -- returns StudentCourse with final_grade, final_grade_letter, grade_summary
2. `/api/course-sections/{id}/gradebook/` -- returns teacher gradebook

Before removing deprecated fields/endpoints, verify:
- [ ] `/api/courses/student/` computes final_grade from GradeEntry averages (not Enrollment.final_grade)
- [ ] `/api/courses/student/` sets grade_summary.has_released_grades from SectionReportCard.is_published (not GradeEntry.is_published)
- [ ] `/api/course-sections/{id}/gradebook/` continues to work with the new model
- [ ] Grade submit endpoint `/api/course-sections/{id}/grades/submit/` works end-to-end
- [ ] Report card publish endpoint `/api/advisory/{section_id}/report-card/publish/` works end-to-end
- [ ] Web app fully functional with new grade system

## Verification Steps Before Removal
1. grep -rn "is_published" hna-acadex-rn/src/
2. grep -rn "is_final_published" hna-acadex-rn/src/
3. grep -rn "grades/student" hna-acadex-rn/src/
4. grep -rn "AssignmentWeight" across entire codebase
5. Run full RN test suite
6. Confirm RN app uses /api/students/me/report-card/ (if/when student report card screen is added)
7. Confirm no third-party integrations reference deprecated endpoints

## RN App Audit Summary (as of 2026-04-12)

### Files referencing grade data:
| File | Grade Fields Used | API Endpoint |
|------|-------------------|--------------|
| src/types/index.ts | Enrollment.final_grade, StudentCourse.final_grade/final_grade_letter/grade_summary/grade_overridden, GradebookStudent.final_grade/final_grade_letter/grade_overridden/manual_final_grade, GradeSummary.has_released_grades, NotificationType.grade_released | N/A (types only) |
| src/components/shared/CourseCard.tsx | StudentCourse.final_grade, final_grade_letter, grade_summary (has_released_grades, has_pending, is_partial, etc.) | Reads from StudentCourse data |
| src/screens/course/tabs/GradesTab.tsx | GradebookData (props) | Receives gradebookData prop |
| src/components/gradebook/GradebookTable.tsx | GradebookStudent.final_grade, final_grade_letter, grade_overridden | Reads from gradebookData prop |
| src/components/screens/course/CourseScreen.tsx | gradebookData state, student.final_grade, final_grade_letter | api.get('/course-sections/${id}/gradebook/') |
| src/components/screens/student/StudentDashboard.tsx | StudentCourse (final_grade, final_grade_letter, grade_summary) | api.get('/courses/student/') |
| src/hooks/useCourses.ts | StudentCourse data | api.get('/courses/student/') |
| src/components/screens/NotificationsScreen.tsx | NotificationType.grade_released | N/A (notification display only) |

### Endpoints the RN app calls (grade-related):
| Endpoint | Used By | Deprecated? |
|----------|---------|-------------|
| GET /api/courses/student/ | StudentDashboard, useCourses | No -- but must update internals to use new model |
| GET /api/course-sections/{id}/gradebook/ | CourseScreen | No |
| PATCH /api/activity-submissions/{id}/grade/ | GradebookTable | No |

### Endpoints the RN app does NOT call:
| Endpoint | Status |
|----------|--------|
| GET /api/course-sections/{id}/grades/student/ | Deprecated -- NOT called by RN app |
| GET /api/students/me/report-card/ | New -- NOT yet called by RN app |
| POST /api/course-sections/{id}/grades/submit/ | New -- NOT yet called by RN app |
| POST /api/advisory/{section_id}/report-card/publish/ | New -- NOT yet called by RN app |

### Fields the RN app does NOT reference:
- Enrollment.is_final_published -- NOT in any RN type or component
- GradeEntry.is_published -- NOT referenced in RN code