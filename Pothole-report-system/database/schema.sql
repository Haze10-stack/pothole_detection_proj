CREATE DATABASE IF NOT EXISTS pothole_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pothole_db;

CREATE TABLE custom_user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL UNIQUE,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    phone_number VARCHAR(15),
    password_hash VARCHAR(255) NOT NULL,
    credits INT DEFAULT 0,
    is_staff BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_username (username),
    INDEX idx_email (email)
);

CREATE TABLE pothole_report (
    id INT AUTO_INCREMENT PRIMARY KEY,
    report_id VARCHAR(36) NOT NULL UNIQUE,
    user_id VARCHAR(36) NOT NULL,
    image_url VARCHAR(500),
    s3_bucket_path VARCHAR(300),
    description TEXT,
    location_name VARCHAR(200),
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    severity ENUM('LOW', 'MEDIUM', 'HIGH', 'CRITICAL') NOT NULL,
    status ENUM('PENDING', 'VERIFIED', 'REJECTED', 'IN_PROGRESS', 'COMPLETED') DEFAULT 'PENDING',
    credits_awarded INT DEFAULT 5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES custom_user(user_id) ON DELETE CASCADE,
    INDEX idx_report_id (report_id),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status),
    INDEX idx_severity (severity),
    INDEX idx_created_at (created_at),
    INDEX idx_location (latitude, longitude)
);

CREATE TABLE municipal_verification (
    id INT AUTO_INCREMENT PRIMARY KEY,
    report_id VARCHAR(36) NOT NULL,
    verified_by VARCHAR(100),
    verification_status ENUM('APPROVED', 'REJECTED', 'NEED_INFO'),
    verification_notes TEXT,
    verification_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    estimated_repair_date DATE,
    FOREIGN KEY (report_id) REFERENCES pothole_report(report_id) ON DELETE CASCADE,
    INDEX idx_report_id (report_id),
    INDEX idx_verification_date (verification_date)
);

INSERT INTO custom_user (user_id, username, email, password_hash, is_staff, credits) VALUES
(UUID(), 'municipal_admin', 'admin@municipal.gov', 'pbkdf2:sha256:260000$salt$hash', TRUE, 0);

INSERT INTO custom_user (user_id, username, email, password_hash, is_staff, credits) VALUES
(UUID(), 'john_doe', 'john@example.com', 'pbkdf2:sha256:260000$salt$hash', FALSE, 15);

INSERT INTO pothole_report (
    report_id, user_id, image_url, s3_bucket_path, description, 
    location_name, latitude, longitude, severity, status
) VALUES 
(
    UUID(), 
    (SELECT user_id FROM custom_user WHERE username = 'john_doe'), 
    'https://your-bucket.s3.amazonaws.com/pothole-images/sample1.jpg',
    'pothole-images/sample1.jpg',
    'Large pothole causing vehicle damage on main street',
    'Main Street near City Hall',
    40.7128,
    -74.0060,
    'HIGH',
    'PENDING'
),
(
    UUID(), 
    (SELECT user_id FROM custom_user WHERE username = 'john_doe'), 
    'https://your-bucket.s3.amazonaws.com/pothole-images/sample2.jpg',
    'pothole-images/sample2.jpg',
    'Small pothole but growing larger after recent rain',
    'Oak Avenue intersection',
    40.7500,
    -73.9850,
    'MEDIUM',
    'VERIFIED'
);

CREATE VIEW report_summary AS
SELECT 
    u.username,
    u.email,
    COUNT(p.id) as total_reports,
    SUM(CASE WHEN p.status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_reports,
    SUM(p.credits_awarded) as total_credits,
    MAX(p.created_at) as last_report_date
FROM custom_user u
LEFT JOIN pothole_report p ON u.user_id = p.user_id
WHERE u.is_staff = FALSE
GROUP BY u.user_id, u.username, u.email;

CREATE VIEW status_analytics AS
SELECT 
    status,
    severity,
    COUNT(*) as count,
    AVG(credits_awarded) as avg_credits,
    DATE(created_at) as report_date
FROM pothole_report
GROUP BY status, severity, DATE(created_at)
ORDER BY report_date DESC;

DELIMITER //
CREATE PROCEDURE AwardCredits(
    IN p_user_id VARCHAR(36),
    IN p_credits INT,
    IN p_reason VARCHAR(100)
)
BEGIN
    UPDATE custom_user 
    SET credits = credits + p_credits 
    WHERE user_id = p_user_id;
END //
DELIMITER ;

DELIMITER //
CREATE TRIGGER update_credits_on_status_change
AFTER UPDATE ON pothole_report
FOR EACH ROW
BEGIN
    IF OLD.status != NEW.status THEN
        CASE NEW.status
            WHEN 'VERIFIED' THEN
                UPDATE custom_user 
                SET credits = credits + 10 
                WHERE user_id = NEW.user_id;
            WHEN 'COMPLETED' THEN
                UPDATE custom_user 
                SET credits = credits + 5 
                WHERE user_id = NEW.user_id;
        END CASE;
    END IF;
END //
DELIMITER ;