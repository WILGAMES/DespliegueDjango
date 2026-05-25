-- DDL para el proyecto BURO-todo
-- Basado en los modelos Django encontrados en accounts/models.py, cases/models.py, notifications/models.py, reports/models.py

-- TABLA: sala_juridica
CREATE TABLE sala_juridica (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(200)
);

-- TABLA: rol
CREATE TABLE rol (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(200)
);

-- TABLA: usuario_sistema
CREATE TABLE usuario_sistema (
    id SERIAL PRIMARY KEY,
    password VARCHAR(128) NOT NULL,
    last_login TIMESTAMP WITH TIME ZONE,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    document VARCHAR(50) UNIQUE,
    phone VARCHAR(20),
    role_id INTEGER REFERENCES rol(id) ON DELETE PROTECT,
    room_id INTEGER REFERENCES sala_juridica(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    otp_enabled BOOLEAN NOT NULL DEFAULT FALSE
);

-- TABLA: estudiante
CREATE TABLE estudiante (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES usuario_sistema(id) ON DELETE CASCADE,
    semester INTEGER NOT NULL DEFAULT 1,
    student_code VARCHAR(7) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
);

-- TABLA: profesor
CREATE TABLE profesor (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES usuario_sistema(id) ON DELETE CASCADE,
    specialization VARCHAR(100) NOT NULL DEFAULT ''
);

-- TABLA: secretaria
CREATE TABLE secretaria (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES usuario_sistema(id) ON DELETE CASCADE
);

-- TABLA: permission
CREATE TABLE permission (
    id SERIAL PRIMARY KEY,
    resource VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    UNIQUE(resource, action)
);

-- TABLA: rol_permiso
CREATE TABLE rol_permiso (
    id SERIAL PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES rol(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permission(id) ON DELETE CASCADE,
    UNIQUE(role_id, permission_id)
);

-- TABLA: bitacora_roles
CREATE TABLE bitacora_roles (
    id SERIAL PRIMARY KEY,
    "user_id" INTEGER NOT NULL REFERENCES usuario_sistema(id) ON DELETE CASCADE,
    old_role_id INTEGER NOT NULL REFERENCES rol(id) ON DELETE PROTECT,
    new_role_id INTEGER NOT NULL REFERENCES rol(id) ON DELETE PROTECT,
    changed_by_id INTEGER NOT NULL REFERENCES usuario_sistema(id) ON DELETE PROTECT,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- TABLA: beneficiario
CREATE TABLE beneficiario (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    document VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(254) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL,
    address VARCHAR(100) NOT NULL,
    date_of_birth DATE,
    stratum INTEGER NOT NULL CHECK (stratum >= 1 AND stratum <= 4),
    photo BYTEA,
    digital_signature BYTEA,
    fingerprint_hash VARCHAR(200) NOT NULL DEFAULT '',
    data_authorization BOOLEAN NOT NULL DEFAULT FALSE,
    registration_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- TABLA: solicitud_eliminacion
CREATE TABLE solicitud_eliminacion (
    id SERIAL PRIMARY KEY,
    beneficiary_id INTEGER NOT NULL REFERENCES beneficiario(id) ON DELETE CASCADE,
    requested_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'Pendiente',
    reason TEXT NOT NULL DEFAULT '',
    processed_at TIMESTAMP WITH TIME ZONE,
    processed_by_id INTEGER REFERENCES usuario_sistema(id) ON DELETE PROTECT,
    rejection_reason TEXT NOT NULL DEFAULT ''
);

-- TABLA: otp_code
CREATE TABLE otp_code (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES usuario_sistema(id) ON DELETE CASCADE,
    code VARCHAR(6) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    is_used BOOLEAN NOT NULL DEFAULT FALSE
);

-- TABLA: caso
CREATE TABLE caso (
    id SERIAL PRIMARY KEY,
    number VARCHAR(20) UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    beneficiary_id INTEGER REFERENCES beneficiario(id) ON DELETE CASCADE,
    assigned_student_id INTEGER REFERENCES usuario_sistema(id) ON DELETE SET NULL,
    student_id INTEGER REFERENCES estudiante(id) ON DELETE PROTECT,
    professor_id INTEGER NOT NULL REFERENCES profesor(id) ON DELETE PROTECT,
    room_id INTEGER NOT NULL REFERENCES sala_juridica(id) ON DELETE PROTECT,
    legal_deadline DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- TABLA: configuracion_pesos
CREATE TABLE configuracion_pesos (
    id SERIAL PRIMARY KEY,
    professor_id INTEGER NOT NULL REFERENCES profesor(id) ON DELETE PROTECT,
    room_id INTEGER NOT NULL REFERENCES sala_juridica(id) ON DELETE PROTECT,
    period VARCHAR(20) NOT NULL,
    weight_documents INTEGER NOT NULL,
    weight_followups INTEGER NOT NULL,
    weight_attendance INTEGER NOT NULL,
    UNIQUE(professor_id, room_id, period)
);

-- TABLA: criterios_asignacion
CREATE TABLE criterios_asignacion (
    id SERIAL PRIMARY KEY,
    max_cases_per_professor INTEGER NOT NULL CHECK (max_cases_per_professor >= 1),
    prioritize_same_room BOOLEAN NOT NULL DEFAULT TRUE,
    balance_workload BOOLEAN NOT NULL DEFAULT TRUE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_active_assignment_criteria UNIQUE (active) WHERE (active = TRUE)
);

-- TABLA: bitacora_criterios_asignacion
CREATE TABLE bitacora_criterios_asignacion (
    id SERIAL PRIMARY KEY,
    criteria_id INTEGER NOT NULL REFERENCES criterios_asignacion(id) ON DELETE CASCADE,
    changed_by_id INTEGER NOT NULL REFERENCES usuario_sistema(id) ON DELETE PROTECT,
    field_name VARCHAR(100) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- TABLA: bitacora_asignacion_automatica
CREATE TABLE bitacora_asignacion_automatica (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES caso(id) ON DELETE PROTECT,
    student_id INTEGER REFERENCES estudiante(id) ON DELETE PROTECT,
    assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    assignment_reason TEXT NOT NULL,
    created_by_system BOOLEAN NOT NULL DEFAULT TRUE
);

-- TABLA: accion_academica
CREATE TABLE accion_academica (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES caso(id) ON DELETE PROTECT,
    action_type VARCHAR(20) NOT NULL,
    grade NUMERIC(3,1) NOT NULL CHECK (grade >= 0.0 AND grade <= 5.0),
    observation TEXT NOT NULL DEFAULT '',
    registered_by_id INTEGER NOT NULL REFERENCES profesor(id) ON DELETE PROTECT,
    registered_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    attended BOOLEAN,
    arrival_time TIME,
    document_delivered BOOLEAN
);

-- TABLA: trazabilidad_registro_academico
CREATE TABLE trazabilidad_registro_academico (
    id SERIAL PRIMARY KEY,
    academic_action_id INTEGER NOT NULL REFERENCES accion_academica(id) ON DELETE PROTECT,
    modified_by_id INTEGER NOT NULL REFERENCES usuario_sistema(id) ON DELETE PROTECT,
    field_name VARCHAR(100) NOT NULL,
    old_value TEXT NOT NULL DEFAULT '',
    new_value TEXT NOT NULL DEFAULT '',
    event_type VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- TABLA: bitacora_sistema
CREATE TABLE bitacora_sistema (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES usuario_sistema(id) ON DELETE PROTECT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    action_attempted VARCHAR(100) NOT NULL,
    record_id VARCHAR(100) NOT NULL,
    result VARCHAR(20) NOT NULL
);

-- TABLA: bitacora_caso
CREATE TABLE bitacora_caso (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES caso(id) ON DELETE PROTECT,
    event_type VARCHAR(30) NOT NULL,
    description TEXT NOT NULL,
    executed_by_id INTEGER REFERENCES usuario_sistema(id) ON DELETE PROTECT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- TABLA: cita
CREATE TABLE cita (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES caso(id) ON DELETE PROTECT,
    scheduled_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    modality VARCHAR(20) NOT NULL,
    location_or_link VARCHAR(255) NOT NULL DEFAULT '',
    created_by_id INTEGER NOT NULL REFERENCES usuario_sistema(id) ON DELETE PROTECT,
    status VARCHAR(20) NOT NULL DEFAULT 'programada',
    reminder_sent BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- TABLA: bitacora_cita
CREATE TABLE bitacora_cita (
    id SERIAL PRIMARY KEY,
    appointment_id INTEGER NOT NULL REFERENCES cita(id) ON DELETE PROTECT,
    changed_by_id INTEGER NOT NULL REFERENCES usuario_sistema(id) ON DELETE PROTECT,
    previous_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    new_datetime TIMESTAMP WITH TIME ZONE NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    no_reason_flag BOOLEAN NOT NULL DEFAULT FALSE,
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- TABLA: bitacora_comunicacion
CREATE TABLE bitacora_comunicacion (
    id SERIAL PRIMARY KEY,
    case_id INTEGER NOT NULL REFERENCES caso(id) ON DELETE PROTECT,
    sent_by_id INTEGER NOT NULL REFERENCES usuario_sistema(id) ON DELETE PROTECT,
    recipients JSONB NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(10) NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- TABLA: notificacion_fallida
CREATE TABLE notificacion_fallida (
    id SERIAL PRIMARY KEY,
    "to" VARCHAR(254) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    error_message TEXT NOT NULL,
    failed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- TABLA: reporte_academico
CREATE TABLE reporte_academico (
    id SERIAL PRIMARY KEY,
    period_label VARCHAR(50) NOT NULL,
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    generated_by_id INTEGER REFERENCES usuario_sistema(id) ON DELETE SET NULL,
    is_automatic BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    report_data JSONB NOT NULL DEFAULT '{}'::jsonb
);
