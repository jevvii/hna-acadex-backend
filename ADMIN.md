# HNA Acadex - Django Admin Guide

This guide describes all administrative functions available in the Django Admin panel.

## Table of Contents
- [Accessing the Admin Panel](#accessing-the-admin-panel)
- [User Management](#user-management)
- [Course Management](#course-management)
- [Enrolling Students to Course Groups](#enrolling-students-to-course-groups)
- [Password Reset Requests](#password-reset-requests)
- [Content Management](#content-management)
- [Grading & Submissions](#grading--submissions)
- [Announcements & Calendar](#announcements--calendar)

---

## Accessing the Admin Panel

1. Navigate to: `https://your-backend-url/admin/`
2. Login with your superadmin credentials
3. You'll see all available models organized by category

---

## User Management

### Creating Users

1. Go to **Core** → **Users** → **Add User**
2. Fill in the required fields:
   - **Email**: The user's login email
   - **Personal Email**: Required for teachers/students to receive credentials
   - **Full Name**: Display name
   - **Role**: Choose from:
     - `ADMIN` - System administrator
     - `TEACHER` - Can manage courses, activities, quizzes
     - `STUDENT` - Can enroll in courses, submit activities
   - **Status**: `ACTIVE` or `INACTIVE`
   - **Auto-generate password**: ✅ Recommended
   - **Send credentials via email**: ✅ Recommended (requires personal email)

3. Click **Save**

The system will automatically:
- Generate a secure random password
- Send login credentials to the personal email
- Create the user account

### Bulk Sending Credentials

If you created users without sending credentials, you can send them later:

1. Go to **Core** → **Users**
2. Select the users you want to send credentials to
3. From the **Action** dropdown, select **"Send login credentials via email"**
4. Click **Go**

> Note: Only teachers and students can receive credentials via email.

### User Fields Reference

| Field | Description |
|-------|-------------|
| `employee_id` | Faculty/Staff ID (for teachers) |
| `student_id` | Student ID number |
| `grade_level` | Grade 11 or Grade 12 |
| `strand` | Academic strand (STEM, ABM, HUMSS, etc.) |
| `section` | Student's assigned section |
| `avatar` | Profile picture |
| `theme` | UI theme preference |

---

## Course Management

### Creating Sections (Classes)

Sections represent student cohorts (e.g., "STEM-12A", "ABM-11B"):

1. Go to **Core** → **Sections** → **Add Section**
2. Fill in:
   - **Name**: e.g., "STEM-12A"
   - **Grade Level**: Grade 11 or Grade 12
   - **Strand**: STEM, ABM, HUMSS, etc.
   - **School Year**: e.g., "2025-2026"
   - **Is Active**: ✅

### Creating Courses

1. Go to **Core** → **Courses** → **Add Course**
2. Fill in:
   - **Code**: e.g., "CS101"
   - **Title**: e.g., "Introduction to Computer Science"
   - **School Year**: e.g., "2025-2026"
   - **Semester**: First or Second
   - **Is Active**: ✅

### Creating Course Sections (Teacher Assignments)

A Course Section links a Course to a Section with a Teacher:

1. Go to **Core** → **Course Sections** → **Add Course Section**
2. Select:
   - **Course**: The subject
   - **Section**: The class
   - **Teacher**: The assigned teacher
   - **School Year** & **Semester**
   - **Is Active**: ✅

---

## Enrolling Students to Course Groups

### What is a Course Group?

A **Course Section Group** allows you to bundle multiple courses together and enroll students to all of them at once. This is useful for:
- Enrolling a class to all their semester subjects
- Managing regular class enrollments efficiently

### Step-by-Step: Enroll Students to a Course Group

#### Step 1: Create a Course Section Group

1. Go to **Core** → **Course Section Groups** → **Add Course Section Group**
2. Fill in:
   - **Name**: e.g., "STEM-12A S.Y. 2025-2026 - First Semester"
   - **Description**: Optional description
   - **School Year**: e.g., "2025-2026"
   - **Semester**: First or Second
   - **Course Sections**: Select all courses for this group (max 10)
   - **Is Active**: ✅

3. Click **Save**

#### Step 2: Enroll Students

After saving, you'll see a button: **"Enroll Students to All Courses in Group"**

1. Click the button
2. Select students from the list (use Ctrl/Cmd+Click for multiple)
3. Click **Enroll Students**

**Result**: Each selected student is enrolled in ALL courses in the group.

```
Example:
- Group: "STEM-12A First Semester"
- Courses: Math, Science, English, Filipino, PE
- Students: John, Maria, Pedro

Outcome:
- John → enrolled in Math, Science, English, Filipino, PE
- Maria → enrolled in Math, Science, English, Filipino, PE
- Pedro → enrolled in Math, Science, English, Filipino, PE
```

### Individual Enrollment

To enroll a single student to a single course:

1. Go to **Core** → **Enrollments** → **Add Enrollment**
2. Select the **Student** and **Course Section**
3. Set **Is Active**: ✅
4. Click **Save**

---

## Password Reset Requests

Students/Teachers can request password resets through the app. Admins review and process these requests.

### Processing Password Reset Requests

1. Go to **Core** → **Password Reset Requests**
2. You'll see all pending requests with:
   - User email
   - Personal email (where to send new password)
   - Status (Pending/Approved/Declined)
   - Created date

#### To Approve (Send New Password):

1. Select pending requests
2. From **Action** dropdown, select **"Approve selected password reset requests"**
3. Click **Go**

The system will:
- Generate a new random password
- Send it to the user's personal email
- Mark request as "Approved"

#### To Decline:

1. Select pending requests
2. From **Action** dropdown, select **"Decline selected password reset requests"**
3. Click **Go**

---

## Content Management

### Weekly Modules

Weekly modules organize course content by week:

1. Go to **Core** → **Weekly Modules** → **Add Weekly Module**
2. Select **Course Section**
3. Set **Week Number** and **Title**
4. Check **Is Exam Week** if applicable
5. Toggle **Is Published** to make visible to students

### Activities (Assignments)

1. Go to **Core** → **Activities** → **Add Activity**
2. Fill in:
   - **Title** and **Description**
   - **Course Section**
   - **Points** (maximum score)
   - **Deadline**
   - **Is Published**: ✅ to make visible

### Course Files

Upload files for students to download:

1. Go to **Core** → **Course Files** → **Add Course File**
2. Select the file and category:
   - `LECTURE` - Lecture materials
   - `REFERENCE` - Reference materials
   - `HANDOUT` - Handouts
   - `OTHER` - Other files
3. Set **Is Visible**: ✅ to make accessible

### Quizzes

1. Go to **Core** → **Quizzes** → **Add Quiz**
2. Set title, course section, attempt limit, time limit
3. Add questions via **Quiz Questions**:
   - Multiple Choice (`MULTIPLE_CHOICE`)
   - True/False (`TRUE_FALSE`)
   - Identification (`IDENTIFICATION`)
   - Essay (`ESSAY`)
4. Add choices for multiple choice via **Quiz Choices**
5. Set **Is Published** when ready

---

## Grading & Submissions

### Viewing Submissions

1. Go to **Core** → **Submissions**
2. Filter by status:
   - `SUBMITTED` - Needs grading
   - `GRADED` - Already graded
   - `LATE` - Submitted past deadline

### Grading Submissions

Through the Django Admin, you can view submissions but grading is typically done through the frontend app.

### Quiz Attempts

View all quiz attempts at **Core** → **Quiz Attempts**:
- See score, max score, attempt number
- Check if submitted and if pending manual grading

### Activity Reminders

View scheduled reminders at **Core** → **Activity Reminders**

---

## Announcements & Calendar

### Creating Announcements

1. Go to **Core** → **Announcements** → **Add Announcement**
2. Fill in:
   - **Title** and **Content**
   - **Course Section**: Leave empty for school-wide
   - **School Wide**: ✅ for all users
   - **Audience**: `ALL`, `STUDENTS`, `TEACHERS`
   - **Is Published**: ✅ to make visible

### Calendar Events

1. Go to **Core** → **Calendar Events** → **Add Calendar Event**
2. Set title, description, date/time, and type
3. Set **Is Personal** for personal events only

---

## Attendance Tracking

### Creating Meeting Sessions

Teachers create meeting sessions for attendance:

1. Go to **Core** → **Meeting Sessions** → **Add Meeting Session**
2. Select **Course Section**
3. Set **Date** and **Title** (e.g., "Week 3 - Monday Class")
4. Save

### Recording Attendance

Attendance is recorded through the app, but you can view/edit in:
**Core** → **Attendance Records**

---

## Notifications

View all notifications sent to users at **Core** → **Notifications**

---

## Push Tokens

View and manage push notification tokens at **Core** → **Push Tokens**
- See which devices are registered
- Deactivate invalid tokens

---

## Quick Reference: Admin Actions

| Model | Available Actions |
|-------|-------------------|
| Users | Send login credentials via email |
| Password Reset Requests | Approve selected, Decline selected |
| Course Section Groups | Enroll Students to All Courses in Group |

---

## Tips & Best Practices

1. **Use Course Groups for Batch Enrollment** - Save time by enrolling students to all their subjects at once

2. **Always Set Personal Email** - Required for sending credentials to teachers/students

3. **Check Pending Password Resets Daily** - Users are waiting for approval

4. **Use Filters** - Admin list views support filtering by status, date, course, etc.

5. **Search Functionality** - Search by name, email, or ID in most admin views

6. **Bulk Actions** - Select multiple records and apply actions at once

---

## Support

For technical issues or questions, contact the system administrator.