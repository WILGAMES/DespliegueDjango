-- DML de ejemplo para el proyecto BURO-todo
-- Llena datos mínimos para pruebas de roles, usuarios, casos y calificaciones.

BEGIN;

-- Roles
INSERT INTO rol (id, name, description) VALUES
(1, 'admin', 'Administrador del sistema'),
(2, 'profesor', 'Profesor asesor'),
(3, 'student', 'Estudiante del programa'),
(4, 'secretaria', 'Secretaria administrativa');

-- Salas jurídicas
INSERT INTO sala_juridica (id, name, description) VALUES
(1, 'Civil', 'Sala jurídica de derecho civil'),
(2, 'Laboral', 'Sala jurídica de derecho laboral');

-- Usuarios del sistema
INSERT INTO usuario_sistema (id, password, last_login, is_superuser, name, email, document, phone, role_id, room_id, is_active, is_staff, otp_enabled) VALUES
(1, 'pbkdf2_sha256$260000$dummy$dummyhash', NOW(), TRUE, 'Admin Global', 'admin@example.com', '1000000000', '+573001112233', 1, NULL, TRUE, TRUE, FALSE),
(2, 'pbkdf2_sha256$260000$dummy$dummyhash', NOW(), FALSE, 'Carolina Pérez', 'carolina.perez@example.com', '1010001001', '+573002223344', 2, 2, TRUE, FALSE, FALSE),
(3, 'pbkdf2_sha256$260000$dummy$dummyhash', NOW(), FALSE, 'Juan Estudiante', 'juan.estudiante@example.com', '1020002002', '+573003334455', 3, 2, TRUE, FALSE, FALSE),
(4, 'pbkdf2_sha256$260000$dummy$dummyhash', NOW(), FALSE, 'Ana Secretaría', 'ana.secretaria@example.com', '1030003003', '+573004445566', 4, 2, TRUE, FALSE, FALSE);

-- Perfiles especialistas
INSERT INTO profesor (id, user_id, specialization) VALUES
(1, 2, 'Derecho Laboral');

INSERT INTO estudiante (id, user_id, semester, student_code, status) VALUES
(1, 3, 3, 'STU1020', 'active');

INSERT INTO secretaria (id, user_id) VALUES
(1, 4);

-- Beneficiarios
INSERT INTO beneficiario (id, name, document, email, phone, address, date_of_birth, stratum, data_authorization) VALUES
(1, 'María Gómez', '1070004004', 'maria.gomez@example.com', '+573005556677', 'Calle 123 #45-67', '2002-04-10', 3, TRUE);

-- Casos académicos
INSERT INTO caso (id, number, description, beneficiary_id, assigned_student_id, student_id, professor_id, room_id, legal_deadline, status, created_at) VALUES
(1, 'C-2026-001', 'Caso laboral de asesoría formativa', 1, 3, 1, 1, 2, '2026-06-30', 'active', NOW());

-- Configuraciones de pesos
INSERT INTO configuracion_pesos (id, professor_id, room_id, period, weight_documents, weight_followups, weight_attendance) VALUES
(1, 1, 2, '2026-1', 50, 30, 20);

-- Permisos
INSERT INTO permission (id, resource, action) VALUES
(1, 'case', 'assign'),
(2, 'academic_action', 'create'),
(3, 'academic_action', 'view');

INSERT INTO rol_permiso (id, role_id, permission_id) VALUES
(1, 2, 2),
(2, 2, 3),
(3, 4, 1);

-- Acciones académicas
INSERT INTO accion_academica (id, case_id, action_type, grade, observation, registered_by_id, registered_at, status, attended, arrival_time, document_delivered) VALUES
(1, 1, 'document', 4.5, 'Entrega inicial de documento con apoyo del profesor.', 1, NOW(), 'ACTIVE', FALSE, NULL, FALSE);

-- Trazabilidad de acciones académicas
INSERT INTO trazabilidad_registro_academico (id, academic_action_id, modified_by_id, field_name, old_value, new_value, event_type, created_at) VALUES
(1, 1, 2, 'grade', '4.0', '4.5', 'UPDATE', NOW());

-- Bitácora del sistema (ejemplo de intento bloquedo)
INSERT INTO bitacora_sistema (id, user_id, created_at, action_attempted, record_id, result) VALUES
(1, 2, NOW(), 'DELETE_ACADEMIC_ACTION', '1', 'BLOCKED');

-- Bitácora de casos
INSERT INTO bitacora_caso (id, case_id, event_type, description, executed_by_id, created_at) VALUES
(1, 1, 'asignacion', 'Caso asignado al estudiante Juan Estudiante.', 4, NOW());

-- Citas y reprogramación
INSERT INTO cita (id, case_id, scheduled_datetime, modality, location_or_link, created_by_id, status, reminder_sent, created_at) VALUES
(1, 1, '2026-05-28 09:00:00+00', 'presencial', 'Sala 101', 4, 'programada', FALSE, NOW());

INSERT INTO bitacora_cita (id, appointment_id, changed_by_id, previous_datetime, new_datetime, reason, no_reason_flag, changed_at) VALUES
(1, 1, 1, '2026-05-28 09:00:00+00', '2026-05-29 10:00:00+00', 'Cambio autorizado por disponibilidad.', FALSE, NOW());

-- Comunicaciones
INSERT INTO bitacora_comunicacion (id, case_id, sent_by_id, recipients, subject, body, status, sent_at) VALUES
(1, 1, 3, '["juan.estudiante@example.com"]', 'Recordatorio de entrega', 'Hola Juan, recuerda entregar el documento antes del plazo.', 'enviado', NOW());

-- Notificaciones fallidas
INSERT INTO notificacion_fallida (id, "to", subject, body, error_message, failed_at, resolved) VALUES
(1, 'juan.estudiante@example.com', 'Recordatorio de entrega', 'No se pudo enviar el recordatorio.', 'SMTP connection timed out', NOW(), FALSE);

-- Reportes académicos
INSERT INTO reporte_academico (id, period_label, date_from, date_to, generated_at, generated_by_id, is_automatic, status, report_data) VALUES
(1, '2026-1', '2026-01-01', '2026-06-30', NOW(), 1, FALSE, 'completed', '{"summary": "Reporte inicial de calificaciones"}');

-- Solicitud de eliminación de datos
INSERT INTO solicitud_eliminacion (id, beneficiary_id, requested_at, status, reason, processed_at, processed_by_id, rejection_reason) VALUES
(1, 1, NOW(), 'Pendiente', 'Solicito eliminación de mis datos personales.', NULL, NULL, '');

COMMIT;
