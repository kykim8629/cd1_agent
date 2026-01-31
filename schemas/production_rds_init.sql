-- =============================================================================
-- CD1 Agent - Production RDS Initialization Script
-- =============================================================================
-- Version: 1.0.0
-- Compatible with: MySQL 8.0+, Amazon RDS MySQL
-- Database: cd1_agent
--
-- Tables (9):
--   1. hitl_requests          - HITL 승인 요청 (공통)
--   2. detection_patterns     - BDP 탐지 패턴 정의
--   3. logs                   - BDP 애플리케이션 로그
--   4. auth_logs              - BDP 인증 로그
--   5. slow_query_log         - BDP 슬로우 쿼리
--   6. detection_results      - BDP 탐지 결과
--   7. drift_baselines        - Drift 설정 기준선
--   8. drift_baseline_history - Drift 기준선 변경 이력
--   9. drift_detection_results- Drift 탐지 결과
--
-- Triggers (3): drift_baselines INSERT/UPDATE/DELETE 자동 이력 기록
-- Views (3): v_baselines_summary, v_recent_changes, v_unresolved_drifts
-- =============================================================================

CREATE DATABASE IF NOT EXISTS cd1_agent
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE cd1_agent;


-- =============================================================================
-- Section 1: HITL (Human-in-the-Loop) 공통 테이블
-- =============================================================================
-- 모든 에이전트(cost, bdp, hdsp, drift)가 공유하는 승인 요청 테이블.
-- Critical 수준 이상 탐지 시 사람의 승인을 받기 위해 사용.

