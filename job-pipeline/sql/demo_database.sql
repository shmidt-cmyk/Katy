CREATE DATABASE IF NOT EXISTS hh_automation_test
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE hh_automation_test;

CREATE TABLE IF NOT EXISTS jobpipe_vacancies (
    id INT NOT NULL AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    employer_name VARCHAR(255) NOT NULL DEFAULT '',
    city VARCHAR(120) NULL,
    url VARCHAR(512) NOT NULL,
    description LONGTEXT NULL,
    salary VARCHAR(255) NOT NULL DEFAULT '',
    source VARCHAR(32) NOT NULL DEFAULT 'manual',
    status VARCHAR(40) NOT NULL DEFAULT 'new',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_jobpipe_vacancy_url (url),
    KEY idx_jobpipe_vacancy_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS jobpipe_letters (
    id INT NOT NULL AUTO_INCREMENT,
    vacancy_id INT NOT NULL,
    letter_text LONGTEXT NOT NULL,
    model_name VARCHAR(64) NOT NULL DEFAULT 'gemini-2.0-flash',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_jobpipe_letters_vacancy (vacancy_id),
    CONSTRAINT fk_jobpipe_letters_vacancy FOREIGN KEY (vacancy_id)
        REFERENCES jobpipe_vacancies (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS jobpipe_application_events (
    id INT NOT NULL AUTO_INCREMENT,
    vacancy_id INT NOT NULL,
    status VARCHAR(40) NOT NULL,
    note TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_jobpipe_events_vacancy_time (vacancy_id, created_at),
    KEY idx_jobpipe_events_status (status),
    CONSTRAINT fk_jobpipe_events_vacancy FOREIGN KEY (vacancy_id)
        REFERENCES jobpipe_vacancies (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO jobpipe_vacancies
    (title, employer_name, city, url, description, salary, source, status)
VALUES
    (
        'ДЕМО: Системный аналитик',
        'Учебная компания «Пример»',
        'Москва',
        'https://example.invalid/vacancy/demo-system-analyst',
        'Демонстрационная вакансия. Нужно собирать и анализировать требования, описывать бизнес-процессы и готовить постановки для разработки. Это тестовые данные, вакансия не существует.',
        'от 180 000 ₽',
        'manual',
        'new'
    ),
    (
        'ДЕМО: Бизнес-аналитик',
        'Тестовая организация',
        'Удалённо',
        'https://example.invalid/vacancy/demo-business-analyst',
        'Демонстрационная вакансия. Предстоит описывать процессы в BPMN, взаимодействовать с заказчиками и проверять требования. Это тестовые данные, вакансия не существует.',
        'по договорённости',
        'manual',
        'new'
    ),
    (
        'ДЕМО: Координатор проекта',
        'Демо-команда',
        'Санкт-Петербург',
        'https://example.invalid/vacancy/demo-project-coordinator',
        'Демонстрационная вакансия. Требуется помогать команде планировать задачи, фиксировать договорённости и отслеживать сроки. Это тестовые данные, вакансия не существует.',
        'от 150 000 ₽',
        'manual',
        'new'
    );
