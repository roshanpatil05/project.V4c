CREATE DATABASE IF NOT EXISTS employee_analytics;
USE employee_analytics;

CREATE TABLE IF NOT EXISTS departments (
    department_id INT AUTO_INCREMENT PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    department_id INT NOT NULL,
    job_title VARCHAR(120) NOT NULL,
    hire_date DATE NOT NULL,
    manager_id BIGINT NULL,
    salary DECIMAL(12, 2) NOT NULL,
    performance_score DECIMAL(5, 2) NOT NULL DEFAULT 0,
    attrition_risk TINYINT UNSIGNED NOT NULL DEFAULT 0,
    status ENUM('active', 'inactive') NOT NULL DEFAULT 'active',
    CONSTRAINT fk_employee_department FOREIGN KEY (department_id) REFERENCES departments(department_id),
    CONSTRAINT fk_employee_manager FOREIGN KEY (manager_id) REFERENCES employees(employee_id)
);

CREATE TABLE IF NOT EXISTS projects (
    project_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(160) NOT NULL,
    department_id INT NOT NULL,
    budget DECIMAL(14, 2) NOT NULL DEFAULT 0,
    start_date DATE NULL,
    end_date DATE NULL,
    status ENUM('planned', 'active', 'completed', 'on_hold') NOT NULL DEFAULT 'active',
    CONSTRAINT fk_project_department FOREIGN KEY (department_id) REFERENCES departments(department_id)
);

CREATE TABLE IF NOT EXISTS project_assignments (
    assignment_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    employee_id BIGINT NOT NULL,
    project_id BIGINT NOT NULL,
    allocation_pct DECIMAL(5, 2) NOT NULL DEFAULT 100,
    assigned_date DATE NOT NULL,
    CONSTRAINT fk_assignment_employee FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    CONSTRAINT fk_assignment_project FOREIGN KEY (project_id) REFERENCES projects(project_id),
    CONSTRAINT uq_project_assignment UNIQUE (employee_id, project_id)
);

CREATE TABLE IF NOT EXISTS performance_reviews (
    review_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    employee_id BIGINT NOT NULL,
    review_date DATE NOT NULL,
    manager_id BIGINT NULL,
    overall_score DECIMAL(5, 2) NOT NULL,
    rating VARCHAR(40) NOT NULL,
    comments TEXT NULL,
    CONSTRAINT fk_review_employee FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    CONSTRAINT fk_review_manager FOREIGN KEY (manager_id) REFERENCES employees(employee_id),
    CONSTRAINT chk_review_score CHECK (overall_score BETWEEN 0 AND 100)
);

