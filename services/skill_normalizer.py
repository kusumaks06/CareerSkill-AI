import re
from difflib import SequenceMatcher

# Canonical synonym dictionary
CANONICAL_SYNONYMS = {
    # SQL & Databases
    'sql': 'SQL',
    'postgresql': 'SQL',
    'postgres': 'SQL',
    'mysql': 'SQL',
    'sql server': 'SQL',
    'plsql': 'SQL',
    'tsql': 'SQL',
    't-sql': 'SQL',
    'sqlite': 'SQL',
    'oracle sql': 'SQL',
    'structured query language': 'SQL',

    # Python & Programming
    'python': 'Python',
    'python3': 'Python',
    'python 3': 'Python',
    'py': 'Python',
    'python programming': 'Python',

    # Excel
    'excel': 'Excel',
    'ms excel': 'Excel',
    'microsoft excel': 'Excel',
    'advanced excel': 'Excel',
    'spreadsheets': 'Excel',
    'excel vba': 'Excel',

    # Power BI & Tableau
    'power bi': 'Power BI',
    'powerbi': 'Power BI',
    'microsoft power bi': 'Power BI',
    'ms power bi': 'Power BI',
    'power-bi': 'Power BI',
    'power_bi': 'Power BI',
    'power bi desktop': 'Power BI',
    'tableau': 'Tableau',
    'tableau desktop': 'Tableau',
    'tableau server': 'Tableau',

    # Analytics & Stats
    'statistics': 'Statistics',
    'stats': 'Statistics',
    'statistical analysis': 'Statistics',
    'probability': 'Statistics',
    'probability & statistics': 'Statistics',
    'probability and statistics': 'Statistics',
    'biostatistics': 'Statistics',

    # Data Handling & Cleaning
    'data cleaning': 'Data Cleaning',
    'data cleansing': 'Data Cleaning',
    'data wrangling': 'Data Cleaning',
    'data munging': 'Data Cleaning',
    'data preprocessing': 'Data Cleaning',
    'exploratory data analysis': 'Exploratory Data Analysis (EDA)',
    'eda': 'Exploratory Data Analysis (EDA)',
    'exploratory data analysis (eda)': 'Exploratory Data Analysis (EDA)',

    # Data Visualization
    'data visualization': 'Data Visualization',
    'data visualisation': 'Data Visualization',
    'dataviz': 'Data Visualization',
    'data viz': 'Data Visualization',
    'visualization': 'Data Visualization',
    'visualisation': 'Data Visualization',
    'matplotlib': 'Data Visualization',
    'seaborn': 'Data Visualization',
    'plotly': 'Data Visualization',

    # Python Libraries
    'pandas': 'Pandas',
    'pandas dataframe': 'Pandas',
    'numpy': 'NumPy',
    'numpy arrays': 'NumPy',
    'scikit-learn': 'Scikit-learn',
    'scikit learn': 'Scikit-learn',
    'sklearn': 'Scikit-learn',

    # Machine Learning & AI
    'machine learning': 'Machine Learning',
    'ml': 'Machine Learning',
    'applied ml': 'Machine Learning',
    'applied machine learning': 'Machine Learning',
    'deep learning': 'Deep Learning',
    'dl': 'Deep Learning',
    'neural networks': 'Deep Learning',
    'artificial neural networks': 'Deep Learning',
    'pytorch': 'PyTorch',
    'torch': 'PyTorch',
    'tensorflow': 'TensorFlow',
    'tf': 'TensorFlow',
    'keras': 'TensorFlow',
    'mlops': 'MLOps',
    'ml ops': 'MLOps',
    'model deployment': 'MLOps',

    # NLP & LLMs
    'natural language processing': 'Natural Language Processing (NLP)',
    'natural language processing (nlp)': 'Natural Language Processing (NLP)',
    'nlp': 'Natural Language Processing (NLP)',
    'large language models': 'Large Language Models (LLMs)',
    'large language models (llms)': 'Large Language Models (LLMs)',
    'llm': 'Large Language Models (LLMs)',
    'llms': 'Large Language Models (LLMs)',
    'genai': 'Large Language Models (LLMs)',
    'generative ai': 'Large Language Models (LLMs)',
    'rag': 'Large Language Models (LLMs)',
    'vector databases': 'Vector Databases',
    'vector db': 'Vector Databases',
    'vector dbs': 'Vector Databases',
    'chromadb': 'Vector Databases',
    'pinecone': 'Vector Databases',

    # Computer Vision
    'computer vision': 'Computer Vision',
    'cv': 'Computer Vision',
    'opencv': 'Computer Vision',

    # Business & Analytics
    'business intelligence': 'Business Intelligence',
    'bi': 'Business Intelligence',
    'bi reporting': 'Business Intelligence',
    'product analytics': 'Product Analytics',
    'product metrics': 'Product Analytics',
    'marketing analytics': 'Marketing Analytics',
    'financial modeling': 'Financial Modeling',
    'financial modelling': 'Financial Modeling',
    'financial analysis': 'Financial Analysis',
    'a/b testing': 'A/B Testing',
    'ab testing': 'A/B Testing',
    'split testing': 'A/B Testing',
    'hypothesis testing': 'A/B Testing',

    # Data Engineering & Warehousing
    'data warehousing': 'Data Warehousing',
    'data warehouse': 'Data Warehousing',
    'snowflake': 'Data Warehousing',
    'bigquery': 'Data Warehousing',
    'etl': 'ETL Pipelines',
    'etl pipelines': 'ETL Pipelines',
    'etl pipeline design': 'ETL Pipelines',
    'data pipeline': 'ETL Pipelines',
    'data pipelines': 'ETL Pipelines',
    'airflow': 'ETL Pipelines',

    # Software Engineering & DevOps
    'restful api development': 'RESTful API Development',
    'rest api': 'RESTful API Development',
    'rest apis': 'RESTful API Development',
    'fastapi': 'RESTful API Development',
    'flask': 'RESTful API Development',
    'django': 'RESTful API Development',
    'api development': 'RESTful API Development',
    'docker': 'Docker',
    'docker containers': 'Docker',
    'git': 'Git',
    'git & github': 'Git',
    'github': 'Git',
    'version control': 'Git',
    'ci/cd pipelines': 'CI/CD Pipelines',
    'ci/cd': 'CI/CD Pipelines',
    'cicd': 'CI/CD Pipelines',

    # Soft Skills & Business
    'communication': 'Communication',
    'verbal communication': 'Communication',
    'written communication': 'Communication',
    'problem solving': 'Problem Solving',
    'critical thinking': 'Problem Solving',
    'analytical thinking': 'Problem Solving',
    'requirement gathering': 'Requirement Gathering',
    'requirements gathering': 'Requirement Gathering',
    'stakeholder communication': 'Stakeholder Communication',
    'stakeholder management': 'Stakeholder Communication'
}


