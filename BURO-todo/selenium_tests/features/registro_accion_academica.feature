# Feature: Registro de acción académica
# Casos de prueba: TC-06 a TC-13
# Rol: Profesor | URL: /cases/academic-action/form/<case_id>/
# Nota: la acción se envía vía fetch (JS), los errores aparecen en #error-msg

Feature: Registro de acción académica

  Scenario: TC-06 Registro exitoso con tipo válido y nota en rango
    Given el usuario está autenticado como Profesor
    And existe un caso activo con un estudiante asignado al profesor
    When el usuario navega al formulario de acción académica del caso
    And el usuario selecciona el tipo de acción 'Entrega de documento'
    And el usuario ingresa la nota '4.5'
    And el usuario ingresa la observación 'El estudiante entregó todos los documentos'
    And el usuario hace click en 'Registrar acción'
    Then la acción aparece en el historial del caso
    And la nota parcial acumulada es recalculada y actualizada en pantalla

  Scenario: TC-07 Registro exitoso con nota en límite mínimo 0.0
    Given el usuario está autenticado como Profesor
    And existe un caso activo disponible
    When el usuario navega al formulario de acción académica del caso
    And el usuario selecciona el tipo de acción 'Seguimiento'
    And el usuario ingresa la nota '0.0'
    And el usuario hace click en 'Registrar acción'
    Then la acción es guardada exitosamente con nota 0.0
    And aparece en el historial del caso

  Scenario: TC-08 Registro exitoso con nota en límite máximo 5.0
    Given el usuario está autenticado como Profesor
    And existe un caso activo disponible
    When el usuario navega al formulario de acción académica del caso
    And el usuario selecciona el tipo de acción 'Seguimiento'
    And el usuario ingresa la nota '5.0'
    And el usuario hace click en 'Registrar acción'
    Then la acción es guardada exitosamente con nota 5.0
    And aparece en el historial del caso

  Scenario: TC-09 Registro fallido por nota negativa
    Given el usuario está autenticado como Profesor
    And existe un caso activo disponible
    When el usuario navega al formulario de acción académica del caso
    And el usuario selecciona el tipo de acción 'Entrega de documento'
    And el usuario ingresa la nota '-1.0'
    And el usuario hace click en 'Registrar acción'
    Then el sistema muestra el mensaje 'La nota debe estar entre 0.0 y 5.0'
    And la acción no es guardada en el sistema

  Scenario: TC-10 Registro fallido por nota superior al máximo
    Given el usuario está autenticado como Profesor
    And existe un caso activo disponible
    When el usuario navega al formulario de acción académica del caso
    And el usuario selecciona el tipo de acción 'Seguimiento'
    And el usuario ingresa la nota '5.1'
    And el usuario hace click en 'Registrar acción'
    Then el sistema muestra el mensaje 'La nota debe estar entre 0.0 y 5.0'
    And la acción no es guardada en el sistema

  Scenario: TC-11 Registro fallido por tipo de acción no seleccionado
    Given el usuario está autenticado como Profesor
    And existe un caso activo disponible
    When el usuario navega al formulario de acción académica del caso
    And el usuario no selecciona ningún tipo de acción
    And el usuario ingresa la nota '4.0'
    And el usuario hace click en 'Registrar acción'
    Then el sistema muestra el mensaje 'Seleccione un tipo de acción'
    And la acción no es guardada en el sistema

  Scenario: TC-12 Registro fallido por campo de nota vacío
    Given el usuario está autenticado como Profesor
    And existe un caso activo disponible
    When el usuario navega al formulario de acción académica del caso
    And el usuario selecciona el tipo de acción 'Seguimiento'
    And el usuario deja el campo de nota vacío
    And el usuario hace click en 'Registrar acción'
    Then el sistema muestra el mensaje 'Ingrese una nota entre 0.0 y 5.0'
    And la acción no es guardada en el sistema

  Scenario: TC-13 Registro exitoso de asistencia a cita con datos adicionales
    Given el usuario está autenticado como Profesor
    And existe un caso activo disponible
    When el usuario navega al formulario de acción académica del caso
    And el usuario selecciona el tipo de acción 'Asistencia a cita'
    Then el sistema muestra la sección adicional de datos de asistencia
    When el usuario marca que el estudiante asistió con valor 'Sí'
    And el usuario ingresa la hora de llegada '09:30'
    And el usuario ingresa la nota '4.0'
    And el usuario hace click en 'Registrar acción'
    Then la acción es guardada con los datos de asistencia incluidos
    And el historial del caso muestra el tipo 'Asistencia a cita'
