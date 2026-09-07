import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from models import (
    db,
    User,
    UserProfile,
    UserSkill,
    TargetCareer,
    SkillGapAnalysis,
    SkillGapItem,
    Course,
    UserRoadmap,
    RoadmapMilestone
)
from services.skill_normalizer import normalize_skill, skills_match
from services.skill_gap_service import skill_gap_service

class RoadmapService:
    """
    Intelligent, Milestone-Driven AI Career Roadmap Generator.
    Sequences skill gaps, topic deficits, prerequisites, and learning velocity
    into an ordered 5-phase multi-week pathway with capstones and interview prep.
    """

    PHASE_DEFINITIONS = [
        {
            'number': 1,
            'name': 'Foundations & Prerequisites',
            'badge': 'Phase 1: Foundations',
            'icon': 'fa-solid fa-cube',
            'summary': 'Master foundational syntax, basic querying, and essential data concepts required as baseline prerequisites.'
        },
        {
            'number': 2,
            'name': 'Core Tool Mastery & Data Manipulation',
            'badge': 'Phase 2: Core Tools',
            'icon': 'fa-solid fa-screwdriver-wrench',
            'summary': 'Deepen proficiency in primary analytics tools, data wrangling, multi-table joins, and interactive data modeling.'
        },
        {
            'number': 3,
            'name': 'Advanced Optimization & Analytics Specialization',
            'badge': 'Phase 3: Specialization',
            'icon': 'fa-solid fa-bolt',
            'summary': 'Elevate your problem-solving with advanced window functions, DAX measures, statistical testing, and performance tuning.'
        },
        {
            'number': 4,
            'name': 'Capstone Portfolio Projects & Real-World Cases',
            'badge': 'Phase 4: Portfolio Projects',
            'icon': 'fa-solid fa-diagram-project',
            'summary': 'Build employer-ready, end-to-end portfolio projects that demonstrate real-world business impact.'
        },
        {
            'number': 5,
            'name': 'Technical Interview Prep & Career Launch',
            'badge': 'Phase 5: Career Launch',
            'icon': 'fa-solid fa-rocket',
            'summary': 'Prepare for live coding assessments, business case interviews, portfolio reviews, and technical screenings.'
        }
    ]

    def get_or_generate_roadmap(self, user=None, target_role=None, force_regenerate=False):
        """
        Retrieves existing active roadmap for the user or generates a fresh personalized pathway.
        """
        if user and not force_regenerate:
            # Check for existing roadmap in DB
            existing = UserRoadmap.query.filter_by(user_id=user.id).order_by(UserRoadmap.id.desc()).first()
            if existing and existing.milestones:
                # Recalculate progress to ensure consistency
                existing.calculate_progress()
                db.session.commit()
                return self._format_roadmap_dict(existing, user)

        # Otherwise generate a new dynamic roadmap
        return self.generate_roadmap(user=user, target_role=target_role)

    def generate_roadmap(self, user=None, target_role=None):
        """
        Main AI Roadmap generation pipeline:
        1. Runs Skill Gap Analysis to extract missing/partial skills and topic deficits.
        2. Retrieves user learning velocity (hours/week).
        3. Dynamically structures milestones across 5 progressive phases with prerequisite sequencing.
        4. Attaches concrete actionable tasks, checkpoint deliverables, and curated learning resources.
        5. Persists the generated roadmap and milestones to SQLite.
        """
        # 1. Fetch Skill Gap Analysis
        gap_analysis = skill_gap_service.analyze_skill_gap(user=user, target_role=target_role)
        target_role_display = gap_analysis.get('target_role', 'Data Analyst')
        is_custom_role = gap_analysis.get('is_custom_role', False)
        market_status = gap_analysis.get('market_status', 'Verified Industry Benchmark')
        gap_items = gap_analysis.get('gap_items', [])

        # 2. Extract weekly hours from user profile
        profile = user.user_profile if user else None
        weekly_hours = 10.0
        if profile and profile.learning_hours_per_week and profile.learning_hours_per_week > 0:
            weekly_hours = float(profile.learning_hours_per_week)

        # 3. Classify gap skills into categories
        missing_skills = [g for g in gap_items if g['status'] == 'MISSING']
        partial_skills = [g for g in gap_items if g['status'] == 'PARTIAL']
        strong_skills = [g for g in gap_items if g['status'] == 'STRONG']

        # 4. Generate Phased Milestones
        milestones_data = []
        current_week = 1

        # --- Phase 1: Foundations & Prerequisites ---
        phase1_items = self._build_phase1_milestones(missing_skills, partial_skills, weekly_hours, current_week, target_role_display)
        milestones_data.extend(phase1_items)
        if phase1_items:
            current_week = phase1_items[-1]['week_end'] + 1

        # --- Phase 2: Core Tool Mastery & Data Manipulation ---
        phase2_items = self._build_phase2_milestones(missing_skills, partial_skills, strong_skills, weekly_hours, current_week, target_role_display)
        milestones_data.extend(phase2_items)
        if phase2_items:
            current_week = phase2_items[-1]['week_end'] + 1

        # --- Phase 3: Advanced Optimization & Specialization ---
        phase3_items = self._build_phase3_milestones(missing_skills, partial_skills, strong_skills, weekly_hours, current_week, target_role_display)
        milestones_data.extend(phase3_items)
        if phase3_items:
            current_week = phase3_items[-1]['week_end'] + 1

        # --- Phase 4: Capstone Portfolio Projects ---
        phase4_items = self._build_phase4_milestones(gap_items, weekly_hours, current_week, target_role_display)
        milestones_data.extend(phase4_items)
        if phase4_items:
            current_week = phase4_items[-1]['week_end'] + 1

        # --- Phase 5: Technical Interview Prep & Career Launch ---
        phase5_items = self._build_phase5_milestones(weekly_hours, current_week, target_role_display)
        milestones_data.extend(phase5_items)
        if phase5_items:
            current_week = phase5_items[-1]['week_end']

        total_weeks = max(4, current_week)
        total_hours = sum(m['estimated_hours'] for m in milestones_data)

        # 5. Persist or update in SQLite database
        if user:
            # Delete previous roadmaps for clean regeneration
            UserRoadmap.query.filter_by(user_id=user.id).delete()
            
            roadmap_record = UserRoadmap(
                user_id=user.id,
                target_role=target_role_display,
                total_weeks=total_weeks,
                total_hours=total_hours,
                weekly_hours=weekly_hours,
                completion_percentage=0,
                status='In Progress'
            )
            db.session.add(roadmap_record)
            db.session.flush()

            for m_data in milestones_data:
                milestone = RoadmapMilestone(
                    roadmap_id=roadmap_record.id,
                    phase_number=m_data['phase_number'],
                    phase_name=m_data['phase_name'],
                    week_start=m_data['week_start'],
                    week_end=m_data['week_end'],
                    title=m_data['title'],
                    description=m_data['description'],
                    skill=m_data['skill'],
                    priority=m_data['priority'],
                    estimated_hours=m_data['estimated_hours'],
                    checkpoint_title=m_data['checkpoint_title'],
                    checkpoint_description=m_data['checkpoint_description'],
                    is_completed=False
                )
                milestone.set_tasks(m_data['tasks'])
                milestone.set_resources(m_data['recommended_resources'])
                db.session.add(milestone)

            db.session.commit()
            return self._format_roadmap_dict(roadmap_record, user)

        # Guest response structure
        return {
            'id': None,
            'user_id': None,
            'target_role': target_role_display,
            'is_custom_role': is_custom_role,
            'market_status': market_status,
            'readiness_score': gap_analysis.get('readiness_score', 0),
            'total_weeks': total_weeks,
            'total_hours': total_hours,
            'weekly_hours': weekly_hours,
            'completion_percentage': 0,
            'status': 'In Progress',
            'milestones': milestones_data,
            'phases': self._group_milestones_by_phase(milestones_data)
        }

    def _build_phase1_milestones(self, missing_skills, partial_skills, weekly_hours, start_week, target_role):
        """Constructs foundational prerequisite milestones (e.g. Basic SQL, Python syntax, Excel basics)."""
        milestones = []
        w_start = start_week

        # Look for SQL foundation needs
        sql_gap = next((g for g in (missing_skills + partial_skills) if skills_match(g['skill_name'], 'SQL')), None)
        if sql_gap:
            dur = 14.0
            weeks_needed = max(1, math.ceil(dur / max(1.0, weekly_hours)))
            w_end = w_start + weeks_needed - 1
            
            tasks = [
                {'id': 1, 'text': 'Learn SELECT, DISTINCT, WHERE, AND/OR/NOT filtering conditions', 'completed': False},
                {'id': 2, 'text': 'Practice sorting with ORDER BY and result limits with LIMIT / TOP', 'completed': False},
                {'id': 3, 'text': 'Master aggregate functions: COUNT(), SUM(), AVG(), MIN(), MAX()', 'completed': False},
                {'id': 4, 'text': 'Group records with GROUP BY and filter aggregates with HAVING clauses', 'completed': False}
            ]
            
            resources = self._get_course_resources_for_skill('SQL', level='Beginner', limit=2)
            
            milestones.append({
                'phase_number': 1,
                'phase_name': 'Foundations & Prerequisites',
                'week_start': w_start,
                'week_end': w_end,
                'title': 'SQL Querying Foundations & Filtering',
                'description': f'Establish core database querying fundamentals essential for {target_role} workflows.',
                'skill': 'SQL',
                'priority': 'Critical' if sql_gap['importance'] == 'Critical' else 'High',
                'estimated_hours': dur,
                'checkpoint_title': 'Checkpoint 1: Customer Transaction Query Script',
                'checkpoint_description': 'Write a clean SQL script that filters, groups, and summarizes total sales revenue by product category from raw database tables.',
                'tasks': tasks,
                'recommended_resources': resources,
                'is_completed': False
            })
            w_start = w_end + 1

        # Look for Python syntax foundation needs
        py_gap = next((g for g in missing_skills if skills_match(g['skill_name'], 'Python')), None)
        if py_gap:
            dur = 12.0
            weeks_needed = max(1, math.ceil(dur / max(1.0, weekly_hours)))
            w_end = w_start + weeks_needed - 1
            
            tasks = [
                {'id': 1, 'text': 'Understand Python variables, primitive types (int, float, str, bool)', 'completed': False},
                {'id': 2, 'text': 'Master core data structures: Lists, Dictionaries, Tuples, and Sets', 'completed': False},
                {'id': 3, 'text': 'Write conditional control flow (if-elif-else) and loops (for, while)', 'completed': False},
                {'id': 4, 'text': 'Create modular functions with arguments, return values, and error handling', 'completed': False}
            ]
            resources = self._get_course_resources_for_skill('Python', level='Beginner', limit=2)

            milestones.append({
                'phase_number': 1,
                'phase_name': 'Foundations & Prerequisites',
                'week_start': w_start,
                'week_end': w_end,
                'title': 'Python Programming & Data Structures',
                'description': 'Build solid programmatic foundations in Python for data manipulation and scripting.',
                'skill': 'Python',
                'priority': 'High',
                'estimated_hours': dur,
                'checkpoint_title': 'Checkpoint 2: CLI Data Parser Script',
                'checkpoint_description': 'Build a Python script that ingests a sample CSV file, parses data into dictionaries, and computes summary statistics.',
                'tasks': tasks,
                'recommended_resources': resources,
                'is_completed': False
            })
            w_start = w_end + 1

        # Fallback if no specific foundation gaps found
        if not milestones:
            milestones.append({
                'phase_number': 1,
                'phase_name': 'Foundations & Prerequisites',
                'week_start': w_start,
                'week_end': w_start + 1,
                'title': f'{target_role} Core Prerequisites Baseline',
                'description': 'Quick review of fundamental query syntax, data types, and spreadsheet operations.',
                'skill': 'Data Fundamentals',
                'priority': 'Medium',
                'estimated_hours': 10.0,
                'checkpoint_title': 'Checkpoint 1: Baseline Skills Verification',
                'checkpoint_description': 'Complete initial technical self-check and environment setup (VS Code, Python, SQLite/PostgreSQL).',
                'tasks': [
                    {'id': 1, 'text': 'Configure local development environment and database clients', 'completed': False},
                    {'id': 2, 'text': 'Review analytical problem-solving methodologies', 'completed': False}
                ],
                'recommended_resources': self._get_course_resources_for_skill('SQL', limit=1),
                'is_completed': False
            })

        return milestones

    def _build_phase2_milestones(self, missing_skills, partial_skills, strong_skills, weekly_hours, start_week, target_role):
        """Constructs core tool mastery milestones (e.g., intermediate SQL JOINs, Pandas wrangling, Power BI modeling)."""
        milestones = []
        w_start = start_week

        # 1. Intermediate SQL Multi-Table Joins & Aggregations
        dur = 14.0
        weeks_needed = max(1, math.ceil(dur / max(1.0, weekly_hours)))
        w_end = w_start + weeks_needed - 1
        
        tasks = [
            {'id': 1, 'text': 'Master INNER JOIN, LEFT JOIN, RIGHT JOIN, and FULL OUTER JOINs', 'completed': False},
            {'id': 2, 'text': 'Construct subqueries in SELECT, FROM, and WHERE clauses', 'completed': False},
            {'id': 3, 'text': 'Combine query results with UNION and UNION ALL', 'completed': False},
            {'id': 4, 'text': 'Solve intermediate SQL challenges on LeetCode / HackerRank', 'completed': False}
        ]
        milestones.append({
            'phase_number': 2,
            'phase_name': 'Core Tool Mastery & Data Manipulation',
            'week_start': w_start,
            'week_end': w_end,
            'title': 'Relational Data Modeling & Multi-Table SQL Joins',
            'description': 'Query across normalized multi-table database schemas to produce complex analytical datasets.',
            'skill': 'SQL',
            'priority': 'Critical',
            'estimated_hours': dur,
            'checkpoint_title': 'Checkpoint 3: Multi-Table Customer Churn Extraction',
            'checkpoint_description': 'Construct a 4-table relational query joining Users, Orders, Subscriptions, and Support Tickets to extract cohort metrics.',
            'tasks': tasks,
            'recommended_resources': self._get_course_resources_for_skill('SQL', level='Intermediate', limit=2),
            'is_completed': False
        })
        w_start = w_end + 1

        # 2. Pandas & Data Wrangling
        dur = 16.0
        weeks_needed = max(1, math.ceil(dur / max(1.0, weekly_hours)))
        w_end = w_start + weeks_needed - 1

        tasks = [
            {'id': 1, 'text': 'Load, explore, and slice Pandas DataFrames and Series', 'completed': False},
            {'id': 2, 'text': 'Clean missing data with dropna(), fillna(), and interpolate()', 'completed': False},
            {'id': 3, 'text': 'Perform grouping, aggregation, and pivot tables with groupby() and pivot_table()', 'completed': False},
            {'id': 4, 'text': 'Merge, concatenate, and reshape complex messy datasets', 'completed': False}
        ]
        milestones.append({
            'phase_number': 2,
            'phase_name': 'Core Tool Mastery & Data Manipulation',
            'week_start': w_start,
            'week_end': w_end,
            'title': 'Data Wrangling & Transformation with Pandas',
            'description': 'Ingest, clean, transform, and structure real-world datasets into analysis-ready formats using Python.',
            'skill': 'Python',
            'priority': 'High',
            'estimated_hours': dur,
            'checkpoint_title': 'Checkpoint 4: Automated Data Cleaning Pipeline',
            'checkpoint_description': 'Develop a Python script that ingests an unformatted raw CSV with nulls, duplicates, and faulty types and outputs a clean dataset.',
            'tasks': tasks,
            'recommended_resources': self._get_course_resources_for_skill('Python', level='Intermediate', limit=2),
            'is_completed': False
        })
        w_start = w_end + 1

        # 3. BI & Visual Modeling (Power BI or Tableau)
        dur = 14.0
        weeks_needed = max(1, math.ceil(dur / max(1.0, weekly_hours)))
        w_end = w_start + weeks_needed - 1

        tasks = [
            {'id': 1, 'text': 'Connect Power BI / Tableau to relational and flat file data sources', 'completed': False},
            {'id': 2, 'text': 'Design Star Schema dimensional models (Fact vs Dimension tables)', 'completed': False},
            {'id': 3, 'text': 'Create calculated columns and basic DAX measures (CALCULATE, RELATED)', 'completed': False},
            {'id': 4, 'text': 'Build interactive visual dashboards with slicers, drill-downs, and KPI cards', 'completed': False}
        ]
        milestones.append({
            'phase_number': 2,
            'phase_name': 'Core Tool Mastery & Data Manipulation',
            'week_start': w_start,
            'week_end': w_end,
            'title': 'Business Intelligence & Interactive Dashboarding',
            'description': f'Design dynamic executive dashboards and data models aligned with {target_role} expectations.',
            'skill': 'Power BI',
            'priority': 'High',
            'estimated_hours': dur,
            'checkpoint_title': 'Checkpoint 5: Executive Sales & Operations Dashboard',
            'checkpoint_description': 'Publish an interactive multi-page BI report featuring dynamic KPI cards, time slicers, and regional heatmaps.',
            'tasks': tasks,
            'recommended_resources': self._get_course_resources_for_skill('Power BI', limit=2),
            'is_completed': False
        })

        return milestones

    def _build_phase3_milestones(self, missing_skills, partial_skills, strong_skills, weekly_hours, start_week, target_role):
        """Constructs advanced specialization milestones (Window functions, statistical inference, ML modeling)."""
        milestones = []
        w_start = start_week

        # 1. Advanced SQL Window Functions & CTEs
        dur = 14.0
        weeks_needed = max(1, math.ceil(dur / max(1.0, weekly_hours)))
        w_end = w_start + weeks_needed - 1

        tasks = [
            {'id': 1, 'text': 'Master Common Table Expressions (WITH clause) and recursive CTEs', 'completed': False},
            {'id': 2, 'text': 'Implement ranking window functions: ROW_NUMBER(), RANK(), DENSE_RANK()', 'completed': False},
            {'id': 3, 'text': 'Compute running totals and moving averages using OVER (PARTITION BY ... ORDER BY ...)', 'completed': False},
            {'id': 4, 'text': 'Calculate period-over-period growth with LAG() and LEAD()', 'completed': False}
        ]
        milestones.append({
            'phase_number': 3,
            'phase_name': 'Advanced Optimization & Analytics Specialization',
            'week_start': w_start,
            'week_end': w_end,
            'title': 'Advanced SQL Window Functions & CTEs',
            'description': 'Master high-level SQL techniques used by senior analytics practitioners to solve complex business queries.',
            'skill': 'SQL',
            'priority': 'Critical',
            'estimated_hours': dur,
            'checkpoint_title': 'Checkpoint 6: Year-Over-Year Retention SQL Model',
            'checkpoint_description': 'Write an advanced SQL script calculating Month-over-Month growth rates and user retention cohorts using Window Functions.',
            'tasks': tasks,
            'recommended_resources': self._get_course_resources_for_skill('SQL', level='Advanced', limit=2),
            'is_completed': False
        })
        w_start = w_end + 1

        # 2. Statistics & Hypothesis Testing
        dur = 14.0
        weeks_needed = max(1, math.ceil(dur / max(1.0, weekly_hours)))
        w_end = w_start + weeks_needed - 1

        tasks = [
            {'id': 1, 'text': 'Understand probability distributions (Normal, Binomial, Poisson)', 'completed': False},
            {'id': 2, 'text': 'Formulate null and alternative hypotheses, p-values, and alpha thresholds', 'completed': False},
            {'id': 3, 'text': 'Conduct two-sample t-tests, ANOVA, and Chi-Square tests of independence', 'completed': False},
            {'id': 4, 'text': 'Design and interpret A/B testing experiment results with confidence intervals', 'completed': False}
        ]
        milestones.append({
            'phase_number': 3,
            'phase_name': 'Advanced Optimization & Analytics Specialization',
            'week_start': w_start,
            'week_end': w_end,
            'title': 'Statistical Inference & A/B Experimentation',
            'description': 'Validate business decisions with rigorous statistical testing, hypothesis evaluation, and experiment design.',
            'skill': 'Statistics',
            'priority': 'High',
            'estimated_hours': dur,
            'checkpoint_title': 'Checkpoint 7: A/B Testing Conversion Evaluation',
            'checkpoint_description': 'Run a complete statistical analysis in Python comparing landing page conversion rates, calculating p-values and confidence intervals.',
            'tasks': tasks,
            'recommended_resources': self._get_course_resources_for_skill('Statistics', limit=2),
            'is_completed': False
        })

        return milestones

    def _build_phase4_milestones(self, gap_items, weekly_hours, start_week, target_role):
        """Constructs capstone portfolio project milestones."""
        w_start = start_week
        dur = 20.0
        weeks_needed = max(2, math.ceil(dur / max(1.0, weekly_hours)))
        w_end = w_start + weeks_needed - 1

        tasks = [
            {'id': 1, 'text': f'Identify and scope an end-to-end business problem relevant to {target_role}', 'completed': False},
            {'id': 2, 'text': 'Extract, clean, and model raw multi-source data with SQL and Python', 'completed': False},
            {'id': 3, 'text': 'Build an interactive BI reporting dashboard with dynamic slicers and KPI metrics', 'completed': False},
            {'id': 4, 'text': 'Document findings in a GitHub repository with README, architecture diagram, and insights summary', 'completed': False}
        ]

        return [{
            'phase_number': 4,
            'phase_name': 'Capstone Portfolio Projects & Real-World Cases',
            'week_start': w_start,
            'week_end': w_end,
            'title': f'End-to-End {target_role} Portfolio Capstone Project',
            'description': f'Develop and publish a comprehensive, employer-ready analytics project solving an authentic business challenge for {target_role}.',
            'skill': 'Portfolio Capstone',
            'priority': 'Critical',
            'estimated_hours': dur,
            'checkpoint_title': 'Checkpoint 8: GitHub Portfolio Repository & Executive Presentation',
            'checkpoint_description': 'Publish a public GitHub repo with clean modular code, interactive dashboard link, and a 1-page executive summary memo.',
            'tasks': tasks,
            'recommended_resources': self._get_course_resources_for_type('Project', limit=2),
            'is_completed': False
        }]

    def _build_phase5_milestones(self, weekly_hours, start_week, target_role):
        """Constructs technical interview prep & career launch milestones."""
        w_start = start_week
        dur = 15.0
        weeks_needed = max(1, math.ceil(dur / max(1.0, weekly_hours)))
        w_end = w_start + weeks_needed - 1

        tasks = [
            {'id': 1, 'text': 'Complete top 30 SQL interview questions under timed conditions', 'completed': False},
            {'id': 2, 'text': 'Practice live Python data manipulation and Pandas problem solving', 'completed': False},
            {'id': 3, 'text': 'Review behavioral STAR stories (Situation, Task, Action, Result) for portfolio projects', 'completed': False},
            {'id': 4, 'text': 'Conduct mock technical screen and optimize LinkedIn / resume keywords', 'completed': False}
        ]

        return [{
            'phase_number': 5,
            'phase_name': 'Technical Interview Prep & Career Launch',
            'week_start': w_start,
            'week_end': w_end,
            'title': 'Technical Interview Prep & Scenario Problem Solving',
            'description': f'Rigorous preparation for technical coding rounds, SQL tests, business case assessments, and behavioral interviews for {target_role}.',
            'skill': 'Interview Prep',
            'priority': 'High',
            'estimated_hours': dur,
            'checkpoint_title': 'Checkpoint 9: Mock Technical Interview Simulation',
            'checkpoint_description': 'Complete a 45-minute live technical coding simulation solving a real-world business case with SQL and Python.',
            'tasks': tasks,
            'recommended_resources': self._get_course_resources_for_type('Practice', limit=2),
            'is_completed': False
        }]

    def toggle_milestone_task(self, roadmap_id, milestone_id, task_id, completed=True):
        """Toggles completion of a specific task in a milestone and updates overall progress."""
        try:
            milestone = db.session.get(RoadmapMilestone, milestone_id)
            if not milestone or milestone.roadmap_id != roadmap_id:
                return {'success': False, 'error': 'Milestone not found'}

            tasks = milestone.get_tasks()
            task_found = False
            for t in tasks:
                if str(t.get('id')) == str(task_id):
                    t['completed'] = bool(completed)
                    task_found = True
                    break

            if not task_found:
                return {'success': False, 'error': 'Task not found in milestone'}

            milestone.set_tasks(tasks)

            # Check if all tasks in milestone are completed
            all_done = all(t.get('completed', False) for t in tasks) if tasks else False
            milestone.is_completed = all_done
            milestone.completed_at = datetime.now(timezone.utc) if all_done else None

            roadmap = milestone.roadmap
            overall_progress = roadmap.calculate_progress()
            db.session.commit()

            return {
                'success': True,
                'milestone_id': milestone.id,
                'task_id': task_id,
                'task_completed': completed,
                'is_milestone_completed': milestone.is_completed,
                'milestone_tasks_completed': sum(1 for t in tasks if t.get('completed')),
                'milestone_tasks_total': len(tasks),
                'overall_progress': overall_progress,
                'roadmap_status': roadmap.status
            }
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}

    def update_milestone_status(self, roadmap_id, milestone_id, is_completed=True):
        """Marks an entire milestone and all its subtasks as completed or incomplete."""
        try:
            milestone = db.session.get(RoadmapMilestone, milestone_id)
            if not milestone or milestone.roadmap_id != roadmap_id:
                return {'success': False, 'error': 'Milestone not found'}

            milestone.is_completed = bool(is_completed)
            milestone.completed_at = datetime.now(timezone.utc) if is_completed else None

            # Mark all subtasks with same status
            tasks = milestone.get_tasks()
            for t in tasks:
                t['completed'] = bool(is_completed)
            milestone.set_tasks(tasks)

            roadmap = milestone.roadmap
            overall_progress = roadmap.calculate_progress()
            db.session.commit()

            return {
                'success': True,
                'milestone_id': milestone.id,
                'is_completed': milestone.is_completed,
                'overall_progress': overall_progress,
                'roadmap_status': roadmap.status
            }
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}

    def _get_course_resources_for_skill(self, skill_name, level=None, limit=2):
        """Finds top curated courses matching skill and level."""
        canonical_skill, _ = normalize_skill(skill_name)
        courses = Course.query.filter_by(is_active=True).all()
        matched = []
        for c in courses:
            c_canon, _ = normalize_skill(c.skill)
            if skills_match(c_canon, canonical_skill):
                if level is None or c.level == level or c.level == 'All Levels':
                    matched.append({
                        'id': c.id,
                        'title': c.title,
                        'provider': c.provider,
                        'url': c.url,
                        'resource_type': c.resource_type,
                        'duration_hours': c.duration_hours,
                        'is_free': c.is_free,
                        'level': c.level
                    })
                    if len(matched) >= limit:
                        break
        return matched

    def _get_course_resources_for_type(self, resource_type, limit=2):
        """Finds top curated courses matching resource type (Project, Practice, etc.)."""
        courses = Course.query.filter_by(is_active=True, resource_type=resource_type).limit(limit).all()
        return [{
            'id': c.id,
            'title': c.title,
            'provider': c.provider,
            'url': c.url,
            'resource_type': c.resource_type,
            'duration_hours': c.duration_hours,
            'is_free': c.is_free,
            'level': c.level
        } for c in courses]

    def _format_roadmap_dict(self, roadmap, user=None):
        """Formats a UserRoadmap ORM entity into a clean template-friendly dictionary."""
        milestones = [m.to_dict() for m in roadmap.milestones]
        
        # Calculate summary KPIs
        total_tasks = sum(len(m.get('tasks', [])) for m in milestones)
        completed_tasks = sum(sum(1 for t in m.get('tasks', []) if t.get('completed')) for m in milestones)
        completed_milestones_count = sum(1 for m in milestones if m.get('is_completed'))

        return {
            'id': roadmap.id,
            'user_id': roadmap.user_id,
            'target_role': roadmap.target_role,
            'total_weeks': roadmap.total_weeks,
            'total_hours': roadmap.total_hours,
            'weekly_hours': roadmap.weekly_hours,
            'completion_percentage': roadmap.completion_percentage,
            'status': roadmap.status,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'total_milestones': len(milestones),
            'completed_milestones': completed_milestones_count,
            'milestones': milestones,
            'phases': self._group_milestones_by_phase(milestones)
        }

    def _group_milestones_by_phase(self, milestones):
        """Groups flat milestone list into sequential phases."""
        phases_map = {p['number']: {**p, 'milestones': [], 'is_completed': False, 'total_hours': 0} for p in self.PHASE_DEFINITIONS}
        
        for m in milestones:
            p_num = m['phase_number']
            if p_num in phases_map:
                phases_map[p_num]['milestones'].append(m)
                phases_map[p_num]['total_hours'] += m.get('estimated_hours', 0)

        # Mark phase completion
        for p in phases_map.values():
            if p['milestones']:
                p['is_completed'] = all(m.get('is_completed', False) for m in p['milestones'])
            else:
                p['is_completed'] = False

        return list(phases_map.values())


roadmap_service = RoadmapService()