CREATE TABLE IF NOT EXISTS hitl_requests (
    -- Primary identifier
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID v4 format',

    -- Request classification
    agent_type ENUM('cost', 'bdp', 'hdsp', 'drift') NOT NULL COMMENT 'Agent type that created the request',
    request_type VARCHAR(50) NOT NULL COMMENT 'Type of HITL request',
    status ENUM('pending', 'approved', 'rejected', 'expired', 'cancelled') DEFAULT 'pending' COMMENT 'Current request status',

    -- Request content
    title VARCHAR(255) NOT NULL COMMENT 'Human-readable title',
    description TEXT COMMENT 'Detailed description of the request',
    payload JSON NOT NULL COMMENT 'Request payload with agent-specific data',
    response JSON COMMENT 'Response data after approval/rejection',

    -- Timestamps (UTC)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Request creation time',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update time',
    expires_at TIMESTAMP NOT NULL COMMENT 'Request expiration time',

    -- Audit fields
    created_by VARCHAR(100) COMMENT 'System/user that created the request',
    responded_by VARCHAR(100) COMMENT 'User that responded to the request',

    -- Indexes for common queries
    INDEX idx_status (status),
    INDEX idx_agent_status (agent_type, status),
    INDEX idx_expires (expires_at),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- Section 2: BDP (Big Data Platform) 에이전트 테이블
-- =============================================================================
-- 로그 이상 탐지를 위한 테이블들.
-- 탐지 패턴 정의, 로그 저장, 탐지 결과 기록.

-- 2-1. Detection patterns table (탐지 패턴 정의)
CREATE TABLE IF NOT EXISTS detection_patterns (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pattern_id VARCHAR(64) NOT NULL UNIQUE,
    pattern_name VARCHAR(255) NOT NULL,
    pattern_type ENUM('auth_failure', 'exception', 'timeout', 'resource_exhaustion', 'security') NOT NULL,
    regex_pattern TEXT NOT NULL,
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL DEFAULT 'medium',
    threshold INT NOT NULL DEFAULT 5,
    time_window_minutes INT NOT NULL DEFAULT 60,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_pattern_type (pattern_type),
    INDEX idx_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2-2. Application logs table (애플리케이션 로그)
CREATE TABLE IF NOT EXISTS logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    service_name VARCHAR(128) NOT NULL,
    log_level ENUM('DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL') NOT NULL,
    message TEXT NOT NULL,
    context JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_timestamp (timestamp),
    INDEX idx_service (service_name),
    INDEX idx_level (log_level),
    INDEX idx_service_level_time (service_name, log_level, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2-3. Authentication logs table (인증 로그)
CREATE TABLE IF NOT EXISTS auth_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    username VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    success BOOLEAN NOT NULL,
    failure_reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_timestamp (timestamp),
    INDEX idx_username (username),
    INDEX idx_success (success),
    INDEX idx_failure_time (success, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2-4. Slow query log table (슬로우 쿼리 로그)
CREATE TABLE IF NOT EXISTS slow_query_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    query_hash VARCHAR(64) NOT NULL,
    query_text TEXT NOT NULL,
    execution_time_ms INT NOT NULL,
    rows_examined BIGINT,
    rows_returned BIGINT,
    database_name VARCHAR(128),
    user_host VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_timestamp (timestamp),
    INDEX idx_execution_time (execution_time_ms),
    INDEX idx_query_hash (query_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2-5. Detection results table (탐지 결과)
CREATE TABLE IF NOT EXISTS detection_results (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    detection_id VARCHAR(64) NOT NULL UNIQUE,
    detection_type ENUM('log_anomaly', 'metric_anomaly', 'pattern_anomaly') NOT NULL,
    severity ENUM('low', 'medium', 'high', 'critical') NOT NULL,
    service_name VARCHAR(128),
    pattern_id VARCHAR(64),
    anomaly_details JSON NOT NULL,
    detected_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP,
    resolution_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_detection_type (detection_type),
    INDEX idx_severity (severity),
    INDEX idx_detected_at (detected_at),
    INDEX idx_service (service_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- Section 3: Drift 에이전트 테이블
-- =============================================================================
-- AWS 리소스 설정 변경(drift) 감지를 위한 테이블들.
-- 기준선 저장, 변경 이력, 탐지 결과 기록.

-- 3-1. Drift baselines table (설정 기준선)
CREATE TABLE IF NOT EXISTS drift_baselines (
    -- Composite Primary Key
    resource_type VARCHAR(50) NOT NULL COMMENT 'Resource type (glue, athena, emr, etc.)',
    resource_id VARCHAR(255) NOT NULL COMMENT 'Resource identifier',

    -- Version Information
    version INT NOT NULL DEFAULT 1 COMMENT 'Current version number',

    -- Baseline Configuration (JSON)
    config JSON NOT NULL COMMENT 'Expected configuration as JSON',
    config_hash VARCHAR(64) NOT NULL COMMENT 'SHA256 hash for change detection',

    -- Metadata
    resource_arn VARCHAR(512) COMMENT 'Full AWS ARN of the resource',
    description TEXT COMMENT 'Human-readable description',
    tags JSON COMMENT 'Resource tags as JSON',

    -- Timestamps (UTC)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update time',

    -- Audit Fields
    created_by VARCHAR(100) COMMENT 'User/system that created the baseline',
    updated_by VARCHAR(100) COMMENT 'User/system that last updated the baseline',

    -- Primary Key
    PRIMARY KEY (resource_type, resource_id),

    -- Indexes for Common Queries
    INDEX idx_resource_type (resource_type),
    INDEX idx_updated_at (updated_at),
    INDEX idx_config_hash (config_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3-2. Drift baseline history table (기준선 변경 이력)
CREATE TABLE IF NOT EXISTS drift_baseline_history (
    -- Primary Key
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID v4 format',

    -- Resource Identification
    resource_type VARCHAR(50) NOT NULL COMMENT 'Resource type',
    resource_id VARCHAR(255) NOT NULL COMMENT 'Resource identifier',

    -- Version Information
    version INT NOT NULL COMMENT 'Version number at time of change',

    -- Change Type
    change_type ENUM('CREATE', 'UPDATE', 'DELETE') NOT NULL COMMENT 'Type of change',

    -- Configuration Diff
    previous_config JSON COMMENT 'Configuration before change (NULL for CREATE)',
    current_config JSON NOT NULL COMMENT 'Configuration after change',
    config_hash VARCHAR(64) NOT NULL COMMENT 'Hash of current config',

    -- Change Metadata
    change_reason TEXT COMMENT 'Why was this change made?',

    -- Timestamp
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'When the change occurred',

    -- Audit
    changed_by VARCHAR(100) NOT NULL COMMENT 'Who made this change',

    -- Indexes
    INDEX idx_resource (resource_type, resource_id),
    INDEX idx_resource_version (resource_type, resource_id, version),
    INDEX idx_changed_at (changed_at),
    INDEX idx_changed_by (changed_by),
    INDEX idx_change_type (change_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3-3. Drift detection results table (드리프트 탐지 결과)
CREATE TABLE IF NOT EXISTS drift_detection_results (
    -- Primary Key
    id VARCHAR(36) PRIMARY KEY COMMENT 'UUID v4 format',

    -- Detection Context
    detection_run_id VARCHAR(36) NOT NULL COMMENT 'ID of the detection run',
    resource_type VARCHAR(50) NOT NULL COMMENT 'Resource type',
    resource_id VARCHAR(255) NOT NULL COMMENT 'Resource identifier',

    -- Detection Result
    has_drift BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Whether drift was detected',
    severity ENUM('critical', 'high', 'medium', 'low') COMMENT 'Drift severity',

    -- Configuration Comparison
    baseline_config JSON NOT NULL COMMENT 'Expected configuration',
    current_config JSON NOT NULL COMMENT 'Actual current configuration',
    drift_details JSON COMMENT 'Detailed drift information',

    -- Timestamps
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT 'Detection time',

    -- Resolution
    resolved_at TIMESTAMP COMMENT 'When drift was resolved',
    resolved_by VARCHAR(100) COMMENT 'Who resolved the drift',
    resolution_action ENUM('updated_baseline', 'reverted_resource', 'ignored', 'auto_resolved') COMMENT 'How it was resolved',
    resolution_notes TEXT COMMENT 'Notes about resolution',

    -- Indexes
    INDEX idx_detection_run (detection_run_id),
    INDEX idx_resource (resource_type, resource_id),
    INDEX idx_has_drift (has_drift),
    INDEX idx_severity (severity),
    INDEX idx_detected_at (detected_at),
    INDEX idx_unresolved (has_drift, resolved_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =============================================================================
-- Section 4: Drift 트리거 (기준선 변경 시 자동 이력 기록)
-- =============================================================================

DELIMITER //

-- Trigger: INSERT 시 이력 기록
CREATE TRIGGER drift_baselines_after_insert
AFTER INSERT ON drift_baselines
FOR EACH ROW
BEGIN
    INSERT INTO drift_baseline_history (
        id,
        resource_type,
        resource_id,
        version,
        change_type,
        previous_config,
        current_config,
        config_hash,
        change_reason,
        changed_by
    ) VALUES (
        UUID(),
        NEW.resource_type,
        NEW.resource_id,
        NEW.version,
        'CREATE',
        NULL,
        NEW.config,
        NEW.config_hash,
        'Initial baseline creation',
        COALESCE(NEW.created_by, 'system')
    );
END//

-- Trigger: UPDATE 시 이력 기록 (config 변경된 경우만)
CREATE TRIGGER drift_baselines_after_update
AFTER UPDATE ON drift_baselines
FOR EACH ROW
BEGIN
    IF OLD.config_hash != NEW.config_hash THEN
        INSERT INTO drift_baseline_history (
            id,
            resource_type,
            resource_id,
            version,
            change_type,
            previous_config,
            current_config,
            config_hash,
            changed_by
        ) VALUES (
            UUID(),
            NEW.resource_type,
            NEW.resource_id,
            NEW.version,
            'UPDATE',
            OLD.config,
            NEW.config,
            NEW.config_hash,
            COALESCE(NEW.updated_by, 'system')
        );
    END IF;
END//

-- Trigger: DELETE 시 이력 기록
CREATE TRIGGER drift_baselines_after_delete
AFTER DELETE ON drift_baselines
FOR EACH ROW
BEGIN
    INSERT INTO drift_baseline_history (
        id,
        resource_type,
        resource_id,
        version,
        change_type,
        previous_config,
        current_config,
        config_hash,
        changed_by
    ) VALUES (
        UUID(),
        OLD.resource_type,
        OLD.resource_id,
        OLD.version + 1,
        'DELETE',
        OLD.config,
        JSON_OBJECT('_deleted', true, '_deleted_at', NOW()),
        OLD.config_hash,
        'system'
    );
END//

DELIMITER ;


-- =============================================================================
-- Section 5: Drift 뷰
-- =============================================================================

-- View: 기준선 요약 (버전 수 포함)
CREATE OR REPLACE VIEW v_baselines_summary AS
SELECT
    b.resource_type,
    b.resource_id,
    b.version,
    b.config_hash,
    b.updated_at,
    b.updated_by,
    (SELECT COUNT(*) FROM drift_baseline_history h
     WHERE h.resource_type = b.resource_type
     AND h.resource_id = b.resource_id) as total_versions
FROM drift_baselines b;

-- View: 최근 변경 (7일 이내)
CREATE OR REPLACE VIEW v_recent_changes AS
SELECT
    h.id,
    h.resource_type,
    h.resource_id,
    h.version,
    h.change_type,
    h.changed_at,
    h.changed_by,
    h.change_reason
FROM drift_baseline_history h
WHERE h.changed_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
ORDER BY h.changed_at DESC;

-- View: 미해결 드리프트
CREATE OR REPLACE VIEW v_unresolved_drifts AS
SELECT
    d.id,
    d.resource_type,
    d.resource_id,
    d.severity,
    d.detected_at,
    d.drift_details,
    TIMESTAMPDIFF(HOUR, d.detected_at, NOW()) as hours_unresolved
FROM drift_detection_results d
WHERE d.has_drift = TRUE
AND d.resolved_at IS NULL
ORDER BY
    FIELD(d.severity, 'critical', 'high', 'medium', 'low'),
    d.detected_at ASC;


-- =============================================================================
-- Section 6: Seed 데이터 (선택 사항)
-- =============================================================================
-- 필요 시 아래 주석을 해제하고 실행하세요.
-- detection_patterns 초기 패턴 17개 + 샘플 로그 데이터

-- -- Auth failure patterns
-- INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
-- ('auth_failed_login', 'Failed Login Attempts', 'auth_failure',
--  '(Failed login|Authentication failed|Invalid credentials|Login attempt failed)',
--  'high', 5, 30, 'Detects multiple failed login attempts'),
-- ('auth_account_lockout', 'Account Lockout', 'auth_failure',
--  '(Account locked|Too many failed attempts|User account disabled)',
--  'critical', 3, 60, 'Detects account lockout events'),
-- ('auth_invalid_token', 'Invalid Token Access', 'auth_failure',
--  '(Invalid token|Token expired|JWT validation failed|Unauthorized access)',
--  'high', 10, 15, 'Detects invalid token access attempts');

-- -- Exception patterns
-- INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
-- ('exc_null_pointer', 'NullPointerException', 'exception',
--  '(NullPointerException|null reference|NoneType)',
--  'medium', 5, 30, 'Detects null pointer exceptions'),
-- ('exc_out_of_memory', 'OutOfMemoryError', 'exception',
--  '(OutOfMemory|heap space|memory exhausted|OOM)',
--  'critical', 1, 60, 'Detects out of memory errors'),
-- ('exc_stack_overflow', 'StackOverflow', 'exception',
--  '(StackOverflow|stack depth exceeded|recursive call)',
--  'high', 3, 30, 'Detects stack overflow errors'),
-- ('exc_general', 'General Exception', 'exception',
--  '(Exception:|Error:|FATAL:|CRITICAL:)',
--  'medium', 10, 15, 'Detects general exceptions and errors');

-- -- Timeout patterns
-- INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
-- ('timeout_connection', 'Connection Timeout', 'timeout',
--  '(Connection timeout|connection timed out|connect timeout|ConnectTimeoutException)',
--  'high', 5, 30, 'Detects connection timeout errors'),
-- ('timeout_read', 'Read Timeout', 'timeout',
--  '(Read timeout|read timed out|socket timeout|SocketTimeoutException)',
--  'high', 5, 30, 'Detects read timeout errors'),
-- ('timeout_db', 'Database Timeout', 'timeout',
--  '(Database timeout|query timeout|Lock wait timeout|deadlock)',
--  'critical', 3, 30, 'Detects database timeout errors');

-- -- Resource exhaustion patterns
-- INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
-- ('res_conn_pool', 'Connection Pool Exhausted', 'resource_exhaustion',
--  '(Connection pool exhausted|no available connections|pool size exceeded)',
--  'critical', 3, 30, 'Detects connection pool exhaustion'),
-- ('res_disk_full', 'Disk Space Full', 'resource_exhaustion',
--  '(No space left|disk full|storage quota exceeded)',
--  'critical', 1, 60, 'Detects disk space issues'),
-- ('res_thread_pool', 'Thread Pool Exhausted', 'resource_exhaustion',
--  '(Thread pool exhausted|no available threads|task rejected)',
--  'high', 5, 30, 'Detects thread pool exhaustion');

-- -- Security patterns
-- INSERT INTO detection_patterns (pattern_id, pattern_name, pattern_type, regex_pattern, severity, threshold, time_window_minutes, description) VALUES
-- ('sec_sql_injection', 'SQL Injection Attempt', 'security',
--  '(SQL injection|sqlmap|union select|OR 1=1)',
--  'critical', 1, 60, 'Detects SQL injection attempts'),
-- ('sec_xss_attempt', 'XSS Attempt', 'security',
--  '(<script>|javascript:|onerror=|onload=)',
--  'high', 3, 30, 'Detects XSS attempts'),
-- ('sec_path_traversal', 'Path Traversal Attempt', 'security',
--  '(\\.\\./|%2e%2e%2f|directory traversal)',
--  'high', 3, 30, 'Detects path traversal attempts');

-- -- Sample baseline logs
-- INSERT INTO logs (service_name, log_level, message, context) VALUES
-- ('auth-service', 'INFO', 'Service started successfully', '{"version": "1.0.0"}'),
-- ('auth-service', 'INFO', 'Health check passed', '{"status": "healthy"}'),
-- ('api-gateway', 'INFO', 'Request processed', '{"latency_ms": 50}'),
-- ('api-gateway', 'INFO', 'Cache hit', '{"cache_key": "user_123"}'),
-- ('data-processor', 'INFO', 'Batch job completed', '{"records": 1000}');

-- -- Sample auth logs
-- INSERT INTO auth_logs (username, ip_address, success, failure_reason) VALUES
-- ('user@example.com', '192.168.1.1', TRUE, NULL),
-- ('admin@example.com', '192.168.1.2', TRUE, NULL),
-- ('test@example.com', '192.168.1.3', TRUE, NULL);
