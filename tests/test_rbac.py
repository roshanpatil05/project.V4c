from src.auth import rbac


def test_can_create_cross_department_projects():
    # Super Admin can create cross-department projects
    super_admin = {"role": "Super Admin", "department_name": "Engineering"}
    assert rbac.can_create_cross_department_projects(super_admin) is True

    # Operations Manager can create cross-department projects
    ops_mgr = {"role": "Department Manager", "department_name": "Operations"}
    assert rbac.can_create_cross_department_projects(ops_mgr) is True

    # Other Department Managers cannot create cross-department projects
    eng_mgr = {"role": "Department Manager", "department_name": "Engineering"}
    assert rbac.can_create_cross_department_projects(eng_mgr) is False

    sales_mgr = {"role": "Department Manager", "department_name": "Sales"}
    assert rbac.can_create_cross_department_projects(sales_mgr) is False

    hr_admin = {"role": "HR Admin", "department_name": "Human Resources"}
    assert rbac.can_create_cross_department_projects(hr_admin) is False


def test_can_assign_cross_department():
    # Super Admin can assign cross-department
    super_admin = {"role": "Super Admin", "department_name": "Engineering"}
    assert rbac.can_assign_cross_department(super_admin) is True

    # Operations Manager can assign cross-department
    ops_mgr = {"role": "Department Manager", "department_name": "Operations"}
    assert rbac.can_assign_cross_department(ops_mgr) is True

    # Other Department Managers cannot assign cross-department
    eng_mgr = {"role": "Department Manager", "department_name": "Engineering"}
    assert rbac.can_assign_cross_department(eng_mgr) is False

    sales_mgr = {"role": "Department Manager", "department_name": "Sales"}
    assert rbac.can_assign_cross_department(sales_mgr) is False


def test_all_department_managers_can_manage_projects():
    departments = [
        "Engineering",
        "Finance",
        "Operations",
        "Sales",
        "Marketing",
        "Customer Success",
        "Supply Chain",
        "Research & Development",
    ]
    for dept in departments:
        mgr = {"role": "Department Manager", "department_name": dept}
        assert rbac.can_manage_projects(mgr) is True, f"{dept} manager should manage projects"
        pages = rbac.allowed_pages(mgr["role"], mgr["department_name"])
        assert "Project Management" in pages, f"{dept} manager should have Project Management page"


def test_analyst_has_read_only_project_management():
    analyst = {"role": "Analyst", "department_name": "Finance"}
    assert rbac.can_manage_projects(analyst) is False
    pages = rbac.allowed_pages(analyst["role"], analyst["department_name"])
    assert "Project Management" in pages
    assert "Performance Reviews" in pages


def test_employee_has_project_management_and_reviews():
    employee = {"role": "Employee", "department_name": "Customer Success"}
    assert rbac.can_manage_projects(employee) is False
    pages = rbac.allowed_pages(employee["role"], employee["department_name"])
    assert "Project Management" in pages
    assert "Performance Reviews" in pages


def test_export_workforce_permissions():
    assert rbac.can_export_workforce({"role": "Super Admin"}) is True
    assert rbac.can_export_workforce({"role": "HR Admin"}) is True
    assert rbac.can_export_workforce({"role": "Department Manager"}) is True
    assert rbac.can_export_workforce({"role": "Analyst"}) is False
    assert rbac.can_export_workforce({"role": "Employee"}) is False


def test_export_salary_permissions():
    # Only Super Admin, HR Admin, and Finance Dept Manager see salary in exports
    assert rbac.can_export_salary({"role": "Super Admin"}) is True
    assert rbac.can_export_salary({"role": "HR Admin"}) is True
    assert rbac.can_export_salary({"role": "Department Manager", "department_name": "Finance"}) is True
    assert rbac.can_export_salary({"role": "Department Manager", "department_name": "Engineering"}) is False
    assert rbac.can_export_salary({"role": "Analyst"}) is False
    assert rbac.can_export_salary({"role": "Employee"}) is False


def test_export_projects_and_reviews_permissions():
    assert rbac.can_export_projects({"role": "Super Admin"}) is True
    assert rbac.can_export_projects({"role": "Department Manager"}) is True
    assert rbac.can_export_projects({"role": "Analyst"}) is True
    assert rbac.can_export_projects({"role": "Employee"}) is False

    assert rbac.can_export_reviews({"role": "Super Admin"}) is True
    assert rbac.can_export_reviews({"role": "HR Admin"}) is True
    assert rbac.can_export_reviews({"role": "Department Manager"}) is True
    assert rbac.can_export_reviews({"role": "Employee"}) is False


def test_can_view_timeline():
    assert rbac.can_view_timeline({"role": "Super Admin"}) is True
    assert rbac.can_view_timeline({"role": "Department Manager"}) is True
    assert rbac.can_view_timeline({"role": "Analyst"}) is True
    assert rbac.can_view_timeline({"role": "Employee"}) is False