def clean_skill_key(text: str) -> str:
    """Removes special characters and extra whitespace for key normalization."""
    if not text:
        return ""
    cleaned = text.lower()
    cleaned = re.sub(r'[^a-z0-9\s]', ' ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def normalize_skill(skill_name: str) -> tuple[str, str]:
    """
    Normalizes a skill name into:
    (Canonical Display Name, Clean Search Key)
    """
    if not skill_name or not skill_name.strip():
        return "", ""

    raw_name = skill_name.strip()
    clean_key = clean_skill_key(raw_name)

    # 1. Direct dictionary lookup on raw lowercase
    raw_lower = raw_name.lower()
    if raw_lower in CANONICAL_SYNONYMS:
        canonical = CANONICAL_SYNONYMS[raw_lower]
        return canonical, clean_skill_key(canonical)

    # 2. Lookup on cleaned key
    if clean_key in CANONICAL_SYNONYMS:
        canonical = CANONICAL_SYNONYMS[clean_key]
        return canonical, clean_skill_key(canonical)

    # 3. Substring / Token matching against known synonyms
    for syn_key, canonical in CANONICAL_SYNONYMS.items():
        syn_clean = clean_skill_key(syn_key)
        if clean_key == syn_clean:
            return canonical, clean_skill_key(canonical)

    # 4. Fuzzy SequenceMatcher fallback if similarity >= 0.88
    best_match = None
    highest_ratio = 0.0
    for syn_key, canonical in CANONICAL_SYNONYMS.items():
        syn_clean = clean_skill_key(syn_key)
        ratio = SequenceMatcher(None, clean_key, syn_clean).ratio()
        if ratio > highest_ratio and ratio >= 0.88:
            highest_ratio = ratio
            best_match = canonical

    if best_match:
        return best_match, clean_skill_key(best_match)

    # Fallback to Title Cased display version
    display = " ".join(word.capitalize() for word in raw_name.split())
    return display, clean_key


def skills_match(skill_a: str, skill_b: str) -> bool:
    """Checks if two skill strings resolve to the same canonical skill."""
    if not skill_a or not skill_b:
        return False
    _, key_a = normalize_skill(skill_a)
    _, key_b = normalize_skill(skill_b)
    if key_a == key_b:
        return True
    
    # Check fuzzy similarity between clean keys
    ratio = SequenceMatcher(None, key_a, key_b).ratio()
    return ratio >= 0.90


def find_matching_skill(user_skill_name: str, target_skills_list: list[str]) -> str | None:
    """
    Finds the matching target benchmark skill from a list of required target skills.
    Returns the target skill name if matched, else None.
    """
    if not user_skill_name or not target_skills_list:
        return None

    _, user_key = normalize_skill(user_skill_name)
    for target in target_skills_list:
        _, target_key = normalize_skill(target)
        if user_key == target_key:
            return target
        if SequenceMatcher(None, user_key, target_key).ratio() >= 0.90:
            return target

    return None
