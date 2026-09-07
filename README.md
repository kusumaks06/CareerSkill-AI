# CareerSkill AI

> **"Learn what matters. Build the skills that matter. Reach the career you want."**

CareerSkill AI is an intelligent, data-driven career planning and skill-gap recommendation platform built as a final-year engineering project for Artificial Intelligence & Data Science (AIDS) / Data Analytics students.

---

## 🎯 Key Features & Modules
1. **Dynamic Career Role Analyzer**: Free-text career role input with NLP TF-IDF cosine similarity & domain requirement synthesis.
2. **7-Step Career Profile Onboarding**: Background, experience, self-reported skills inventory, learning velocity, and career goals.
3. **Secure Authentication & Email OTP Password Reset**:
   - Secure password hashing with Werkzeug.
   - 6-digit random OTP generation with 10-minute expiry.
   - Hashed OTP database storage (`PasswordResetOTP`).
   - Rate limiting: max 5 failed attempts & 60-second resend cooldown.
   - Session-guarded password updates and development console fallback.
4. **Skill Gap Analysis**: Compare current user skill profile against industry demand.
5. **AI Career Roadmap**: Generate personalized milestone-driven learning pathways using ML.
6. **Market Trend Analytics**: Interactive dashboards highlighting in-demand tech stacks and salary insights using Pandas & Plotly.

---

## 🛠️ Technology Stack
- **Backend**: Python 3, Flask, Jinja2
- **Database / ORM**: SQLite, SQLAlchemy
- **Data Analytics & ML**: Pandas, NumPy, Scikit-learn, NLTK, TextBlob, Plotly
- **Frontend / Styling**: HTML5, CSS3, Bootstrap 5 (Dark Mode Theme)

---

## 📁 Project Structure
```text
CareerSkill-AI/
├── app.py                  # Flask Application & route controllers
├── config.py               # Environment & App Configuration
├── requirements.txt        # Python dependency specifications
├── .env.example            # Environment variables template
├── README.md               # Project documentation
│
├── instance/               # SQLite database directory (careerskill.db)
│
├── templates/              # Jinja2 HTML templates
│   ├── base.html           # Master dark-mode layout
│   ├── index.html          # Welcome / Landing page
│   ├── login.html          # User Login
│   ├── forgot_password.html# Request Password Reset OTP
│   ├── verify_otp.html     # Enter & Verify 6-digit OTP
│   ├── reset_password.html # Create New Password
│   ├── get_started.html    # Registration & Career Search
│   ├── onboarding.html     # 7-Step Career Profile Wizard
│   ├── career_analysis.html# Skill Gap Matrix & Diagnostic Visuals
│   ├── assessment_overview.html # Skill Assessment Hub & Progress Tracking
│   ├── assessment_take.html # Interactive Technical Quiz & Knowledge Test
│   ├── assessment_result.html # Three-Way Benchmark Report & Topic Diagnostics
│   ├── course_recommendations.html # Personalized Course Recommendations
│   ├── course_detail.html  # Detailed Course View & Status Tracker
│   ├── roadmap.html        # AI Milestone Learning Roadmap
│   ├── market_trends.html  # Market Trend Analytics & Salary Insights
│   └── dashboard.html      # Authenticated user dashboard
│
├── static/                 # Static web assets
│   ├── css/
│   │   └── style.css       # Custom Dark Mode styling
│   └── images/             # Static logos and visuals
│
├── models/                 # Database models (User, Course, UserRoadmap, AssessmentQuestion, etc.)
├── services/               # Services (CareerService, RecommendationService, RoadmapService, AssessmentService)
├── analytics/              # Analytics & Plotly Charts (gap_charts.py, trend_charts.py)
├── data/                   # Datasets (careers.json, courses.json, market_trends.json, assessment_questions.json)
├── scripts/                # Utility scripts (init_db.py)
└── tests/                  # Automated test suites (80 tests)
```

---

## 📧 Email & SMTP Configuration

CareerSkill AI supports email delivery for password reset verification codes.

### 1. Production / Live SMTP Configuration
To send actual emails to users, configure your SMTP server credentials in a `.env` file:

```env
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=CareerSkill AI <noreply@careerskill.ai>
```

> **Note for Gmail users**: Use a Google App Password (not your regular account password).

### 2. Local Development Mode (No SMTP Credentials Required)
If SMTP credentials are not configured, the application **will not crash**. Instead, the system operates in development mode and outputs the generated 6-digit OTP directly to the **development terminal**:

```text
==================================================
[*] Password reset OTP generated for:
[*] Email: user@example.com
[*] Development OTP: ******
[*] Expiry: 10 minutes
==================================================
```
*(The OTP is never exposed in the browser or HTTP responses).*

---

## 🚀 Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Initialize the SQLite Database
```bash
python scripts/init_db.py
```

### 3. Run the Automated Tests
```bash
python -m unittest discover -s tests
```

### 4. Start the Application
```bash
python app.py
```

### 5. Open in Browser
Navigate to `http://127.0.0.1:5000` to access the CareerSkill AI portal.

## 👩‍💻 Developed By

Kusuma K S

Artificial Intelligence and Data Science Student 

GitHub: https://github.com/kusumaks06
