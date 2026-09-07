import json
import os
import sys
import secrets
from functools import wraps
from datetime import datetime, timezone, timedelta
from pathlib import Path
from flask import (
    Flask, 
    render_template, 
    request, 
    redirect, 
    url_for, 
    flash, 
    session, 
    jsonify,
    abort
)
from config import config_by_name, INSTANCE_DIR
from models import (
    db, 
    User, 
    CareerProfile, 
    UserProfile, 
    UserSkill, 
    TargetCareer,
    PasswordResetOTP,
    SkillGapAnalysis,
    SkillGapItem,
    PROFICIENCY_SCORE_MAP,
    Course,
    UserCourseRecommendation,
    CourseFeedback,
    UserRoadmap,
    RoadmapMilestone,
    AssessmentQuestion,
    AssessmentAttempt,
    AssessmentAnswer,
    CourseProgress,
    LearningActivity,
    SkillProgressHistory,
    Suggestion,
    CustomCareer,
    SkillDefinition,
    MarketRequirement
)
from services.career_service import career_service
from services.email_service import email_service
from services.skill_normalizer import normalize_skill, skills_match
from services.skill_gap_service import skill_gap_service
from services.recommendation_service import recommendation_service
from services.feedback_service import feedback_service
from services.suggestion_service import suggestion_service
from services.roadmap_service import roadmap_service
from services.assessment_service import assessment_service
from services.progress_service import progress_service
from services.admin_service import admin_service
from services.db_migrator import migrate_database_schema
from analytics.gap_charts import (
    generate_readiness_gauge,
    generate_skill_breakdown_donut,
    generate_level_comparison_chart,
    generate_priority_hours_chart
)
from analytics.market_trend_service import market_trend_service
from analytics.trend_charts import (
    generate_salary_benchmark_chart,
    generate_skills_growth_bar_chart,
    generate_industry_hiring_donut,
    generate_skill_roi_scatter_chart,
    generate_work_mode_chart,
    generate_tools_popularity_chart
)

def init_db(app):
    """Safely initializes and auto-migrates the SQLite database tables inside application context."""
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        migrate_database_schema(db, app)
        with app.app_context():
            recommendation_service.seed_courses_if_empty()
            assessment_service.seed_questions_if_empty()
    except Exception as e:
        print(f"[-] Database initialization warning: {e}", file=sys.stderr)

