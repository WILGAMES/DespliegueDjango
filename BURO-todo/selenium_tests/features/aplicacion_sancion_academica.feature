# Feature: Aplicación de sanción académica
# Casos de prueba: TC-14 a TC-18
# Rol: Profesor | Modal en: /cases/academic-action/form/<case_id>/
# La sanción se envía como form POST estándar; la validación de checkbox
# y selects vacíos la hace el navegador (HTML5 required).

Feature: Aplicación de sanción académica

  Scenario: TC-14 Sanción aplicada exitosamente con todos los datos válidos
    Given el usuario está autenticado como Profesor
    And existe un caso activo con estudiantes disponibles para sancionar
    When el usuario navega al formulario de acción académica del caso
    And el usuario hace click en el botón 'Reasignar como sanción'
    Then el modal de sanción académica aparece en pantalla
    When el usuario selecciona un estudiante del dropdown
    And el usuario ingresa el motivo 'Entrevista deficiente por falta de preparación'
    And el usuario marca el checkbox de confirmación de responsabilidad
    And el usuario hace click en 'Aplicar sanción'
    Then el sistema muestra un modal de confirmación de éxito
    And la sanción queda registrada en el historial del caso de forma inmutable

  Scenario: TC-15 Sanción fallida por estudiante no seleccionado
    Given el usuario está autenticado como Profesor
    And existe un caso activo con estudiantes disponibles para sancionar
    And el modal de sanción académica está abierto
    When el usuario no selecciona ningún estudiante del dropdown
    And el usuario ingresa un motivo válido
    And el usuario marca el checkbox de confirmación
    And el usuario hace click en 'Aplicar sanción'
    Then el sistema muestra error de campo requerido en el selector de estudiante
    And la sanción no es registrada en el sistema

  Scenario: TC-16 Sanción fallida por campo de motivo vacío
    Given el usuario está autenticado como Profesor
    And existe un caso activo con estudiantes disponibles para sancionar
    And el modal de sanción académica está abierto
    When el usuario selecciona un estudiante válido del dropdown
    And el usuario deja el campo de motivo vacío
    And el usuario marca el checkbox de confirmación
    And el usuario hace click en 'Aplicar sanción'
    Then el sistema muestra error de campo requerido en el motivo
    And la sanción no es registrada en el sistema

  Scenario: TC-17 Sanción fallida por checkbox de confirmación sin marcar
    Given el usuario está autenticado como Profesor
    And existe un caso activo con estudiantes disponibles para sancionar
    And el modal de sanción académica está abierto
    When el usuario selecciona un estudiante válido del dropdown
    And el usuario ingresa un motivo válido
    And el usuario NO marca el checkbox de confirmación
    And el usuario hace click en 'Aplicar sanción'
    Then el formulario no es enviado al servidor
    And el sistema indica que el checkbox de confirmación es requerido

  Scenario: TC-18 Modal de sanción se cierra sin aplicar cambios
    Given el usuario está autenticado como Profesor
    And existe un caso activo con estudiantes disponibles para sancionar
    And el usuario está en el formulario de acción académica de un caso
    When el usuario hace click en el botón 'Reasignar como sanción'
    Then el modal de sanción académica aparece en pantalla
    When el usuario hace click en el botón de cerrar o en 'Cancelar'
    Then el modal se cierra correctamente
    And ninguna sanción es aplicada al caso
    And el historial del caso no presenta cambios
