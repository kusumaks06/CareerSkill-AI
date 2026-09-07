import json
import unittest
from app import create_app
from analytics.market_trend_service import MarketTrendService, market_trend_service
from analytics.trend_charts import (
    generate_salary_benchmark_chart,
    generate_skills_growth_bar_chart,
    generate_industry_hiring_donut,
    generate_skill_roi_scatter_chart,
    generate_work_mode_chart,
    generate_tools_popularity_chart
)


class MarketTrendAnalyticsTestCase(unittest.TestCase):
    """Test suite for Module 6: Market Trend Analytics & Salary Insights."""

    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.service = MarketTrendService()

    def tearDown(self):
        self.app_context.pop()

    # ---------------------------------------------------------
    # Service Unit Tests
    # ---------------------------------------------------------
    def test_market_overview_usd_and_inr(self):
        """Verifies summary KPI calculations in USD and INR."""
        overview_usd = self.service.get_market_overview(currency='usd')
        self.assertGreater(overview_usd['total_openings'], 50000)
        self.assertEqual(overview_usd['currency_prefix'], '$')
        self.assertGreater(overview_usd['avg_salary_mid'], 50000)
        self.assertIn('fastest_growing_skill', overview_usd)
        self.assertIn('top_hiring_sector', overview_usd)

        overview_inr = self.service.get_market_overview(currency='inr')
        self.assertEqual(overview_inr['currency_prefix'], '₹')
        self.assertEqual(overview_inr['currency_suffix'], ' LPA')
        self.assertGreater(overview_inr['avg_salary_mid'], 10.0)

    def test_get_all_roles_list(self):
        """Verifies role dropdown list extraction."""
        roles = self.service.get_all_roles_list()
        self.assertGreaterEqual(len(roles), 10)
        role_ids = [r['id'] for r in roles]
        self.assertIn('data_analyst', role_ids)
        self.assertIn('ai_engineer', role_ids)
        self.assertIn('data_scientist', role_ids)

    def test_get_role_data(self):
        """Verifies fetching specific role analytics."""
        analyst = self.service.get_role_data('data_analyst')
        self.assertIsNotNone(analyst)
        self.assertEqual(analyst['title'], 'Data Analyst')
        self.assertIn('salary', analyst)
        self.assertIn('top_skills', analyst)

        # Non-existent role returns None
        none_role = self.service.get_role_data('all')
        self.assertIsNone(none_role)

    def test_salary_benchmark_df(self):
        """Verifies salary DataFrame structure."""
        df_usd = self.service.get_salary_benchmark_df(currency='usd', role_id='all')
        self.assertFalse(df_usd.empty)
        self.assertIn('Entry Level', df_usd.columns)
        self.assertIn('Lead / Principal', df_usd.columns)

        df_single = self.service.get_salary_benchmark_df(currency='inr', role_id='ai_engineer')
        self.assertEqual(len(df_single), 1)

    def test_skills_demand_df(self):
        """Verifies skills demand and growth metrics."""
        skills_all = self.service.get_skills_demand_df(role_id='all')
        self.assertFalse(skills_all.empty)
        self.assertIn('skill_name', skills_all.columns)
        self.assertIn('demand_pct', skills_all.columns)

        skills_role = self.service.get_skills_demand_df(role_id='data_scientist')
        self.assertFalse(skills_role.empty)
        skill_names = skills_role['skill_name'].tolist()
        self.assertIn('Python', skill_names)

    def test_industry_hiring_distribution(self):
        """Verifies industry hiring distribution percentages."""
        industry = self.service.get_industry_hiring_distribution(role_id='all')
        self.assertIsInstance(industry, dict)
        self.assertGreater(len(industry), 0)
        self.assertAlmostEqual(sum(industry.values()), 100.0, delta=1.5)

    def test_tools_frequency(self):
        """Verifies tool frequency ranking."""
        tools = self.service.get_tools_frequency(role_id='all')
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)
        self.assertIn('tool', tools[0])
        self.assertIn('pct', tools[0])

    # ---------------------------------------------------------
    # Plotly Chart Generator Unit Tests
    # ---------------------------------------------------------
    def test_chart_generators_output_valid_json(self):
        """Verifies that all 6 Plotly chart generators output valid serialized JSON."""
        salary_df = self.service.get_salary_benchmark_df(currency='usd')
        skills_df = self.service.get_skills_demand_df()
        industry_dict = self.service.get_industry_hiring_distribution()
        tools_list = self.service.get_tools_frequency()
        role_data = self.service.get_role_data('data_analyst')

        chart_salary = generate_salary_benchmark_chart(salary_df, currency='usd')
        parsed_salary = json.loads(chart_salary)
        self.assertIn('data', parsed_salary)
        self.assertIn('layout', parsed_salary)

        chart_skills = generate_skills_growth_bar_chart(skills_df)
        parsed_skills = json.loads(chart_skills)
        self.assertIn('data', parsed_skills)

        chart_industry = generate_industry_hiring_donut(industry_dict)
        parsed_industry = json.loads(chart_industry)
        self.assertIn('data', parsed_industry)

        chart_roi = generate_skill_roi_scatter_chart(skills_df)
        parsed_roi = json.loads(chart_roi)
        self.assertIn('data', parsed_roi)

        chart_work_modes = generate_work_mode_chart(role_data)
        parsed_wm = json.loads(chart_work_modes)
        self.assertIn('data', parsed_wm)

        chart_tools = generate_tools_popularity_chart(tools_list)
        parsed_tools = json.loads(chart_tools)
        self.assertIn('data', parsed_tools)

    # ---------------------------------------------------------
    # HTTP Routes and REST API Tests
    # ---------------------------------------------------------
    def test_market_trends_html_route(self):
        """Verifies GET /market-trends renders full interactive dashboard."""
        response = self.client.get('/market-trends')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn("Market Trend Analytics", html)
        self.assertIn("Salary Progression by Seniority", html)
        self.assertIn("Skills Demand Frequency vs Growth", html)
        self.assertIn("Hiring by Industry Sector", html)
        self.assertIn("Skill ROI: Demand vs Salary Boost", html)
        self.assertIn("chart-salary", html)
        self.assertIn("chart-skills-growth", html)
        self.assertIn("chart-industry", html)
        self.assertIn("chart-roi", html)

    def test_analytics_alias_route(self):
        """Verifies GET /analytics alias route."""
        response = self.client.get('/analytics')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Market Trend Analytics", html)

    def test_market_trends_with_role_and_inr_filters(self):
        """Verifies GET /market-trends with query parameters."""
        response = self.client.get('/market-trends?role=ai_engineer&currency=inr')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertIn("AI Engineer", html)
        self.assertIn("Role Deep-Dive", html)
        self.assertIn("Check My Skill Gap for This Role", html)

    def test_api_market_trends_json_endpoint(self):
        """Verifies GET /api/market-trends returns structured JSON."""
        response = self.client.get('/api/market-trends')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertTrue(data['success'])
        self.assertIn('overview', data)
        self.assertIn('chart_salary_json', data)
        self.assertIn('chart_skills_json', data)
        self.assertIn('chart_industry_json', data)
        self.assertIn('chart_roi_json', data)
        self.assertIn('chart_work_modes_json', data)
        self.assertIn('chart_tools_json', data)


if __name__ == '__main__':
    unittest.main()