def create_app(config_name=None, test_config=None):
    """Application factory for CareerSkill AI."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
        
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name['default']))
    if test_config:
        app.config.update(test_config)

    # Initialize SQLAlchemy
    db.init_app(app)

    # Initialize database tables automatically
    init_db(app)

    # Context processor to make current_user available in all templates
    @app.context_processor
    def inject_user():
        current_user = None
        user_id = session.get('user_id')
        if user_id:
            try:
                current_user = db.session.get(User, user_id)
            except Exception:
                current_user = None
        return {'current_user': current_user}

    # ---------------------------------------------------------
    # Core Public Routes
    # ---------------------------------------------------------
    @app.route('/')
    def index():
        """Welcome / Landing page."""
        return render_template('index.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """User Login Route."""
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '').strip()

            if not email or not password:
                flash("Please enter both email and password.", "error")
                return render_template('login.html')

            user = User.query.filter_by(email=email).first()

            if user and user.check_password(password):
                if not user.is_active:
                    flash("Your account has been deactivated. Please contact administrator.", "error")
                    return render_template('login.html')

                session['user_id'] = user.id
                session['is_admin'] = bool(user.is_admin or user.role == 'admin')
                flash("Login successful.", "success")
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid email or password.", "error")
                return render_template('login.html')

        return render_template('login.html')

    @app.route('/logout')
    def logout():
        """Logs out the user and clears session."""
        session.clear()
        flash("You have been logged out.", "info")
        return redirect(url_for('login'))

    # ---------------------------------------------------------
    # Password Reset with Email OTP Flow
    # ---------------------------------------------------------
    @app.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        """Step 1: Request Email OTP for Password Reset."""
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()

            if not email:
                flash("Please enter your email address.", "error")
                return render_template('forgot_password.html')

            user = User.query.filter_by(email=email).first()

            if user:
                # Invalidate any prior unverified OTPs for this user
                PasswordResetOTP.query.filter_by(user_id=user.id, verified=False).delete()

                # Generate secure 6-digit OTP
                otp_code = str(secrets.randbelow(900000) + 100000)
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

                otp_record = PasswordResetOTP(
                    user_id=user.id,
                    expires_at=expires_at
                )
                otp_record.set_otp(otp_code)
                db.session.add(otp_record)
                db.session.commit()

                # Send OTP via Email service (or dev terminal fallback)
                email_service.send_password_reset_otp(email, otp_code)

            # Store email in session for OTP verification step
            session['reset_email'] = email

            # Generic message for security (prevents user enumeration)
            flash("If an account is associated with this email, a verification OTP has been sent.", "info")
            return redirect(url_for('verify_otp'))

        return render_template('forgot_password.html')

    @app.route('/verify-otp', methods=['GET', 'POST'])
    def verify_otp():
        """Step 2: Enter and Verify 6-digit Email OTP."""
        email = session.get('reset_email')
        if not email:
            flash("Please enter your email to request a verification OTP.", "warning")
            return redirect(url_for('forgot_password'))

        if request.method == 'POST':
            otp_entered = request.form.get('otp', '').strip()

            if not otp_entered or len(otp_entered) != 6 or not otp_entered.isdigit():
                flash("Please enter a valid 6-digit verification code.", "error")
                return render_template('verify_otp.html', email=email)

            user = User.query.filter_by(email=email).first()
            if not user:
                flash("Invalid or expired verification code. Please request a new OTP.", "error")
                return render_template('verify_otp.html', email=email)

            otp_record = PasswordResetOTP.query.filter_by(
                user_id=user.id, 
                verified=False
            ).order_by(PasswordResetOTP.id.desc()).first()

            if not otp_record:
                flash("Invalid or expired verification code. Please request a new OTP.", "error")
                return render_template('verify_otp.html', email=email)

            # Check attempt limit
            if otp_record.attempts >= 5:
                flash("Too many incorrect attempts. Please request a new OTP.", "error")
                return render_template('verify_otp.html', email=email)

            # Check expiry (10 minutes)
            if otp_record.is_expired():
                flash("This OTP has expired. Please request a new OTP.", "error")
                return render_template('verify_otp.html', email=email)

            # Validate OTP code hash
            if not otp_record.check_otp(otp_entered):
                otp_record.attempts += 1
                db.session.commit()
                
                if otp_record.attempts >= 5:
                    flash("Too many incorrect attempts. Please request a new OTP.", "error")
                else:
                    remaining = 5 - otp_record.attempts
                    flash(f"Invalid verification code. {remaining} attempt(s) remaining.", "error")
                return render_template('verify_otp.html', email=email)

            # OTP verified successfully
            otp_record.verified = True
            session['reset_user_id'] = user.id
            session.pop('reset_email', None)
            db.session.commit()

            flash("Email verified successfully. Please create your new password.", "success")
            return redirect(url_for('reset_password'))

        return render_template('verify_otp.html', email=email)

    @app.route('/resend-otp', methods=['POST'])
    def resend_otp():
        """Resends 6-digit OTP with 60-second cooldown enforcement."""
        email = session.get('reset_email')
        if not email:
            flash("Please request a password reset first.", "warning")
            return redirect(url_for('forgot_password'))

        user = User.query.filter_by(email=email).first()
        if user:
            # Check 60-second cooldown from most recent OTP
            latest_otp = PasswordResetOTP.query.filter_by(user_id=user.id).order_by(PasswordResetOTP.id.desc()).first()
            if latest_otp and latest_otp.created_at:
                now = datetime.now(timezone.utc)
                created = latest_otp.created_at
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                diff = (now - created).total_seconds()
                if diff < 60:
                    flash("Please wait 60 seconds before requesting another OTP.", "warning")
                    return redirect(url_for('verify_otp'))

            # Invalidate previous unverified OTPs
            PasswordResetOTP.query.filter_by(user_id=user.id, verified=False).delete()

            # Generate new 6-digit OTP
            otp_code = str(secrets.randbelow(900000) + 100000)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

            otp_record = PasswordResetOTP(
                user_id=user.id,
                expires_at=expires_at
            )
            otp_record.set_otp(otp_code)
            db.session.add(otp_record)
            db.session.commit()

            # Send OTP
            email_service.send_password_reset_otp(email, otp_code)

        flash("A new verification OTP has been sent.", "info")
        return redirect(url_for('verify_otp'))

    @app.route('/reset-password', methods=['GET', 'POST'])
    def reset_password():
        """Step 3: Create & Confirm New Password after OTP verification."""
        reset_user_id = session.get('reset_user_id')
        if not reset_user_id:
            flash("Unauthorized or session expired. Please verify your email first.", "error")
            return redirect(url_for('forgot_password'))

        user = db.session.get(User, reset_user_id)
        if not user:
            session.pop('reset_user_id', None)
            flash("User not found. Please try again.", "error")
            return redirect(url_for('forgot_password'))

        if request.method == 'POST':
            new_password = request.form.get('new_password', '').strip()
            confirm_password = request.form.get('confirm_password', '').strip()

            # Password requirements: at least 8 chars, at least 1 letter, at least 1 number
            if len(new_password) < 8:
                flash("Password must be at least 8 characters long.", "error")
                return render_template('reset_password.html')

            if not any(c.isalpha() for c in new_password):
                flash("Password must contain at least one letter.", "error")
                return render_template('reset_password.html')

            if not any(c.isdigit() for c in new_password):
                flash("Password must contain at least one number.", "error")
                return render_template('reset_password.html')

            if new_password != confirm_password:
                flash("Passwords do not match. Please verify and try again.", "error")
                return render_template('reset_password.html')

            # Update password hash securely
            user.set_password(new_password)

            # Invalidate any unused reset OTPs for this user
            PasswordResetOTP.query.filter_by(user_id=user.id).delete()

            db.session.commit()

            # Invalidate password reset session token
            session.pop('reset_user_id', None)

            flash("Your password has been reset successfully. Please log in with your new password.", "success")
            return redirect(url_for('login'))

        return render_template('reset_password.html')

    # ---------------------------------------------------------
    # Registration & Onboarding Routes
    # ---------------------------------------------------------
    @app.route('/get-started', methods=['GET', 'POST'])
    @app.route('/register', methods=['GET', 'POST'])
    def get_started():
        """Get Started / User Registration & Career Role Selection."""
        if request.method == 'POST':
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '').strip()
            target_role = request.form.get('target_role', '').strip()

            # Server-side validation
            if not target_role:
                flash("Please enter the career or job role you want to pursue.", "error")
                return render_template('get_started.html')

            if not email or not full_name:
                flash("Please provide your name and email address.", "error")
                return render_template('get_started.html')

            if not password:
                flash("Please enter a password.", "error")
                return render_template('get_started.html')

            # Check for duplicate email
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash("An account with this email already exists.", "error")
                return render_template('get_started.html')

            # Analyze role using CareerService (exact match or NLP similarity)
            analysis = career_service.analyze_career_role(target_role)
            norm_role = analysis.get('target_role', target_role) if analysis.get('success') else target_role

            # Create new user
            user = User(
                full_name=full_name,
                email=email,
                first_login=True
            )
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            # Store user ID in session
            session['user_id'] = user.id

            # Create CareerProfile
            profile = CareerProfile(
                user_id=user.id,
                target_role=norm_role,
                normalized_role=analysis.get('normalized_role', norm_role),
                is_custom_role=analysis.get('is_custom_role', False),
                confidence_score=analysis.get('confidence_score', 90),
                market_status=analysis.get('market_status', 'Verified Industry Benchmark'),
                explanation=analysis.get('explanation', '')
            )
            profile.set_skills(analysis.get('matched_skills', []))
            profile.set_related_roles(analysis.get('related_roles', []))
            db.session.add(profile)

            # Store TargetCareer record
            target_career = TargetCareer(
                user_id=user.id,
                career_name=norm_role,
                normalized_career_name=analysis.get('normalized_role', norm_role)
            )
            db.session.add(target_career)

            # Extract Current Status and status-specific information
            current_status = request.form.get('current_status', 'Student').strip()

            education = "Undergraduate / Bachelor's"
            degree = "BE / BTech"
            branch = "Computer Science"
            graduation_year = "2026"
            current_semester_year = None
            current_job_role = None
            previous_role = None
            years_of_experience = None
            break_duration = None
            existing_skills_raw = ""
            experience_level = "Beginner / Student"

            if current_status == 'Student':
                education = request.form.get('student_education', "Undergraduate / Bachelor's").strip() or "Undergraduate / Bachelor's"
                degree = request.form.get('student_degree', 'BE / BTech').strip() or "BE / BTech"
                branch = request.form.get('student_branch', 'Computer Science').strip() or "Computer Science"
                current_semester_year = request.form.get('student_semester_year', 'Final Year (Sem 7-8)').strip() or "Final Year (Sem 7-8)"
                experience_level = f"Student ({current_semester_year})"
                graduation_year = "2026"

            elif current_status == 'Fresher / Job Seeker':
                education = request.form.get('fresher_qualification', "Bachelor's (BE/BTech/BCA/BSc)").strip() or "Bachelor's (BE/BTech/BCA/BSc)"
                degree = education
                branch = "Engineering / IT"
                graduation_year = request.form.get('fresher_grad_year', '2025').strip() or "2025"
                existing_skills_raw = request.form.get('fresher_skills', '').strip()
                experience_level = f"Fresher ({graduation_year} Graduate)"

            elif current_status == 'Working Professional':
                current_job_role = request.form.get('prof_current_role', '').strip()
                years_of_experience = request.form.get('prof_experience_years', '1-2 years').strip() or "1-2 years"
                existing_skills_raw = request.form.get('prof_skills', '').strip()
                education = "Bachelor's / Professional Degree"
                degree = "Professional Background"
                branch = current_job_role or "IT / Tech"
                experience_level = f"Working Professional ({years_of_experience})"

            elif current_status == 'Career Switcher':
                previous_role = request.form.get('switcher_previous_role', '').strip()
                years_of_experience = request.form.get('switcher_experience_years', '1-3 years').strip() or "1-3 years"
                existing_skills_raw = request.form.get('switcher_skills', '').strip()
                education = "Graduate / Professional"
                degree = "Professional Background"
                branch = previous_role or "Industry Background"
                experience_level = f"Career Switcher ({years_of_experience} in {previous_role})" if previous_role else f"Career Switcher ({years_of_experience})"

            elif current_status == 'Returning After Career Break':
                previous_role = request.form.get('break_previous_role', '').strip()
                years_of_experience = request.form.get('break_experience_years', '2-4 years').strip() or "2-4 years"
                break_duration = request.form.get('break_duration', '6-12 months').strip() or "6-12 months"
                existing_skills_raw = request.form.get('break_skills', '').strip()
                education = "Graduate / Prior Professional"
                degree = "Professional Background"
                branch = previous_role or "Prior Tech Experience"
                experience_level = f"Returning ({break_duration} break, {years_of_experience} exp)"

            # Initialize UserProfile with complete captured details
            user_profile = UserProfile(
                user_id=user.id,
                education=education,
                degree=degree,
                branch=branch,
                graduation_year=graduation_year,
                current_status=current_status,
                current_semester_year=current_semester_year,
                current_job_role=current_job_role,
                previous_role=previous_role,
                years_of_experience=years_of_experience,
                break_duration=break_duration,
                existing_skills=existing_skills_raw,
                experience_level=experience_level,
                learning_hours_per_day="2 hours/day",
                learning_days_per_week=5,
                learning_hours_per_week=10.0,
                preferred_difficulty="Balanced"
            )
            db.session.add(user_profile)

            # Process existing skills and register them in user_skills table
            if existing_skills_raw:
                skills_list = [s.strip() for s in existing_skills_raw.replace(';', ',').split(',') if s.strip()]
                default_prof = 'Intermediate' if current_status in ['Working Professional', 'Career Switcher', 'Returning After Career Break'] else 'Beginner'
                for skill_name in skills_list:
                    existing_skill_record = UserSkill.query.filter_by(user_id=user.id, skill_name=skill_name).first()
                    if not existing_skill_record:
                        user_skill = UserSkill(
                            user_id=user.id,
                            skill_name=skill_name,
                            confidence_level=3
                        )
                        user_skill.set_proficiency(default_prof)
                        db.session.add(user_skill)

            db.session.commit()

            flash(f"Welcome to CareerSkill AI, {full_name}! Your account has been created successfully.", "success")
            # Redirect user to Dashboard as requested in user flow
            return redirect(url_for('dashboard'))

        return render_template('get_started.html')

    # ---------------------------------------------------------
    # Dashboard (Protected Route)
    # ---------------------------------------------------------
    @app.route('/dashboard')
    def dashboard():
        """User Dashboard displaying career status, skills, and progress."""
        user_id = session.get('user_id')
        if not user_id:
            flash("Please log in to access your dashboard.", "error")
            return redirect(url_for('login'))

        user = db.session.get(User, user_id)
        if not user:
            session.pop('user_id', None)
            flash("User profile not found. Please log in again.", "error")
            return redirect(url_for('login'))

        profile = user.user_profile
        user_skills = UserSkill.query.filter_by(user_id=user.id).all()
        
        tc = TargetCareer.query.filter_by(user_id=user.id).first()
        target_role = tc.career_name if tc else "Data Analyst"

        cp = CareerProfile.query.filter_by(user_id=user.id).order_by(CareerProfile.id.desc()).first()

        # Generate top 3 gap-based recommendations for the dashboard
        rec_data = recommendation_service.generate_recommendations(user=user, target_role=target_role)
        top_recommendations = rec_data.get('recommendations', [])[:3]
        total_recs_count = len(rec_data.get('recommendations', []))
        readiness_score = rec_data.get('readiness_score', 0)

        # Fetch active AI roadmap progress for dashboard
        roadmap_data = roadmap_service.get_or_generate_roadmap(user=user, target_role=target_role)

        # Fetch assessment statistics
        assessment_stats = assessment_service.get_user_assessment_stats(user.id if user else None)

        # Fetch comprehensive progress summary
        progress_summary = progress_service.get_overall_progress_summary(user.id if user else None, target_role=target_role)

        # Fetch user's submitted course feedbacks
        user_feedbacks = feedback_service.get_user_feedbacks(user.id)

        # Fetch user's platform suggestions & feedback (Module 10)
        user_suggestions = suggestion_service.get_user_suggestions(user.id)

        # Determine if this is the user's first dashboard visit after registration
        is_first_login = bool(getattr(user, 'first_login', False))
        if is_first_login:
            user.first_login = False
            db.session.commit()

        return render_template(
            'dashboard.html',
            user=user,
            is_first_login=is_first_login,
            profile=profile,
            user_skills=user_skills,
            target_role=target_role,
            career_profile=cp,
            top_recommendations=top_recommendations,
            total_recs_count=total_recs_count,
            readiness_score=readiness_score,
            roadmap=roadmap_data,
            assessment_stats=assessment_stats,
            progress_summary=progress_summary,
            user_feedbacks=user_feedbacks,
            user_suggestions=user_suggestions
        )

    # ---------------------------------------------------------
    # Onboarding Flow (Step 3)
    # ---------------------------------------------------------
    @app.route('/onboarding', methods=['GET', 'POST'])
    def onboarding():
        """Multi-step Career Profile & Skills Onboarding."""
        user_id = session.get('user_id') or request.args.get('user_id', type=int) or request.form.get('user_id', type=int)
        user = db.session.get(User, user_id) if user_id else None

        if request.method == 'POST':
            target_role = request.form.get('target_role', '').strip()
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip().lower()
            
            # Step 1: Education
            highest_education = request.form.get('highest_education', '').strip()
            degree = request.form.get('degree', '').strip()
            branch = request.form.get('branch', '').strip()
            graduation_year = request.form.get('graduation_year', '').strip()
            current_status = request.form.get('current_status', 'Student').strip()

            # Step 2: Experience
            experience_level = request.form.get('experience_level', 'No experience').strip()
            has_projects = request.form.get('has_projects_radio', 'no') == 'yes'
            project_experience = request.form.get('project_experience', '').strip()

            # Step 4: Learning Schedule
            learning_hours_per_day = request.form.get('learning_hours_per_day', '2 hours/day').strip()
            learning_days_per_week = request.form.get('learning_days_per_week', 5, type=int)
            learning_hours_per_week = request.form.get('learning_hours_per_week', 10.0, type=float)

            # Step 5 & 6: Preferences & Goals
            learning_prefs_raw = request.form.get('learning_prefs_json', '[]')
            preferred_difficulty = request.form.get('preferred_difficulty', 'Balanced').strip()
            career_goals_raw = request.form.get('career_goals_json', '[]')

            # Step 3: Skills Data
            skills_data_raw = request.form.get('skills_data_json', '[]')

            # Parse JSON data safely
            try:
                skills_list = json.loads(skills_data_raw)
            except Exception:
                skills_list = []

            try:
                learning_prefs = json.loads(learning_prefs_raw)
            except Exception:
                learning_prefs = []

            try:
                career_goals = json.loads(career_goals_raw)
            except Exception:
                career_goals = []

            # Validation
            if not target_role:
                flash("Target Career is required.", "error")
                return redirect(url_for('onboarding', user_id=user.id if user else None, role=target_role))

            if not highest_education or not degree or not branch:
                flash("Please fill in your educational background.", "error")
                return redirect(url_for('onboarding', user_id=user.id if user else None, role=target_role))

            if not skills_list:
                flash("Please add at least one current skill before proceeding.", "error")
                return redirect(url_for('onboarding', user_id=user.id if user else None, role=target_role))

            # Ensure user exists or create if new
            if not user:
                if email:
                    user = User.query.filter_by(email=email).first()
                if not user:
                    user = User(
                        full_name=full_name or 'Candidate',
                        email=email or f"user_{os.urandom(4).hex()}@example.com",
                        first_login=True
                    )
                    db.session.add(user)
                    db.session.commit()
                session['user_id'] = user.id

            # Update or create UserProfile
            user_profile = UserProfile.query.filter_by(user_id=user.id).first()
            if not user_profile:
                user_profile = UserProfile(user_id=user.id)
                db.session.add(user_profile)

            user_profile.education = highest_education
            user_profile.degree = degree
            user_profile.branch = branch
            user_profile.graduation_year = graduation_year
            user_profile.current_status = current_status
            user_profile.experience_level = experience_level
            user_profile.has_project_experience = has_projects
            user_profile.project_experience = project_experience
            user_profile.learning_hours_per_day = learning_hours_per_day
            user_profile.learning_days_per_week = learning_days_per_week
            user_profile.learning_hours_per_week = learning_hours_per_week
            user_profile.preferred_difficulty = preferred_difficulty
            user_profile.set_learning_preferences(learning_prefs)
            user_profile.set_career_goals(career_goals)

            # Update TargetCareer
            target_career = TargetCareer.query.filter_by(user_id=user.id).first()
            norm_title = career_service.normalize_role(target_role)[1]
            if not target_career:
                target_career = TargetCareer(
                    user_id=user.id,
                    career_name=target_role,
                    normalized_career_name=norm_title
                )
                db.session.add(target_career)
            else:
                target_career.career_name = target_role
                target_career.normalized_career_name = norm_title

            # Save UserSkills (Clear old skills and repopulate)
            UserSkill.query.filter_by(user_id=user.id).delete()
            for s in skills_list:
                s_name = s.get('name', '').strip()
                if not s_name:
                    continue
                prof_level = s.get('proficiency', 'Beginner')
                conf_level = int(s.get('confidence', 3))
                
                user_skill = UserSkill(
                    user_id=user.id,
                    skill_name=s_name,
                    confidence_level=conf_level
                )
                user_skill.set_proficiency(prof_level)
                db.session.add(user_skill)

            db.session.commit()

            flash("Career profile configured successfully!", "success")
            return redirect(url_for('career_analysis', user_id=user.id))

        # GET request: load initial context
        target_role = request.args.get('role', '')
        if not target_role and user:
            tc = TargetCareer.query.filter_by(user_id=user.id).first()
            if tc:
                target_role = tc.career_name
            else:
                cp = CareerProfile.query.filter_by(user_id=user.id).order_by(CareerProfile.id.desc()).first()
                if cp:
                    target_role = cp.target_role

        if not target_role:
            target_role = "Data Analyst"

        return render_template('onboarding.html', user=user, target_role=target_role)

    # ---------------------------------------------------------
    # Career Gap Analysis Route
    # ---------------------------------------------------------
    @app.route('/career-analysis')
    @app.route('/career-analysis/<int:user_id>')
    def career_analysis(user_id=None):
        """Displays full data-driven Career Gap Analysis for the authenticated user."""
        user = None
        if session.get('user_id'):
            user = db.session.get(User, session.get('user_id'))
        elif user_id:
            user = db.session.get(User, user_id)

        if not user and not app.config.get('TESTING'):
            flash("Please log in or register to access personalized Career Analysis.", "error")
            return redirect(url_for('login'))

        if not user and app.config.get('TESTING'):
            user = User.query.order_by(User.id.desc()).first()

        profile = user.user_profile if user else None
        
        # Determine target role
        target_role = request.args.get('role')
        if target_role and user:
            target_role = target_role.strip()
            tc = TargetCareer.query.filter_by(user_id=user.id).first()
            if tc:
                tc.career_name = target_role
                tc.normalized_career_name = target_role
            else:
                tc = TargetCareer(user_id=user.id, career_name=target_role, normalized_career_name=target_role)
                db.session.add(tc)
            db.session.commit()
        elif not target_role and user:
            tc = TargetCareer.query.filter_by(user_id=user.id).first()
            if tc:
                target_role = tc.career_name
            elif user.profiles:
                target_role = user.profiles[-1].target_role
        
        if not target_role:
            target_role = "Data Analyst"

        # Check for saved topic evaluations
        topic_evaluations = {}
        if user:
            saved_analysis = SkillGapAnalysis.query.filter_by(user_id=user.id).order_by(SkillGapAnalysis.id.desc()).first()
            if saved_analysis and saved_analysis.target_role.lower() == target_role.lower():
                topic_evaluations = saved_analysis.get_topic_evaluations()

        # Run complete Skill Gap Engine
        analysis = skill_gap_service.analyze_skill_gap(
            user=user, 
            target_role=target_role,
            custom_topic_evaluations=topic_evaluations
        )

        # Save snapshot to SQLite
        if user:
            skill_gap_service.save_analysis_to_db(user.id, analysis)

        # Generate Visual Analytics Charts
        gauge_json = generate_readiness_gauge(analysis['readiness_score'])
        donut_json = generate_skill_breakdown_donut(
            analysis['strong_count'], 
            analysis['partial_count'], 
            analysis['missing_count']
        )
        bar_json = generate_level_comparison_chart(analysis['gap_items'])
        hours_json = generate_priority_hours_chart(analysis['gap_items'])

        return render_template(
            'career_analysis.html', 
            user=user, 
            profile=profile, 
            analysis=analysis, 
            target_role=analysis['target_role'],
            gauge_json=gauge_json,
            donut_json=donut_json,
            bar_json=bar_json,
            hours_json=hours_json
        )

    @app.route('/career-analysis/update-skills', methods=['POST'])
    def update_career_skills():
        """Updates user's current skill proficiency levels from Career Analysis page and recalculates gap analysis."""
        user_id = session.get('user_id')
        if not user_id and not app.config.get('TESTING'):
            flash("Please log in to update your skills.", "error")
            return redirect(url_for('login'))

        user = db.session.get(User, user_id) if user_id else User.query.order_by(User.id.desc()).first()
        target_role = request.form.get('target_role', 'Data Analyst').strip()
        count = request.form.get('total_skills_count', 0, type=int)

        if user and count > 0:
            for i in range(count):
                s_name = request.form.get(f'skill_name_{i}', '').strip()
                s_level = request.form.get(f'skill_level_{i}', "I don't know this skill").strip()
                if not s_name:
                    continue

                user_skill = UserSkill.query.filter_by(user_id=user.id, skill_name=s_name).first()
                if not user_skill:
                    norm = normalize_skill(s_name)
                    for us in UserSkill.query.filter_by(user_id=user.id).all():
                        if normalize_skill(us.skill_name) == norm:
                            user_skill = us
                            break

                if not user_skill:
                    user_skill = UserSkill(
                        user_id=user.id,
                        skill_name=s_name,
                        confidence_level=3
                    )
                    db.session.add(user_skill)

                user_skill.set_proficiency(s_level)

            db.session.commit()
            flash("Your skills have been updated! Skill gap analysis has been recalculated.", "success")

        return redirect(url_for('career_analysis', role=target_role))

    # ---------------------------------------------------------
    # AI Skill Assessment & Progress Validation Routes (Module 7)
    # ---------------------------------------------------------
    @app.route('/assessments')
    @app.route('/assessment-hub')
    @app.route('/assessment')
    def assessment_hub():
        """
        Skill Assessment & Progress Validation Hub.
        Lists target career skills, current validation status, and recent assessment attempt history.
        """
        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None
        
        tc = TargetCareer.query.filter_by(user_id=user.id).first() if user else None
        target_role = tc.career_name if tc else "Data Analyst"

        skills = assessment_service.get_available_assessment_skills(user=user, target_role=target_role)
        stats = assessment_service.get_user_assessment_stats(user.id if user else None)

        return render_template(
            'assessment_overview.html',
            user=user,
            target_role=target_role,
            available_skills=skills,
            stats=stats
        )

    @app.route('/assessment/start/<skill_name>')
    def start_assessment_view(skill_name):
        """Interactive test taking interface for a specific technical skill."""
        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None

        tc = TargetCareer.query.filter_by(user_id=user.id).first() if user else None
        target_role = tc.career_name if tc else "Data Analyst"

        assessment_payload = assessment_service.generate_assessment(
            user=user,
            skill_name=skill_name,
            target_role=target_role,
            num_questions=8
        )

        return render_template(
            'assessment_take.html',
            user=user,
            assessment=assessment_payload
        )

    @app.route('/assessment/submit', methods=['POST'])
    def submit_assessment_action():
        """Handles assessment submission, computes score & diagnostics, and triggers cascading updates."""
        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None

        skill_name = request.form.get('skill_name', 'SQL')
        target_role = request.form.get('target_role', 'Data Analyst')

        # Collect answered questions from form
        answers_dict = {}
        for key, val in request.form.items():
            if key.startswith('q_'):
                q_id_str = key[2:]
                answers_dict[q_id_str] = val

        eval_result = assessment_service.evaluate_assessment(
            user=user,
            skill_name=skill_name,
            answers_dict=answers_dict,
            target_role=target_role
        )

        flash(f"{skill_name} assessment completed! Score: {eval_result['score']}%", "success")
        return redirect(url_for('assessment_result_view', attempt_id=eval_result['attempt_id']))

    @app.route('/assessment/result/<int:attempt_id>')
    def assessment_result_view(attempt_id):
        """Displays detailed assessment result report and three-way benchmark calibration."""
        attempt = db.session.get(AssessmentAttempt, attempt_id)
        if not attempt:
            flash("Assessment record not found.", "error")
            return redirect(url_for('assessment_hub'))

        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None

        # Build evaluated answers view
        answers_list = []
        for ans in attempt.answers:
            answers_list.append({
                'question_id': ans.question_id,
                'topic': ans.topic,
                'user_answer': ans.user_answer,
                'correct_answer': ans.correct_answer,
                'is_correct': ans.is_correct,
                'question_text': ans.question.question_text if ans.question else f"Question #{ans.question_id}",
                'explanation': ans.question.explanation if ans.question else None,
                'difficulty': ans.question.difficulty if ans.question else 'Intermediate'
            })

        result_dict = attempt.to_dict()
        result_dict['evaluated_answers'] = answers_list

        return render_template(
            'assessment_result.html',
            user=user,
            result=result_dict
        )

    @app.route('/api/assessment/questions', methods=['GET'])
    def api_assessment_questions():
        """REST endpoint returning questions for a skill."""
        skill_name = request.args.get('skill', 'SQL')
        user_id = request.args.get('user_id', type=int) or session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None
        role = request.args.get('role', 'Data Analyst')

        payload = assessment_service.generate_assessment(user=user, skill_name=skill_name, target_role=role)
        return jsonify(payload)

    @app.route('/api/assessment/submit', methods=['POST'])
    def api_assessment_submit():
        """AJAX endpoint for submitting assessment answers."""
        data = request.get_json(silent=True) or request.form
        skill_name = data.get('skill_name', 'SQL')
        target_role = data.get('target_role', 'Data Analyst')
        answers = data.get('answers', {})
        user_id = data.get('user_id') or session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None

        eval_result = assessment_service.evaluate_assessment(
            user=user,
            skill_name=skill_name,
            answers_dict=answers,
            target_role=target_role
        )
        return jsonify({'success': True, 'result': eval_result})

    @app.route('/api/assessment/stats', methods=['GET'])
    def api_assessment_stats():
        """REST endpoint for user assessment statistics."""
        user_id = request.args.get('user_id', type=int) or session.get('user_id')
        stats = assessment_service.get_user_assessment_stats(user_id)
        return jsonify(stats)

    # ---------------------------------------------------------
    # Learning Progress Tracking Routes (Module 8)
    # ---------------------------------------------------------
    @app.route('/progress-history')
    @app.route('/learning-progress')
    @app.route('/progress')
    def progress_history():
        """
        Learning Progress Tracking & Activity History Dashboard.
        Displays overall progress %, career readiness %, learning hours tracker,
        skill growth matrix over time, and chronological audit trail.
        """
        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None

        tc = TargetCareer.query.filter_by(user_id=user.id).first() if user else None
        target_role = tc.career_name if tc else "Data Analyst"

        summary = progress_service.get_overall_progress_summary(user.id if user else None, target_role=target_role)
        activities = progress_service.get_activity_history(user.id if user else None, limit=50)

        return render_template(
            'progress_history.html',
            user=user,
            target_role=target_role,
            summary=summary,
            activities=activities
        )

    @app.route('/api/progress/course/update', methods=['POST'])
    def api_update_course_progress():
        """AJAX endpoint to update progress percentage, status, and completed hours for a course."""
        data = request.get_json(silent=True) or request.form
        user_id = data.get('user_id') or session.get('user_id')
        course_id = data.get('course_id')
        status = data.get('status')
        progress_percentage = data.get('progress_percentage')
        hours_completed = data.get('hours_completed')

        if not user_id or not course_id:
            return jsonify({'success': False, 'error': 'Missing user_id or course_id'}), 400

        try:
            c_id = int(course_id)
            u_id = int(user_id)
            pct = int(progress_percentage) if progress_percentage is not None else None
            hrs = float(hours_completed) if hours_completed is not None else None
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid number format'}), 400

        result = progress_service.update_course_progress(
            user_id=u_id,
            course_id=c_id,
            status=status,
            progress_percentage=pct,
            hours_completed=hrs
        )
        return jsonify(result)

    @app.route('/api/progress/log-session', methods=['POST'])
    def api_log_session():
        """Endpoint to manually log a study session or technical practice hours."""
        data = request.get_json(silent=True) or request.form
        user_id = data.get('user_id') or session.get('user_id')
        skill = data.get('skill', 'General')
        title = data.get('title', 'Study Session')
        hours = data.get('hours', 1.0)
        notes = data.get('notes', '')

        if not user_id:
            return jsonify({'success': False, 'error': 'User not authenticated'}), 401

        try:
            u_id = int(user_id)
            h = float(hours)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid parameters'}), 400

        result = progress_service.log_learning_session(
            user_id=u_id,
            skill=skill,
            title=title,
            hours=h,
            notes=notes
        )
        return jsonify(result)

    @app.route('/api/progress/summary', methods=['GET'])
    def api_progress_summary():
        """JSON endpoint returning consolidated 9 progress KPIs."""
        user_id = request.args.get('user_id', type=int) or session.get('user_id')
        role = request.args.get('role')
        summary = progress_service.get_overall_progress_summary(user_id, target_role=role)
        return jsonify(summary)

    @app.route('/api/progress/history', methods=['GET'])
    def api_progress_history():
        """JSON endpoint returning chronological learning activity timeline."""
        user_id = request.args.get('user_id', type=int) or session.get('user_id')
        limit = request.args.get('limit', 50, type=int)
        activities = progress_service.get_activity_history(user_id, limit=limit)
        return jsonify({'activities': activities})

    # ---------------------------------------------------------
    # Course Recommendation Routes (Step 4)
    # ---------------------------------------------------------
    @app.route('/course-recommendations')
    def course_recommendations():
        """
        Personalized Gap-Based Course Recommendations Page.
        Matches user's missing/partial skills, topics, and schedule against curated learning resources.
        """
        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None

        # Determine target role
        target_role = request.args.get('role')
        if not target_role and user:
            tc = TargetCareer.query.filter_by(user_id=user.id).first()
            if tc:
                target_role = tc.career_name
            elif user.profiles:
                target_role = user.profiles[-1].target_role
        if not target_role:
            target_role = "Data Analyst"

        # Generate gap-based recommendations
        rec_data = recommendation_service.generate_recommendations(user=user, target_role=target_role)

        return render_template(
            'course_recommendations.html',
            user=user,
            data=rec_data
        )

    @app.route('/refresh-recommendations', methods=['POST'])
    def refresh_recommendations():
        """Recalculates recommendations with latest user skills and skill gaps."""
        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None
        
        tc = TargetCareer.query.filter_by(user_id=user.id).first() if user else None
        target_role = tc.career_name if tc else "Data Analyst"

        recommendation_service.generate_recommendations(user=user, target_role=target_role, force_refresh=True)
        flash("Learning recommendations refreshed with your latest skill profile!", "success")
        return redirect(url_for('course_recommendations'))

    @app.route('/course/<int:course_id>')
    def course_detail(course_id):
        """Displays rich syllabus, topic alignment, and why-recommended breakdown for a course."""
        course = db.session.get(Course, course_id)
        if not course:
            return render_template('404.html'), 404

        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None

        # Target role
        tc = TargetCareer.query.filter_by(user_id=user.id).first() if user else None
        target_role = tc.career_name if tc else "Data Analyst"

        # Skill gap context for this course
        gap_analysis = skill_gap_service.analyze_skill_gap(user=user, target_role=target_role)
        gap_items = gap_analysis.get('gap_items', [])
        
        canonical_course_skill, _ = normalize_skill(course.skill)
        matched_gap = None
        for g in gap_items:
            g_name = g.get('normalized_skill_name') or g.get('skill_name', '')
            if skills_match(g_name, canonical_course_skill):
                matched_gap = g
                break

        user_level = matched_gap['user_level'] if matched_gap else 'No Knowledge'
        required_level = matched_gap['required_level'] if matched_gap else 'Intermediate'

        weekly_hours = 10.0
        if user and user.user_profile and user.user_profile.learning_hours_per_week:
            weekly_hours = float(user.user_profile.learning_hours_per_week)

        import math
        estimated_weeks = max(1, math.ceil(course.duration_hours / max(1.0, weekly_hours)))

        score_data = recommendation_service._calculate_course_recommendation_score(
            course=course,
            gap_item=matched_gap,
            user_preferences=user.user_profile.get_learning_preferences() if (user and user.user_profile) else [],
            weekly_hours=weekly_hours,
            preferred_difficulty='Balanced',
            target_role=target_role
        )

        return render_template(
            'course_detail.html',
            course=course,
            user=user,
            target_role=target_role,
            user_level=user_level,
            required_level=required_level,
            weekly_hours=weekly_hours,
            estimated_weeks=estimated_weeks,
            recommendation_score=score_data['score'],
            why_recommended=score_data['why_recommended']
        )

    @app.route('/api/recommendations/status', methods=['POST'])
    def api_recommendation_status():
        """Updates user course recommendation status (In Progress, Completed, Saved, Skipped)."""
        data = request.get_json(silent=True) or request.form
        user_id = data.get('user_id') or session.get('user_id')
        raw_course_id = data.get('course_id')
        try:
            course_id = int(raw_course_id) if raw_course_id is not None else None
        except (ValueError, TypeError):
            course_id = None
        status = data.get('status', 'In Progress')

        if not user_id:
            # If guest user, return success without saving
            return jsonify({'success': True, 'guest': True, 'status': status})

        result = recommendation_service.update_recommendation_status(
            user_id=user_id,
            course_id=course_id,
            status=status
        )

        # Synchronize course progress in ProgressService
        if course_id:
            try:
                u_id = int(user_id)
                c_id = int(course_id)
                pct = 100 if status == 'Completed' else (25 if status == 'In Progress' else 0)
                progress_service.update_course_progress(
                    user_id=u_id,
                    course_id=c_id,
                    status=status,
                    progress_percentage=pct if status == 'Completed' else None
                )
            except Exception as e:
                print(f"[-] Progress sync warning: {e}")

        return jsonify(result)

    @app.route('/api/course-recommendations', methods=['GET'])
    def api_course_recommendations():
        """JSON endpoint for course recommendations."""
        user_id = request.args.get('user_id', type=int) or session.get('user_id')
        role = request.args.get('role')
        user = db.session.get(User, user_id) if user_id else None
        rec_data = recommendation_service.generate_recommendations(user=user, target_role=role)
        return jsonify(rec_data)

    # ---------------------------------------------------------
    # Course Completion & User Feedback Routes (Module 9)
    # ---------------------------------------------------------
    @app.route('/course/<int:course_id>/complete', methods=['POST', 'GET'])
    def complete_course_action(course_id):
        """
        Marks course completed (100%), synchronizes roadmap and learning progress,
        and directs the user to submit course feedback.
        """
        user_id = session.get('user_id')
        if not user_id:
            flash("Please log in to complete courses and submit feedback.", "error")
            return redirect(url_for('login'))

        user = db.session.get(User, user_id)
        course = db.session.get(Course, course_id)
        if not course:
            return render_template('404.html'), 404

        # Update course progress to 100% and status to Completed
        progress_service.update_course_progress(
            user_id=user.id,
            course_id=course.id,
            status='Completed',
            progress_percentage=100
        )
        flash(f"Congratulations! You marked '{course.title}' as completed.", "success")
        return redirect(url_for('course_feedback_view', course_id=course.id))

    @app.route('/course/<int:course_id>/feedback', methods=['GET', 'POST'])
    def course_feedback_view(course_id):
        """
        Course Feedback & Rating Page.
        Displays feedback form (1-5 stars, usefulness, skill impact, liked/improvements, recommend).
        Pre-fills existing feedback for editing if already submitted.
        """
        user_id = session.get('user_id')
        if not user_id:
            flash("Please log in to submit course feedback.", "error")
            return redirect(url_for('login'))

        user = db.session.get(User, user_id)
        course = db.session.get(Course, course_id)
        if not course:
            return render_template('404.html'), 404

        if request.method == 'POST':
            rating = request.form.get('rating', 5, type=int)
            usefulness = request.form.get('usefulness', 'Very Useful').strip()
            improved_skill = request.form.get('improved_skill', 'Yes').strip()
            liked_aspects = request.form.get('liked_aspects', '').strip()
            improvement_suggestions = request.form.get('improvement_suggestions', '').strip()
            would_recommend = request.form.get('would_recommend', 'Yes').strip()

            result = feedback_service.submit_or_update_feedback(
                user_id=user.id,
                course_id=course.id,
                rating=rating,
                usefulness=usefulness,
                improved_skill=improved_skill,
                liked_aspects=liked_aspects,
                improvement_suggestions=improvement_suggestions,
                would_recommend=would_recommend
            )

            if result.get('success'):
                flash(result.get('message', "Feedback submitted successfully!"), "success")
                return redirect(url_for('dashboard'))
            else:
                flash(result.get('error', "Could not submit feedback."), "error")

        existing_feedback = feedback_service.get_user_feedback(user.id, course.id)
        return render_template(
            'course_feedback.html',
            user=user,
            course=course,
            existing_feedback=existing_feedback
        )

    @app.route('/api/course/feedback', methods=['POST'])
    def api_submit_course_feedback():
        """AJAX endpoint to submit or update course feedback."""
        data = request.get_json(silent=True) or request.form
        user_id = data.get('user_id') or session.get('user_id')
        course_id = data.get('course_id')

        if not user_id or not course_id:
            return jsonify({'success': False, 'error': 'Missing user_id or course_id'}), 400

        try:
            u_id = int(user_id)
            c_id = int(course_id)
            rating = int(data.get('rating', 5))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid parameter format'}), 400

        usefulness = data.get('usefulness', 'Very Useful')
        improved_skill = data.get('improved_skill', 'Yes')
        liked_aspects = data.get('liked_aspects', '')
        improvement_suggestions = data.get('improvement_suggestions', '')
        would_recommend = data.get('would_recommend', 'Yes')

        result = feedback_service.submit_or_update_feedback(
            user_id=u_id,
            course_id=c_id,
            rating=rating,
            usefulness=usefulness,
            improved_skill=improved_skill,
            liked_aspects=liked_aspects,
            improvement_suggestions=improvement_suggestions,
            would_recommend=would_recommend
        )
        return jsonify(result)

    @app.route('/api/course/<int:course_id>/feedback', methods=['GET'])
    def api_get_course_feedback(course_id):
        """AJAX endpoint to fetch user's feedback for a course."""
        user_id = request.args.get('user_id', type=int) or session.get('user_id')
        if not user_id:
            return jsonify({'success': False, 'error': 'User not authenticated'}), 401
        fb = feedback_service.get_user_feedback(user_id, course_id)
        return jsonify({'success': True, 'feedback': fb})

    # ---------------------------------------------------------
    # User Suggestions & Improvement System (Module 10)
    # ---------------------------------------------------------
    @app.route('/suggestions', methods=['GET', 'POST'])
    def suggestions_view():
        """
        User Suggestions & Feedback Hub.
        Allows learners to submit missing careers, skills, courses, incorrect information,
        and platform enhancement requests, and view previous submissions with admin responses.
        """
        user_id = session.get('user_id')
        if not user_id:
            flash("Please log in to submit suggestions and platform feedback.", "error")
            return redirect(url_for('login'))

        user = db.session.get(User, user_id)
        if not user:
            return redirect(url_for('login'))

        if request.method == 'POST':
            category = request.form.get('category', '').strip()
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            career = request.form.get('career', '').strip()
            skill = request.form.get('skill', '').strip()
            course = request.form.get('course', '').strip()

            result = suggestion_service.submit_suggestion(
                user_id=user.id,
                category=category,
                title=title,
                description=description,
                career=career,
                skill=skill,
                course=course
            )

            if result.get('success'):
                flash(result.get('message', "Suggestion submitted successfully!"), "success")
                return redirect(url_for('suggestions_view'))
            else:
                flash(result.get('error', "Could not submit suggestion."), "error")

        user_suggestions = suggestion_service.get_user_suggestions(user.id)
        categories = suggestion_service.CATEGORIES

        return render_template(
            'suggestions.html',
            user=user,
            suggestions=user_suggestions,
            categories=categories
        )

    @app.route('/suggestions/<int:suggestion_id>/edit', methods=['POST'])
    def edit_suggestion_action(suggestion_id):
        """Allows user to edit their suggestion only when status is 'Submitted'."""
        user_id = session.get('user_id')
        if not user_id:
            flash("Please log in to edit your suggestion.", "error")
            return redirect(url_for('login'))

        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', '').strip()
        career = request.form.get('career', '').strip()
        skill = request.form.get('skill', '').strip()
        course = request.form.get('course', '').strip()

        result = suggestion_service.update_user_suggestion(
            suggestion_id=suggestion_id,
            user_id=user_id,
            title=title,
            description=description,
            category=category,
            career=career,
            skill=skill,
            course=course
        )

        if result.get('success'):
            flash(result.get('message', "Suggestion updated successfully!"), "success")
        else:
            flash(result.get('error', "Could not update suggestion."), "error")

        return redirect(url_for('suggestions_view'))

    @app.route('/suggestions/<int:suggestion_id>/delete', methods=['POST'])
    def delete_suggestion_action(suggestion_id):
        """Allows user to delete their suggestion only when status is 'Submitted'."""
        user_id = session.get('user_id')
        if not user_id:
            flash("Please log in to delete your suggestion.", "error")
            return redirect(url_for('login'))

        result = suggestion_service.delete_user_suggestion(
            suggestion_id=suggestion_id,
            user_id=user_id
        )

        if result.get('success'):
            flash(result.get('message', "Suggestion deleted successfully."), "success")
        else:
            flash(result.get('error', "Could not delete suggestion."), "error")

        return redirect(url_for('suggestions_view'))

    @app.route('/api/suggestions', methods=['GET', 'POST'])
    def api_user_suggestions():
        """AJAX endpoint for fetching or submitting user suggestions."""
        user_id = session.get('user_id')
        if request.method == 'POST':
            data = request.get_json(silent=True) or request.form
            u_id = data.get('user_id') or user_id
            if not u_id:
                return jsonify({'success': False, 'error': 'User not authenticated'}), 401

            result = suggestion_service.submit_suggestion(
                user_id=int(u_id),
                category=data.get('category', 'General Suggestion'),
                title=data.get('title', ''),
                description=data.get('description', ''),
                career=data.get('career'),
                skill=data.get('skill'),
                course=data.get('course')
            )
            return jsonify(result)

        if not user_id:
            return jsonify({'success': False, 'error': 'User not authenticated'}), 401

        suggestions = suggestion_service.get_user_suggestions(user_id)
        return jsonify({'success': True, 'suggestions': suggestions})

    # ---------------------------------------------------------
    # Admin Authorization & Security Decorator (Module 11)
    # ---------------------------------------------------------
    def admin_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_id = session.get('user_id')
            if not user_id:
                flash("Please log in with administrator credentials.", "error")
                return redirect(url_for('login'))
            user = db.session.get(User, user_id)
            if not user or not (user.is_admin or user.role == 'admin' or session.get('is_admin')):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function

    @app.errorhandler(403)
    def forbidden_access_error(error):
        """Custom error handler for unauthorized admin access attempts."""
        return render_template('403.html', error_title="403 - Access Denied", error_message="Access restricted. Administrator privileges are required to view this area."), 403

    # ---------------------------------------------------------
    # 1. Admin Dashboard Overview
    # ---------------------------------------------------------
    @app.route('/admin')
    @app.route('/admin/dashboard')
    @app.route('/admin/dashboard', endpoint='admin_dashboard')
    @admin_required
    def admin_dashboard_view():
        """
        Executive Admin Dashboard.
        Displays summary cards, real database metrics, visual trends, and live activity streams.
        """
        user_id = session.get('user_id')
        user = db.session.get(User, user_id)
        summary = admin_service.get_dashboard_summary()

        return render_template(
            'admin/dashboard.html',
            current_user=user,
            summary=summary,
            active_page='dashboard'
        )

    # ---------------------------------------------------------
    # 2. User Management
    # ---------------------------------------------------------
    @app.route('/admin/users')
    @admin_required
    def admin_users_view():
        """User directory with search, filtering, and account status management."""
        user_id = session.get('user_id')
        user = db.session.get(User, user_id)

        search_query = request.args.get('q', '').strip()
        career_filter = request.args.get('career', '').strip()
        status_filter = request.args.get('status', '').strip()

        users_list = admin_service.get_users_list(
            search_query=search_query if search_query else None,
            career_filter=career_filter if career_filter else None,
            status_filter=status_filter if status_filter else None
        )

        return render_template(
            'admin/users.html',
            current_user=user,
            users=users_list,
            search_query=search_query,
            career_filter=career_filter,
            status_filter=status_filter,
            active_page='users'
        )

    @app.route('/admin/users/<int:user_id>')
    @admin_required
    def admin_user_detail_view(user_id):
        """360-degree user inspection (excluding password hashes)."""
        current_admin = db.session.get(User, session.get('user_id'))
        user_detail = admin_service.get_user_details(user_id)

        if not user_detail:
            flash("User not found.", "error")
            return redirect(url_for('admin_users_view'))

        return render_template(
            'admin/user_detail.html',
            current_user=current_admin,
            target_user=user_detail,
            active_page='users'
        )

    @app.route('/admin/users/<int:user_id>/toggle-status', methods=['POST'])
    @admin_required
    def admin_user_toggle_status(user_id):
        """Activates or deactivates a user account."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'
        result = admin_service.toggle_user_status(user_id, admin_user_id=session.get('user_id'), admin_name=admin_name)
        if result.get('success'):
            flash(result.get('message', "User account status updated."), "success")
        else:
            flash(result.get('error', "Could not update user status."), "error")
        return redirect(request.referrer or url_for('admin_users_view'))

    @app.route('/admin/users/<int:user_id>/toggle-role', methods=['POST'])
    @admin_required
    def admin_user_toggle_role(user_id):
        """Promotes or demotes user administrator role."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'
        result = admin_service.toggle_user_role(user_id, admin_user_id=session.get('user_id'), admin_name=admin_name)
        if result.get('success'):
            flash(result.get('message', "User role updated."), "success")
        else:
            flash(result.get('error', "Could not update user role."), "error")
        return redirect(request.referrer or url_for('admin_users_view'))

    @app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
    @admin_required
    def admin_user_delete(user_id):
        """Deletes a user account safely."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'
        result = admin_service.delete_user(user_id, admin_user_id=session.get('user_id'), admin_name=admin_name)
        if result.get('success'):
            flash(result.get('message', "User account deleted successfully."), "success")
        else:
            flash(result.get('error', "Could not delete user account."), "error")
        return redirect(url_for('admin_users_view'))

    @app.route('/admin/users/create-admin', methods=['POST'])
    @admin_required
    def admin_create_admin_user():
        """Creates a new administrator account."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        result = admin_service.create_admin_account(
            full_name=full_name,
            email=email,
            password=password,
            admin_user_id=session.get('user_id'),
            admin_name=admin_name
        )
        if result.get('success'):
            flash(result.get('message', "Administrator created successfully."), "success")
        else:
            flash(result.get('error', "Could not create administrator."), "error")
        return redirect(url_for('admin_users_view'))

    # ---------------------------------------------------------
    # 3. Career Taxonomy Management
    # ---------------------------------------------------------
    @app.route('/admin/careers')
    @admin_required
    def admin_careers_view():
        """Career pathways taxonomy management."""
        current_admin = db.session.get(User, session.get('user_id'))
        search_query = request.args.get('q', '').strip()
        careers_list = admin_service.get_careers_list(search_query=search_query if search_query else None)

        return render_template(
            'admin/careers.html',
            current_user=current_admin,
            careers=careers_list,
            search_query=search_query,
            active_page='careers'
        )

    @app.route('/admin/careers/save', methods=['POST'])
    @admin_required
    def admin_career_save():
        """Creates or updates a custom career."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        career_id = request.form.get('career_id', type=int)
        title = request.form.get('title', '').strip()
        category = request.form.get('category', 'Technology').strip()
        description = request.form.get('description', '').strip()
        core_skills = request.form.get('core_skills', '')
        secondary_skills = request.form.get('secondary_skills', '')
        experience_level = request.form.get('experience_level', 'All Experience Levels').strip()
        salary_range = request.form.get('salary_range', '₹6,00,000 - ₹15,00,000 / yr').strip()
        market_demand = request.form.get('market_demand', 'High Demand').strip()

        result = admin_service.save_career(
            title=title,
            category=category,
            description=description,
            core_skills=core_skills,
            secondary_skills=secondary_skills,
            experience_level=experience_level,
            salary_range=salary_range,
            market_demand=market_demand,
            career_id=career_id,
            admin_user_id=session.get('user_id'),
            admin_name=admin_name
        )

        if result.get('success'):
            flash(result.get('message', "Career saved successfully!"), "success")
        else:
            flash(result.get('error', "Could not save career."), "error")

        return redirect(url_for('admin_careers_view'))

    @app.route('/admin/careers/<int:career_id>/delete', methods=['POST'])
    @admin_required
    def admin_career_delete(career_id):
        """Deletes a custom career record."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        result = admin_service.delete_career(career_id, admin_user_id=session.get('user_id'), admin_name=admin_name)
        if result.get('success'):
            flash(result.get('message', "Career deleted."), "success")
        else:
            flash(result.get('error', "Could not delete career."), "error")
        return redirect(url_for('admin_careers_view'))

    # ---------------------------------------------------------
    # 4. Skill Repository Management
    # ---------------------------------------------------------
    @app.route('/admin/skills')
    @admin_required
    def admin_skills_view():
        """Skill repository and syllabus management."""
        current_admin = db.session.get(User, session.get('user_id'))
        search_query = request.args.get('q', '').strip()
        skills_list = admin_service.get_skills_list(search_query=search_query if search_query else None)

        return render_template(
            'admin/skills.html',
            current_user=current_admin,
            skills=skills_list,
            search_query=search_query,
            active_page='skills'
        )

    @app.route('/admin/skills/save', methods=['POST'])
    @admin_required
    def admin_skill_save():
        """Creates or updates a skill definition."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        skill_id = request.form.get('skill_id', type=int)
        name = request.form.get('name', '').strip()
        category = request.form.get('category', 'Technical').strip()
        difficulty = request.form.get('difficulty', 'Moderate').strip()
        demand_status = request.form.get('demand_status', 'In-Demand').strip()
        description = request.form.get('description', '').strip()
        topics = request.form.get('topics', '')

        result = admin_service.save_skill(
            name=name,
            category=category,
            description=description,
            topics=topics,
            difficulty=difficulty,
            demand_status=demand_status,
            skill_id=skill_id,
            admin_user_id=session.get('user_id'),
            admin_name=admin_name
        )

        if result.get('success'):
            flash(result.get('message', "Skill saved successfully!"), "success")
        else:
            flash(result.get('error', "Could not save skill."), "error")

        return redirect(url_for('admin_skills_view'))

    @app.route('/admin/skills/<int:skill_id>/delete', methods=['POST'])
    @admin_required
    def admin_skill_delete(skill_id):
        """Deletes a skill definition."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        result = admin_service.delete_skill(skill_id, admin_user_id=session.get('user_id'), admin_name=admin_name)
        if result.get('success'):
            flash(result.get('message', "Skill deleted."), "success")
        else:
            flash(result.get('error', "Could not delete skill."), "error")
        return redirect(url_for('admin_skills_view'))

    # ---------------------------------------------------------
    # 5. Market Requirements Management
    # ---------------------------------------------------------
    @app.route('/admin/market-requirements')
    @admin_required
    def admin_market_requirements_view():
        """Market requirement benchmarks management."""
        current_admin = db.session.get(User, session.get('user_id'))
        search_query = request.args.get('q', '').strip()
        career_filter = request.args.get('career', '').strip()

        reqs = admin_service.get_market_requirements(
            career_filter=career_filter if career_filter else None,
            search_query=search_query if search_query else None
        )

        return render_template(
            'admin/market_requirements.html',
            current_user=current_admin,
            requirements=reqs,
            search_query=search_query,
            career_filter=career_filter,
            active_page='market'
        )

    @app.route('/admin/market-requirements/save', methods=['POST'])
    @admin_required
    def admin_market_requirement_save():
        """Creates or updates a market requirement benchmark."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        req_id = request.form.get('req_id', type=int)
        career_title = request.form.get('career_title', '').strip()
        skill_name = request.form.get('skill_name', '').strip()
        required_level = request.form.get('required_level', 'Intermediate').strip()
        importance = request.form.get('importance', 'Important').strip()
        experience_level = request.form.get('experience_level', 'Entry to Mid-Level').strip()
        salary_range = request.form.get('salary_range', 'Industry Benchmark').strip()
        market_demand = request.form.get('market_demand', 'High Demand').strip()
        estimated_hours = request.form.get('estimated_hours', 20.0, type=float)
        topics = request.form.get('topics', '')
        source_reference = request.form.get('source_reference', 'Industry Benchmark').strip()
        is_verified = bool(request.form.get('is_verified'))

        result = admin_service.save_market_requirement(
            career_title=career_title,
            skill_name=skill_name,
            required_level=required_level,
            importance=importance,
            experience_level=experience_level,
            salary_range=salary_range,
            market_demand=market_demand,
            topics=topics,
            estimated_hours=estimated_hours,
            source_reference=source_reference,
            is_verified=is_verified,
            req_id=req_id,
            admin_user_id=session.get('user_id'),
            admin_name=admin_name
        )

        if result.get('success'):
            flash(result.get('message', "Market requirement saved successfully!"), "success")
        else:
            flash(result.get('error', "Could not save market requirement."), "error")

        return redirect(url_for('admin_market_requirements_view'))

    @app.route('/admin/market-requirements/<int:req_id>/delete', methods=['POST'])
    @admin_required
    def admin_market_requirement_delete(req_id):
        """Deletes a market requirement record."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        result = admin_service.delete_market_requirement(req_id, admin_user_id=session.get('user_id'), admin_name=admin_name)
        if result.get('success'):
            flash(result.get('message', "Market requirement deleted."), "success")
        else:
            flash(result.get('error', "Could not delete market requirement."), "error")
        return redirect(url_for('admin_market_requirements_view'))

    # ---------------------------------------------------------
    # 6. Course Catalog Management
    # ---------------------------------------------------------
    @app.route('/admin/courses')
    @admin_required
    def admin_courses_view():
        """Learning resources catalog management."""
        current_admin = db.session.get(User, session.get('user_id'))
        search_query = request.args.get('q', '').strip()
        skill_filter = request.args.get('skill', '').strip()
        provider_filter = request.args.get('provider', '').strip()

        courses_list = admin_service.get_courses_list(
            search_query=search_query if search_query else None,
            skill_filter=skill_filter if skill_filter else None,
            provider_filter=provider_filter if provider_filter else None
        )

        return render_template(
            'admin/courses.html',
            current_user=current_admin,
            courses=courses_list,
            search_query=search_query,
            skill_filter=skill_filter,
            provider_filter=provider_filter,
            active_page='courses'
        )

    @app.route('/admin/courses/save', methods=['POST'])
    @admin_required
    def admin_course_save():
        """Creates or updates a course record."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        course_id = request.form.get('course_id', type=int)
        title = request.form.get('title', '').strip()
        provider = request.form.get('provider', '').strip()
        skill = request.form.get('skill', '').strip()
        url = request.form.get('url', '').strip()
        category = request.form.get('category', 'Technical').strip()
        level = request.form.get('level', 'Beginner').strip()
        duration_hours = request.form.get('duration_hours', 10.0, type=float)
        difficulty = request.form.get('difficulty', 'Moderate').strip()
        rating = request.form.get('rating', type=float)
        description = request.form.get('description', '').strip()
        topics = request.form.get('topics', '')

        result = admin_service.save_course(
            title=title,
            provider=provider,
            skill=skill,
            url=url,
            category=category,
            level=level,
            duration_hours=duration_hours,
            difficulty=difficulty,
            rating=rating,
            description=description,
            topics=topics,
            course_id=course_id,
            admin_user_id=session.get('user_id'),
            admin_name=admin_name
        )

        if result.get('success'):
            flash(result.get('message', "Course saved successfully!"), "success")
        else:
            flash(result.get('error', "Could not save course."), "error")

        return redirect(url_for('admin_courses_view'))

    @app.route('/admin/courses/<int:course_id>/toggle-status', methods=['POST'])
    @admin_required
    def admin_course_toggle_status(course_id):
        """Toggles active/disabled status for a course."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        result = admin_service.toggle_course_status(course_id, admin_user_id=session.get('user_id'), admin_name=admin_name)
        if result.get('success'):
            flash(result.get('message', "Course status updated."), "success")
        else:
            flash(result.get('error', "Could not update course status."), "error")
        return redirect(url_for('admin_courses_view'))

    @app.route('/admin/courses/<int:course_id>/delete', methods=['POST'])
    @admin_required
    def admin_course_delete(course_id):
        """Deletes a course record."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        result = admin_service.delete_course(course_id, admin_user_id=session.get('user_id'), admin_name=admin_name)
        if result.get('success'):
            flash(result.get('message', "Course deleted successfully."), "success")
        else:
            flash(result.get('error', "Could not delete course."), "error")
        return redirect(url_for('admin_courses_view'))

    # ---------------------------------------------------------
    # 7. Assessment Diagnostics Management
    # ---------------------------------------------------------
    @app.route('/admin/assessments')
    @admin_required
    def admin_assessments_view():
        """Assessment questions and diagnostics management."""
        current_admin = db.session.get(User, session.get('user_id'))
        search_query = request.args.get('q', '').strip()
        skill_filter = request.args.get('skill', '').strip()
        difficulty_filter = request.args.get('difficulty', '').strip()

        questions_list = admin_service.get_assessments_list(
            search_query=search_query if search_query else None,
            skill_filter=skill_filter if skill_filter else None,
            difficulty_filter=difficulty_filter if difficulty_filter else None
        )
        analytics = admin_service.get_assessment_analytics()

        return render_template(
            'admin/assessments.html',
            current_user=current_admin,
            questions=questions_list,
            analytics=analytics,
            search_query=search_query,
            skill_filter=skill_filter,
            difficulty_filter=difficulty_filter,
            active_page='assessments'
        )

    @app.route('/admin/assessments/save', methods=['POST'])
    @admin_required
    def admin_assessment_save():
        """Creates or updates an assessment question."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        question_id = request.form.get('question_id', type=int)
        skill = request.form.get('skill', '').strip()
        topic = request.form.get('topic', '').strip()
        question = request.form.get('question', '').strip()
        options_raw = request.form.get('options', '').strip()
        correct_answer = request.form.get('correct_answer', '').strip()
        difficulty = request.form.get('difficulty', 'Moderate').strip()
        explanation = request.form.get('explanation', '').strip()

        options = [line.strip() for line in options_raw.splitlines() if line.strip()]

        result = admin_service.save_assessment_question(
            skill=skill,
            question=question,
            options=options,
            correct_answer=correct_answer,
            topic=topic,
            difficulty=difficulty,
            explanation=explanation,
            question_id=question_id,
            admin_user_id=session.get('user_id'),
            admin_name=admin_name
        )

        if result.get('success'):
            flash(result.get('message', "Assessment question saved successfully!"), "success")
        else:
            flash(result.get('error', "Could not save question."), "error")

        return redirect(url_for('admin_assessments_view'))

    @app.route('/admin/assessments/<int:question_id>/delete', methods=['POST'])
    @admin_required
    def admin_assessment_delete(question_id):
        """Deletes an assessment question."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        result = admin_service.delete_assessment_question(question_id, admin_user_id=session.get('user_id'), admin_name=admin_name)
        if result.get('success'):
            flash(result.get('message', "Question deleted."), "success")
        else:
            flash(result.get('error', "Could not delete question."), "error")
        return redirect(url_for('admin_assessments_view'))

    # ---------------------------------------------------------
    # 8. Roadmaps Oversight
    # ---------------------------------------------------------
    @app.route('/admin/roadmaps')
    @admin_required
    def admin_roadmaps_view():
        """Roadmap adoption and milestones analytics."""
        current_admin = db.session.get(User, session.get('user_id'))
        analytics = admin_service.get_roadmap_analytics()

        return render_template(
            'admin/roadmaps.html',
            current_user=current_admin,
            analytics=analytics,
            active_page='roadmaps'
        )

    # ---------------------------------------------------------
    # 9. Enterprise Analytics Dashboard
    # ---------------------------------------------------------
    @app.route('/admin/analytics')
    @admin_required
    def admin_analytics_view():
        """Platform analytics telemetry and empirical gap distributions."""
        current_admin = db.session.get(User, session.get('user_id'))
        analytics = admin_service.get_full_analytics()

        return render_template(
            'admin/analytics.html',
            current_user=current_admin,
            analytics=analytics,
            active_page='analytics'
        )

    # ---------------------------------------------------------
    # 10. Admin Governance & Activity Log
    # ---------------------------------------------------------
    @app.route('/admin/activity-log')
    @admin_required
    def admin_activity_log_view():
        """Admin governance activity audit logs."""
        current_admin = db.session.get(User, session.get('user_id'))
        logs = admin_service.get_admin_activity_logs(limit=200)

        return render_template(
            'admin/activity_log.html',
            current_user=current_admin,
            logs=logs,
            active_page='activity_log'
        )

    @app.route('/api/admin/activity-log', methods=['GET'])
    @admin_required
    def api_admin_activity_log():
        """JSON endpoint returning recent audit logs for administration tools."""
        limit = request.args.get('limit', 100, type=int)
        logs = admin_service.get_admin_activity_logs(limit=limit)
        return jsonify({'success': True, 'logs': logs})

    # ---------------------------------------------------------
    # 11. Platform Settings & Maintenance
    # ---------------------------------------------------------
    @app.route('/admin/settings')
    @admin_required
    def admin_settings_view():
        """Platform runtime settings and maintenance operations."""
        current_admin = db.session.get(User, session.get('user_id'))

        return render_template(
            'admin/settings.html',
            current_user=current_admin,
            active_page='settings'
        )

    @app.route('/admin/settings/seed-courses', methods=['POST'])
    @admin_required
    def admin_settings_seed_courses():
        """Synchronizes and seeds course catalog."""
        recommendation_service.seed_courses_if_empty()
        flash("Course catalog verified and synchronized successfully.", "success")
        return redirect(url_for('admin_settings_view'))

    @app.route('/admin/settings/seed-questions', methods=['POST'])
    @admin_required
    def admin_settings_seed_questions():
        """Synchronizes diagnostic questions pool."""
        assessment_service.seed_questions_if_empty()
        flash("Assessment diagnostics pool verified and synchronized successfully.", "success")
        return redirect(url_for('admin_settings_view'))

    # ---------------------------------------------------------
    # 11. Course Feedback Quality Portal (Module 9 Integration)
    # ---------------------------------------------------------
    @app.route('/admin/feedback')
    @admin_required
    def admin_feedback():
        """Admin Course Feedback & Quality Analytics Dashboard."""
        user_id = session.get('user_id')
        user = db.session.get(User, user_id)

        search_query = request.args.get('q', '').strip()
        min_rating = request.args.get('min_rating', '').strip()
        usefulness_filter = request.args.get('usefulness', '').strip()
        course_id_filter = request.args.get('course_id', type=int)

        min_rating_val = int(min_rating) if min_rating.isdigit() else None

        feedbacks = feedback_service.get_all_feedbacks_for_admin(
            limit=200,
            course_id=course_id_filter,
            min_rating=min_rating_val,
            usefulness=usefulness_filter if usefulness_filter else None,
            search_query=search_query if search_query else None
        )
        analytics = feedback_service.get_feedback_analytics()
        all_courses = Course.query.order_by(Course.title.asc()).all()

        return render_template(
            'admin_feedback.html',
            user=user,
            feedbacks=feedbacks,
            analytics=analytics,
            courses=all_courses,
            selected_course_id=course_id_filter,
            search_query=search_query,
            min_rating=min_rating,
            usefulness_filter=usefulness_filter,
            active_page='feedback'
        )

    @app.route('/api/admin/feedbacks', methods=['GET'])
    @admin_required
    def api_admin_feedbacks():
        """JSON endpoint returning feedback list and analytics for admin consumers."""
        search_query = request.args.get('q', '').strip()
        min_rating = request.args.get('min_rating', type=int)
        usefulness = request.args.get('usefulness')
        course_id = request.args.get('course_id', type=int)

        feedbacks = feedback_service.get_all_feedbacks_for_admin(
            limit=200,
            course_id=course_id,
            min_rating=min_rating,
            usefulness=usefulness,
            search_query=search_query
        )
        analytics = feedback_service.get_feedback_analytics()

        return jsonify({
            'success': True,
            'analytics': analytics,
            'feedbacks': feedbacks
        })

    # ---------------------------------------------------------
    # 12. Suggestions Moderation Hub (Module 10 Integration)
    # ---------------------------------------------------------
    @app.route('/admin/suggestions')
    @admin_required
    def admin_suggestions():
        """Admin Suggestions & Improvements Management Hub."""
        user_id = session.get('user_id')
        user = db.session.get(User, user_id)

        search_query = request.args.get('q', '').strip()
        status_filter = request.args.get('status', '').strip()
        category_filter = request.args.get('category', '').strip()

        suggestions = suggestion_service.get_all_suggestions_for_admin(
            status=status_filter if status_filter else None,
            category=category_filter if category_filter else None,
            search_query=search_query if search_query else None,
            limit=200
        )
        analytics = suggestion_service.get_suggestion_analytics()

        return render_template(
            'admin_suggestions.html',
            user=user,
            suggestions=suggestions,
            analytics=analytics,
            categories=suggestion_service.CATEGORIES,
            statuses=suggestion_service.STATUSES,
            search_query=search_query,
            status_filter=status_filter,
            category_filter=category_filter,
            active_page='suggestions'
        )

    @app.route('/admin/suggestions/<int:suggestion_id>/respond', methods=['POST'])
    @admin_required
    def admin_respond_suggestion(suggestion_id):
        """Admin action route to update suggestion status and write response."""
        current_admin = db.session.get(User, session.get('user_id'))
        admin_name = current_admin.full_name if current_admin else 'Administrator'

        status = request.form.get('status', 'Under Review').strip()
        admin_response = request.form.get('admin_response', '').strip()

        result = suggestion_service.admin_update_suggestion(
            suggestion_id=suggestion_id,
            status=status,
            admin_response=admin_response
        )

        if result.get('success'):
            admin_service.log_admin_action(
                admin_id=session.get('user_id'),
                admin_name=admin_name,
                action='Responded to Suggestion',
                target_type='Suggestion',
                target_name=f"Suggestion #{suggestion_id}",
                details=f"Updated status to '{status}'"
            )
            flash(f"Suggestion #{suggestion_id} updated to '{status}' with admin response.", "success")
        else:
            flash(result.get('error', "Could not update suggestion."), "error")

        return redirect(url_for('admin_suggestions'))

    @app.route('/api/admin/suggestions', methods=['GET'])
    @admin_required
    def api_admin_suggestions():
        """JSON endpoint returning suggestions and analytics for admin consumers."""
        search_query = request.args.get('q', '').strip()
        status_filter = request.args.get('status')
        category_filter = request.args.get('category')

        suggestions = suggestion_service.get_all_suggestions_for_admin(
            status=status_filter,
            category=category_filter,
            search_query=search_query
        )
        analytics = suggestion_service.get_suggestion_analytics()

        return jsonify({
            'success': True,
            'analytics': analytics,
            'suggestions': suggestions
        })

    @app.route('/api/admin/suggestions/<int:suggestion_id>/update', methods=['POST'])
    @admin_required
    def api_admin_update_suggestion(suggestion_id):
        """AJAX endpoint for admin status and response update."""
        data = request.get_json(silent=True) or request.form
        status = data.get('status', 'Under Review')
        admin_response = data.get('admin_response')

        result = suggestion_service.admin_update_suggestion(
            suggestion_id=suggestion_id,
            status=status,
            admin_response=admin_response
        )
        return jsonify(result)

    # ---------------------------------------------------------
    # AI Career Roadmap Routes (Module 5)
    # ---------------------------------------------------------
    @app.route('/roadmap')
    @app.route('/roadmap/<int:user_id>')
    def roadmap(user_id=None):
        """
        Personalized AI Career Roadmap Page.
        Displays dynamic milestone-driven learning pathway sequenced across 5 progressive phases.
        """
        user = None
        if user_id:
            user = db.session.get(User, user_id)
        elif session.get('user_id'):
            user = db.session.get(User, session.get('user_id'))
        else:
            user = User.query.order_by(User.id.desc()).first()

        # Determine target role
        target_role = request.args.get('role')
        if not target_role and user:
            tc = TargetCareer.query.filter_by(user_id=user.id).first()
            if tc:
                target_role = tc.career_name
            elif user.profiles:
                target_role = user.profiles[-1].target_role
        if not target_role:
            target_role = "Data Analyst"

        roadmap_data = roadmap_service.get_or_generate_roadmap(user=user, target_role=target_role)

        return render_template(
            'roadmap.html',
            user=user,
            roadmap=roadmap_data,
            target_role=target_role
        )

    @app.route('/roadmap/generate', methods=['POST'])
    def generate_roadmap_action():
        """Regenerates the roadmap with latest skill gaps and preferences."""
        user_id = session.get('user_id')
        user = db.session.get(User, user_id) if user_id else None

        target_role = request.form.get('target_role')
        if not target_role and user:
            tc = TargetCareer.query.filter_by(user_id=user.id).first()
            target_role = tc.career_name if tc else "Data Analyst"

        roadmap_service.generate_roadmap(user=user, target_role=target_role)
        flash("AI Career Roadmap regenerated with your latest skill profile!", "success")
        return redirect(url_for('roadmap'))

    @app.route('/api/roadmap/task-toggle', methods=['POST'])
    def api_roadmap_task_toggle():
        """Interactive AJAX endpoint to toggle task completion within a milestone."""
        data = request.get_json(silent=True) or request.form
        roadmap_id = data.get('roadmap_id')
        milestone_id = data.get('milestone_id')
        task_id = data.get('task_id')
        completed = data.get('completed', True)

        if isinstance(completed, str):
            completed = completed.lower() in ['true', '1', 'yes']

        if not roadmap_id or not milestone_id or task_id is None:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

        try:
            r_id = int(roadmap_id)
            m_id = int(milestone_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid ID format'}), 400

        res = roadmap_service.toggle_milestone_task(
            roadmap_id=r_id,
            milestone_id=m_id,
            task_id=task_id,
            completed=completed
        )
        return jsonify(res)

    @app.route('/api/roadmap/milestone-status', methods=['POST'])
    def api_roadmap_milestone_status():
        """AJAX endpoint to mark an entire milestone completed/incomplete."""
        data = request.get_json(silent=True) or request.form
        roadmap_id = data.get('roadmap_id')
        milestone_id = data.get('milestone_id')
        is_completed = data.get('is_completed', True)

        if isinstance(is_completed, str):
            is_completed = is_completed.lower() in ['true', '1', 'yes']

        if not roadmap_id or not milestone_id:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

        try:
            r_id = int(roadmap_id)
            m_id = int(milestone_id)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid ID format'}), 400

        res = roadmap_service.update_milestone_status(
            roadmap_id=r_id,
            milestone_id=m_id,
            is_completed=is_completed
        )
        return jsonify(res)

    @app.route('/api/roadmap-data', methods=['GET'])
    def api_roadmap_data():
        """JSON endpoint returning roadmap structure and progress."""
        user_id = request.args.get('user_id', type=int) or session.get('user_id')
        role = request.args.get('role')
        user = db.session.get(User, user_id) if user_id else None
        data = roadmap_service.get_or_generate_roadmap(user=user, target_role=role)
        return jsonify(data)

    # ---------------------------------------------------------
    # Market Trend Analytics Routes (Module 6)
    # ---------------------------------------------------------
    @app.route('/market-trends')
    @app.route('/analytics')
    def market_trends():
        """
        Interactive Market Trend Analytics & Salary Insights Dashboard.
        Leverages Pandas & Plotly to display real-time industry compensation benchmarks,
        skill growth velocity, hiring distributions, and tech stack adoption.
        """
        selected_role_id = request.args.get('role', 'all').strip().lower()
        currency = request.args.get('currency', 'usd').strip().lower()
        if currency not in ['usd', 'inr']:
            currency = 'usd'

        overview = market_trend_service.get_market_overview(currency=currency)
        available_roles = market_trend_service.get_all_roles_list()
        selected_role_data = market_trend_service.get_role_data(selected_role_id)

        # Salary Benchmarks DataFrame & Chart
        salary_df = market_trend_service.get_salary_benchmark_df(currency=currency, role_id=selected_role_id)
        chart_salary_json = generate_salary_benchmark_chart(salary_df, currency=currency)

        # Skills Demand & Growth DataFrame & Chart
        skills_df = market_trend_service.get_skills_demand_df(role_id=selected_role_id)
        chart_skills_json = generate_skills_growth_bar_chart(skills_df)

        # Industry Hiring Distribution Donut Chart
        industry_dict = market_trend_service.get_industry_hiring_distribution(role_id=selected_role_id)
        chart_industry_json = generate_industry_hiring_donut(industry_dict)

        # Skill ROI Scatter / Bubble Chart
        chart_roi_json = generate_skill_roi_scatter_chart(skills_df)

        # Work Modes Distribution Stacked Chart
        chart_work_modes_json = generate_work_mode_chart(selected_role_data, overview)

        # Developer & Analyst Tools Frequency Chart
        tools_list = market_trend_service.get_tools_frequency(role_id=selected_role_id)
        chart_tools_json = generate_tools_popularity_chart(tools_list)

        return render_template(
            'market_trends.html',
            overview=overview,
            available_roles=available_roles,
            selected_role_id=selected_role_id,
            selected_role_data=selected_role_data,
            currency=currency,
            chart_salary_json=chart_salary_json,
            chart_skills_json=chart_skills_json,
            chart_industry_json=chart_industry_json,
            chart_roi_json=chart_roi_json,
            chart_work_modes_json=chart_work_modes_json,
            chart_tools_json=chart_tools_json
        )

    @app.route('/api/market-trends', methods=['GET'])
    def api_market_trends():
        """REST API endpoint returning market trend analytics and Plotly chart JSONs."""
        role_id = request.args.get('role', 'all')
        currency = request.args.get('currency', 'usd')

        overview = market_trend_service.get_market_overview(currency=currency)
        role_data = market_trend_service.get_role_data(role_id)
        salary_df = market_trend_service.get_salary_benchmark_df(currency=currency, role_id=role_id)
        skills_df = market_trend_service.get_skills_demand_df(role_id=role_id)
        industry_dict = market_trend_service.get_industry_hiring_distribution(role_id=role_id)
        tools_list = market_trend_service.get_tools_frequency(role_id=role_id)

        chart_salary_json = generate_salary_benchmark_chart(salary_df, currency=currency)
        chart_skills_json = generate_skills_growth_bar_chart(skills_df)
        chart_industry_json = generate_industry_hiring_donut(industry_dict)
        chart_roi_json = generate_skill_roi_scatter_chart(skills_df)
        chart_work_modes_json = generate_work_mode_chart(role_data, overview)
        chart_tools_json = generate_tools_popularity_chart(tools_list)

        return jsonify({
            'success': True,
            'overview': overview,
            'selected_role': role_data,
            'chart_salary_json': chart_salary_json,
            'chart_skills_json': chart_skills_json,
            'chart_industry_json': chart_industry_json,
            'chart_roi_json': chart_roi_json,
            'chart_work_modes_json': chart_work_modes_json,
            'chart_tools_json': chart_tools_json
        })

    # ---------------------------------------------------------
    # API Endpoints
    # ---------------------------------------------------------
    @app.route('/api/assess-topics', methods=['POST'])
    def api_assess_topics():
        """
        Interactive AJAX endpoint allowing the user to refine known topics for any skill.
        Recalculates remaining topics, remaining hours, readiness score, and updates DB.
        """
        data = request.get_json(silent=True) or request.form
        user_id = data.get('user_id') or session.get('user_id')
        skill_name = data.get('skill_name')
        checked_topics = data.get('checked_topics', [])
        target_role = data.get('target_role')

        user = db.session.get(User, user_id) if user_id else None
        
        if not skill_name:
            return jsonify({'success': False, 'error': 'Skill name is required'}), 400

        # Load existing topic evaluations
        saved_analysis = SkillGapAnalysis.query.filter_by(user_id=user.id).order_by(SkillGapAnalysis.id.desc()).first() if user else None
        topic_evaluations = saved_analysis.get_topic_evaluations() if saved_analysis else {}

        # Update topic evaluation for this skill
        canonical_name, _ = normalize_skill(skill_name)
        topic_evaluations[canonical_name] = checked_topics

        # Re-run analysis with updated topic evaluations
        analysis = skill_gap_service.analyze_skill_gap(
            user=user,
            target_role=target_role or (saved_analysis.target_role if saved_analysis else 'Data Analyst'),
            custom_topic_evaluations=topic_evaluations
        )

        if user:
            skill_gap_service.save_analysis_to_db(user.id, analysis)

        # Generate updated chart JSONs
        gauge_json = generate_readiness_gauge(analysis['readiness_score'])
        donut_json = generate_skill_breakdown_donut(
            analysis['strong_count'], 
            analysis['partial_count'], 
            analysis['missing_count']
        )
        bar_json = generate_level_comparison_chart(analysis['gap_items'])
        hours_json = generate_priority_hours_chart(analysis['gap_items'])

        return jsonify({
            'success': True,
            'analysis': analysis,
            'gauge_json': gauge_json,
            'donut_json': donut_json,
            'bar_json': bar_json,
            'hours_json': hours_json
        })

    @app.route('/api/skill-gap-data', methods=['GET'])
    def api_skill_gap_data():
        """Returns JSON representation of skill gap analysis for external consumers."""
        user_id = request.args.get('user_id', type=int) or session.get('user_id')
        role = request.args.get('role')
        user = db.session.get(User, user_id) if user_id else None
        analysis = skill_gap_service.analyze_skill_gap(user=user, target_role=role)
        return jsonify(analysis)

    @app.route('/api/analyze-career', methods=['POST', 'GET'])
    def api_analyze_career():
        """AJAX API endpoint to analyze any entered career role."""
        if request.method == 'POST':
            data = request.get_json(silent=True) or request.form
            role_text = data.get('career_role', '')
        else:
            role_text = request.args.get('role', '')

        analysis = career_service.analyze_career_role(role_text)
        return jsonify(analysis)

    # ---------------------------------------------------------
    # Error Handlers
    # ---------------------------------------------------------
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('500.html'), 500

    return app

app = create_app()

if __name__ == '__main__':
    print("==================================================")
    print("[*] Starting CareerSkill AI Server...")
    print(f"[*] Database: {INSTANCE_DIR / 'careerskill.db'}")
    print("[*] URL: http://127.0.0.1:5000")
    print("[*] Mode: Dark Mode Theme (Flask + Bootstrap 5)")
    print("==================================================")
    app.run(host='127.0.0.1', port=5000, debug=True)
