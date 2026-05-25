# Feature: Registro de caso nuevo
# Casos de prueba: TC-01 a TC-05
# Rol: Secretaria | URL: /accounts/cases/new/

Feature: Registro de caso nuevo

  Scenario: TC-01 Registro exitoso con todos los campos válidos
    Given el usuario está autenticado como Secretaria
    And existe al menos un beneficiario registrado en el sistema
    And existe al menos una sala jurídica registrada en el sistema
    When el usuario navega a /accounts/cases/new/
    And el usuario ingresa el número de caso 'CASO-2026-TEST'
    And el usuario selecciona un beneficiario de la lista
    And el usuario ingresa la descripción 'Caso de arrendamiento vivienda'
    And el usuario selecciona una sala jurídica de la lista
    And el usuario ingresa la fecha límite '2026-12-31'
    And el usuario hace click en 'Registrar caso'
    Then el sistema redirige a la lista de casos
    And el caso 'CASO-2026-TEST' aparece con estado 'Pendiente'

  Scenario: TC-02 Registro fallido por número de caso duplicado
    Given el usuario está autenticado como Secretaria
    And existe un caso con número 'CASO-2026-001' en el sistema
    When el usuario navega a /accounts/cases/new/
    And el usuario ingresa el número de caso 'CASO-2026-001'
    And el usuario completa el resto de campos con datos válidos
    And el usuario hace click en 'Registrar caso'
    Then el sistema permanece en el formulario
    And se muestra un error indicando que el número de caso ya existe

  Scenario: TC-03 Registro fallido por campos obligatorios vacíos
    Given el usuario está autenticado como Secretaria
    When el usuario navega a /accounts/cases/new/
    And el usuario no ingresa ningún dato en el formulario
    And el usuario hace click en 'Registrar caso'
    Then el sistema muestra mensajes de error en los campos obligatorios
    And el caso no es creado en el sistema

  Scenario: TC-04 Registro fallido por fecha límite en el pasado
    Given el usuario está autenticado como Secretaria
    When el usuario navega a /accounts/cases/new/
    And el usuario completa todos los campos con datos válidos
    And el usuario ingresa la fecha límite '2020-01-01'
    And el usuario hace click en 'Registrar caso'
    Then el sistema muestra un error de validación en el campo de fecha
    And el caso no es creado en el sistema

  Scenario: TC-05 Registro fallido por sala jurídica no seleccionada
    Given el usuario está autenticado como Secretaria
    When el usuario navega a /accounts/cases/new/
    And el usuario completa todos los campos con datos válidos excepto sala jurídica
    And el usuario hace click en 'Registrar caso'
    Then el sistema muestra error de campo requerido en sala jurídica
    And el caso no es creado en el sistema