CREATE TABLE IF NOT EXISTS dim_department (
    department_key INT AUTO_INCREMENT PRIMARY KEY,
    department_id INT NOT NULL UNIQUE,
    department_name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_employee (
    employee_key BIGINT AUTO_INCREMENT PRIMARY KEY,
    employee_id BIGINT NOT NULL,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    email VARCHAR(255) NOT NULL,
    department_key INT NOT NULL,
    job_title VARCHAR(120) NOT NULL,
    hire_date DATE NOT NULL,
    salary DECIMAL(12, 2) NOT NULL,
    performance_score DECIMAL(5, 2) NOT NULL DEFAULT 0,
    attrition_risk TINYINT UNSIGNED NOT NULL DEFAULT 0,
    start_date DATETIME NOT NULL,
    end_date DATETIME NULL,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT fk_dim_employee_department FOREIGN KEY (department_key) REFERENCES dim_department(department_key),
    CONSTRAINT uq_dim_employee_version UNIQUE (employee_id, start_date),
    INDEX ix_dim_employee_asof (employee_id, start_date, end_date, is_current)
);

CREATE TABLE IF NOT EXISTS dim_project (
    project_key BIGINT AUTO_INCREMENT PRIMARY KEY,
    project_id BIGINT NOT NULL UNIQUE,
    project_name VARCHAR(160) NOT NULL,
    department_key INT NOT NULL,
    CONSTRAINT fk_dim_project_department FOREIGN KEY (department_key) REFERENCES dim_department(department_key)
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key INT PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    year_num SMALLINT NOT NULL,
    quarter_num TINYINT NOT NULL,
    month_num TINYINT NOT NULL,
    day_num TINYINT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_performance_reviews (
    fact_review_key BIGINT AUTO_INCREMENT PRIMARY KEY,
    review_id BIGINT NOT NULL UNIQUE,
    employee_key BIGINT NOT NULL,
    employee_id BIGINT NOT NULL,
    department_key INT NOT NULL,
    project_key BIGINT NULL,
    date_key INT NOT NULL,
    review_date DATE NOT NULL,
    overall_score DECIMAL(5, 2) NOT NULL,
    rating VARCHAR(40) NOT NULL,
    CONSTRAINT fk_fact_employee FOREIGN KEY (employee_key) REFERENCES dim_employee(employee_key),
    CONSTRAINT fk_fact_department FOREIGN KEY (department_key) REFERENCES dim_department(department_key),
    CONSTRAINT fk_fact_project FOREIGN KEY (project_key) REFERENCES dim_project(project_key),
    CONSTRAINT fk_fact_date FOREIGN KEY (date_key) REFERENCES dim_date(date_key),
    INDEX ix_fact_review_date (review_date),
    INDEX ix_fact_employee_id (employee_id)
);

-- ============================================================
-- AUTH: user accounts, role rules, and audit log
-- ============================================================

CREATE TABLE IF NOT EXISTS user_accounts (
    account_id    BIGINT AUTO_INCREMENT PRIMARY KEY,
    employee_id   BIGINT NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    -- When set, overrides role_rules resolution entirely.
    -- Only assignable via CLI (setup_auth.py); never from the UI.
    forced_role   VARCHAR(60) NULL DEFAULT NULL,
    last_login    DATETIME NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_account_employee FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- Maps job-title patterns (LIKE syntax) to app user-roles.
-- priority: lower number = checked first (more specific rules win).
-- department_id NULL means "any department".
CREATE TABLE IF NOT EXISTS role_rules (
    rule_id       INT AUTO_INCREMENT PRIMARY KEY,
    title_pattern VARCHAR(120) NOT NULL,
    department_id INT NULL,
    role_name     VARCHAR(60)  NOT NULL,
    priority      INT          NOT NULL DEFAULT 10,
    CONSTRAINT fk_role_rule_department FOREIGN KEY (department_id) REFERENCES departments(department_id)
);

CREATE TABLE IF NOT EXISTS auth_audit_log (
    log_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
    employee_id  BIGINT NULL,
    event_type   ENUM('login_success','login_failed','logout','action') NOT NULL,
    description  VARCHAR(500) NULL,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_audit_employee (employee_id),
    INDEX ix_audit_created  (created_at)
);

-- ============================================================
-- ROLE RULES SEED DATA
-- Run once - safe to re-run (INSERT IGNORE).
-- ============================================================

-- Priority 1: Human Resources department — ALL titles become HR Admin
-- (department_id will be filled by the seed script below — see setup_auth.py)
-- We use a stored procedure so the insert stays portable without hardcoding IDs.

DROP PROCEDURE IF EXISTS sp_seed_role_rules;
DELIMITER $$
CREATE PROCEDURE sp_seed_role_rules()
BEGIN
    DECLARE hr_dept_id INT DEFAULT NULL;

    SELECT department_id INTO hr_dept_id
    FROM   departments
    WHERE  department_name = 'Human Resources'
    LIMIT  1;

    -- Clear existing rules so this is idempotent
    DELETE FROM role_rules;

    -- P1: Entire HR department → HR Admin (cross-dept access)
    IF hr_dept_id IS NOT NULL THEN
        INSERT INTO role_rules (title_pattern, department_id, role_name, priority)
        VALUES ('%', hr_dept_id, 'HR Admin', 1);
    END IF;

    -- P5: Director titles (any dept) → Department Manager
    INSERT INTO role_rules (title_pattern, department_id, role_name, priority)
    VALUES ('%Director%', NULL, 'Department Manager', 5);

    -- P10: Manager titles (any dept) → Department Manager
    INSERT INTO role_rules (title_pattern, department_id, role_name, priority)
    VALUES ('%Manager%', NULL, 'Department Manager', 10);

    -- P20: Analyst titles → Analyst (read-only analytics)
    INSERT INTO role_rules (title_pattern, department_id, role_name, priority)
    VALUES ('%Analyst%', NULL, 'Analyst', 20);

    -- P20: Controller (Finance) → Analyst
    INSERT INTO role_rules (title_pattern, department_id, role_name, priority)
    VALUES ('Controller', NULL, 'Analyst', 20);

    -- P20: Project Coordinator → Analyst (sees bottleneck dashboard)
    INSERT INTO role_rules (title_pattern, department_id, role_name, priority)
    VALUES ('Project Coordinator', NULL, 'Analyst', 20);

    -- P99: Catch-all → Employee (Overview + own reviews only)
    INSERT INTO role_rules (title_pattern, department_id, role_name, priority)
    VALUES ('%', NULL, 'Employee', 99);
END$$
DELIMITER ;

CALL sp_seed_role_rules();

DROP PROCEDURE IF EXISTS sp_close_employee_scd2_version;
DELIMITER $$
CREATE PROCEDURE sp_close_employee_scd2_version(
    IN p_employee_id BIGINT,
    IN p_effective_date DATE
)
BEGIN
    UPDATE dim_employee
    SET end_date = p_effective_date, is_current = FALSE
    WHERE employee_id = p_employee_id AND is_current = TRUE;
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS sp_etl_dim_date;
DELIMITER $$
CREATE PROCEDURE sp_etl_dim_date()
BEGIN
    INSERT INTO dim_date (date_key, full_date, year_num, quarter_num, month_num, day_num)
    SELECT DISTINCT YEAR(review_date) * 10000 + MONTH(review_date) * 100 + DAY(review_date),
           review_date, YEAR(review_date), QUARTER(review_date),
           MONTH(review_date), DAY(review_date)
    FROM performance_reviews
    ON DUPLICATE KEY UPDATE full_date = VALUES(full_date);
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS sp_etl_dim_project;
DELIMITER $$
CREATE PROCEDURE sp_etl_dim_project()
BEGIN
    INSERT INTO dim_project (project_id, project_name, department_key)
    SELECT p.project_id, p.project_name, d.department_key
    FROM projects p
    JOIN departments source_department ON source_department.department_id = p.department_id
    JOIN dim_department d ON d.department_id = source_department.department_id
    ON DUPLICATE KEY UPDATE project_name = VALUES(project_name),
                            department_key = VALUES(department_key);
END$$
DELIMITER ;

DROP PROCEDURE IF EXISTS sp_etl_fact_reviews;
DELIMITER $$
CREATE PROCEDURE sp_etl_fact_reviews()
BEGIN
    INSERT INTO fact_performance_reviews (
        review_id, employee_key, employee_id, department_key, project_key,
        date_key, review_date, overall_score, rating
    )
    WITH ranked_assignments AS (
        SELECT pr.review_id, pa.project_id,
               ROW_NUMBER() OVER (
                   PARTITION BY pr.review_id ORDER BY pa.assigned_date DESC, pa.assignment_id DESC
               ) AS assignment_rank
        FROM performance_reviews pr
        LEFT JOIN project_assignments pa
          ON pa.employee_id = pr.employee_id AND pa.assigned_date <= pr.review_date
    )
    SELECT pr.review_id, e.employee_key, pr.employee_id, e.department_key,
           dp.project_key,
           YEAR(pr.review_date) * 10000 + MONTH(pr.review_date) * 100 + DAY(pr.review_date),
           pr.review_date, pr.overall_score, pr.rating
    FROM performance_reviews pr
    JOIN dim_employee e
      ON e.employee_id = pr.employee_id
     AND pr.review_date >= e.start_date
     AND (e.end_date IS NULL OR pr.review_date < e.end_date)
    LEFT JOIN ranked_assignments ra
      ON ra.review_id = pr.review_id AND ra.assignment_rank = 1
    LEFT JOIN dim_project dp ON dp.project_id = ra.project_id
    ON DUPLICATE KEY UPDATE employee_key = VALUES(employee_key),
                            department_key = VALUES(department_key),
                            project_key = VALUES(project_key),
                            overall_score = VALUES(overall_score), rating = VALUES(rating);
END$$
DELIMITER ;
