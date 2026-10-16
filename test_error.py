import pandas as pd
from src.managers import EmployeeManager, AnalyticsManager

emp_manager = EmployeeManager()
analytics = AnalyticsManager()

depts = [d["department_name"] for d in emp_manager.list_departments()]
for dept in depts:
    trend = pd.DataFrame(analytics.get_performance_trends("review", dept))
    top = pd.DataFrame(analytics.get_top_performers("review", dept))
    risk = pd.DataFrame(analytics.get_attrition_risk(dept))
    bottlenecks = pd.DataFrame(analytics.get_project_bottlenecks(dept))
    if trend.empty or top.empty or risk.empty or bottlenecks.empty:
        print(f"Dept: {dept} HAS EMPTY DATA! trend:{trend.empty}, top:{top.empty}, risk:{risk.empty}, bottlenecks:{bottlenecks.empty}")
    else:
        print(f"Dept: {dept} is fine")
