-- Initialize databases and users for finance-data-agent
CREATE DATABASE IF NOT EXISTS `dw` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `meta` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'atguigu'@'%' IDENTIFIED BY 'Atguigu.123';
GRANT ALL PRIVILEGES ON `dw`.* TO 'atguigu'@'%';
GRANT ALL PRIVILEGES ON `meta`.* TO 'atguigu'@'%';
FLUSH PRIVILEGES;
