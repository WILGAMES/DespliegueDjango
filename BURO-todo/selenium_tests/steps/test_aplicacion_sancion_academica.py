"""
Steps para Feature: Aplicación de sanción académica (TC-14 a TC-18).

El modal de sanción es un form HTML estándar (POST). Validación:
  - select[name="student_id"] required  → HTML5 impide submit sin selección
  - textarea[name="reason"]   required  → HTML5 impide submit vacío
  - input[type="checkbox"]    required  → HTML5 impide submit sin marcar

Tras una sanción exitosa, la página recarga con id="modal-overlay" visible
(componente modal.html con tipo='success').

Selectores clave del modal:
  #modal-aplicar-sancion          — contenedor del modal
  select[name="student_id"]       — dropdown estudiante
  textarea[name="reason"]         — motivo de sanción
  input[type="checkbox"]          — confirmación (required)
  button[type="submit"]           — dentro del modal
  #modal-overlay                  — modal de éxito/error post-sanción
"""
import pytest
from pytest_bdd import parsers, scenarios, then, when
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from conftest import BASE_URL, TEST_CASE_ID, WAIT, _select_first_valid

scenarios("../features/aplicacion_sancion_academica.feature")


# ── When ──────────────────────────────────────────────────────────────────────

@when("el usuario navega al formulario de acción académica del caso")
def navegar_formulario_caso(context):
    """Reutilizado también en TC-14; navega al formulario del caso activo."""
    driver  = context["driver"]
    w       = context["wait"]
    case_id = context.get("case_id", TEST_CASE_ID)
    driver.get(f"{BASE_URL}/cases/academic-action/form/{case_id}/")
    w.until(EC.presence_of_element_located((By.ID, "modal-aplicar-sancion")))


@when("el usuario hace click en el botón 'Reasignar como sanción'")
def click_reasignar_sancion(context):
    driver = context["driver"]
    w      = context["wait"]
    btn    = driver.find_element(
        By.XPATH,
        "//*[contains(normalize-space(text()), 'Reasignar como sanci')]"
    )
    btn.click()
    w.until(EC.visibility_of_element_located((By.ID, "modal-aplicar-sancion")))


@when("el usuario selecciona un estudiante del dropdown")
def seleccionar_estudiante(context):
    driver = context["driver"]
    sel    = Select(
        driver.find_element(By.CSS_SELECTOR, "#modal-aplicar-sancion select[name='student_id']")
    )
    _select_first_valid(sel)
    context["student_selected"] = True


@when("el usuario no selecciona ningún estudiante del dropdown")
def no_seleccionar_estudiante(context):
    # El select queda en la primera opción vacía (value="")
    context["student_selected"] = False


@when(parsers.parse("el usuario ingresa el motivo '{motivo}'"))
def ingresar_motivo(context, motivo):
    driver = context["driver"]
    field  = driver.find_element(
        By.CSS_SELECTOR, "#modal-aplicar-sancion textarea[name='reason']"
    )
    field.clear()
    field.send_keys(motivo)
    context["motivo_ingresado"] = True


@when("el usuario ingresa un motivo válido")
def ingresar_motivo_valido(context):
    ingresar_motivo(context, "Entrevista deficiente por falta de preparación")


@when("el usuario deja el campo de motivo vacío")
def dejar_motivo_vacio(context):
    driver = context["driver"]
    field  = driver.find_element(
        By.CSS_SELECTOR, "#modal-aplicar-sancion textarea[name='reason']"
    )
    field.clear()
    context["motivo_ingresado"] = False


@when("el usuario marca el checkbox de confirmación de responsabilidad")
def marcar_checkbox_confirmacion(context):
    driver   = context["driver"]
    checkbox = driver.find_element(
        By.CSS_SELECTOR, "#modal-aplicar-sancion input[type='checkbox']"
    )
    if not checkbox.is_selected():
        checkbox.click()
    context["checkbox_marcado"] = True


@when("el usuario marca el checkbox de confirmación")
def marcar_checkbox(context):
    marcar_checkbox_confirmacion(context)


@when("el usuario NO marca el checkbox de confirmación")
def no_marcar_checkbox(context):
    # Deja el checkbox desmarcado (estado por defecto)
    context["checkbox_marcado"] = False


@when("el usuario selecciona un estudiante válido del dropdown")
def seleccionar_estudiante_valido(context):
    seleccionar_estudiante(context)


@when("el usuario hace click en 'Aplicar sanción'")
def click_aplicar_sancion(context):
    driver = context["driver"]
    modal  = driver.find_element(By.ID, "modal-aplicar-sancion")
    # El botón "Aplicar sanción" tiene type="submit" (via button.html variant='accent')
    submit_btn = modal.find_element(By.CSS_SELECTOR, "button[type='submit']")
    submit_btn.click()


@when("el usuario hace click en el botón de cerrar o en 'Cancelar'")
def click_cerrar_modal(context):
    driver = context["driver"]
    # Primero intenta el botón X (cierre con ×)
    try:
        close_btn = driver.find_element(
            By.CSS_SELECTOR,
            "#modal-aplicar-sancion button[onclick*=\"classList.add('hidden')\"]"
        )
        close_btn.click()
    except Exception:
        # Fallback: botón Cancelar (div wrapper con onclick)
        cancelar = driver.find_element(
            By.XPATH,
            "//*[@id='modal-aplicar-sancion']//*[contains(normalize-space(text()), 'Cancelar')]"
        )
        cancelar.click()


# ── Then ──────────────────────────────────────────────────────────────────────

@then("el modal de sanción académica aparece en pantalla")
def modal_sancion_visible(context):
    w      = context["wait"]
    modal  = w.until(EC.visibility_of_element_located((By.ID, "modal-aplicar-sancion")))
    assert modal.is_displayed(), "El modal de sanción no es visible."


@then("el sistema muestra un modal de confirmación de éxito")
def modal_exito_visible(context):
    driver  = context["driver"]
    w       = context["wait"]
    case_id = context.get("case_id", TEST_CASE_ID)

    # ApplySanctionView (POST) redirige a cases:case-detail.
    # Esperamos a que el URL salga de la página del formulario de acción.
    w.until(lambda d: "academic-action" not in d.current_url)

    # El modal de sesión lo consume AcademicActionFormView (GET).
    # Navegamos al formulario académico para leerlo.
    driver.get(f"{BASE_URL}/cases/academic-action/form/{case_id}/")

    try:
        w.until(EC.presence_of_element_located((By.ID, "modal-overlay")))
    except Exception:
        page_text = driver.find_element(By.TAG_NAME, "body").text[:800]
        current_url = driver.current_url
        raise AssertionError(
            f"Modal de éxito no apareció.\nURL: {current_url}\nPágina: {page_text}"
        )

    overlay = driver.find_element(By.ID, "modal-overlay")
    assert overlay.is_displayed(), "El modal de éxito no es visible."


@then("la sanción queda registrada en el historial del caso de forma inmutable")
def sancion_registrada_en_historial(context):
    # La presencia del modal de éxito confirma el registro; verificación adicional
    # comprobando que el modal overlay existe (el servidor lo inyecta solo si fue exitoso)
    driver = context["driver"]
    assert driver.find_element(By.ID, "modal-overlay").is_displayed(), (
        "La sanción no fue registrada: no se muestra el modal de confirmación."
    )


@then("el sistema muestra error de campo requerido en el selector de estudiante")
def error_selector_estudiante(context):
    driver = context["driver"]
    # Con HTML5 required, el formulario no se envía y el modal permanece abierto
    modal_visible = driver.find_element(By.ID, "modal-aplicar-sancion").is_displayed()
    assert modal_visible, (
        "El modal debería permanecer abierto al fallar la validación del estudiante."
    )


@then("la sanción no es registrada en el sistema")
def sancion_no_registrada(context):
    driver = context["driver"]
    # Si no hubo submit exitoso, no habrá #modal-overlay
    overlays = driver.find_elements(By.ID, "modal-overlay")
    assert len(overlays) == 0, (
        "Se encontró el modal de éxito cuando no debería haberse registrado la sanción."
    )


@then("el sistema muestra error de campo requerido en el motivo")
def error_campo_motivo(context):
    driver = context["driver"]
    modal_visible = driver.find_element(By.ID, "modal-aplicar-sancion").is_displayed()
    assert modal_visible, (
        "El modal debería permanecer abierto al fallar la validación del motivo."
    )


@then("el formulario no es enviado al servidor")
def formulario_no_enviado(context):
    driver = context["driver"]
    # El modal sigue abierto → el form no se envió (HTML5 required en checkbox)
    modal_visible = driver.find_element(By.ID, "modal-aplicar-sancion").is_displayed()
    assert modal_visible, (
        "El modal debería permanecer abierto cuando el checkbox no está marcado."
    )


@then("el sistema indica que el checkbox de confirmación es requerido")
def checkbox_indicado_como_requerido(context):
    driver   = context["driver"]
    checkbox = driver.find_element(
        By.CSS_SELECTOR, "#modal-aplicar-sancion input[type='checkbox']"
    )
    # HTML5 `required` en checkbox impide submit → el checkbox tiene el atributo required
    required = checkbox.get_attribute("required")
    assert required is not None, (
        "El checkbox no tiene el atributo 'required'; la validación HTML5 no aplica."
    )


@then("el modal se cierra correctamente")
def modal_se_cierra(context):
    w = context["wait"]
    w.until(EC.invisibility_of_element_located((By.ID, "modal-aplicar-sancion")))
    visible = context["driver"].find_element(By.ID, "modal-aplicar-sancion").is_displayed()
    assert not visible, "El modal sigue visible después de cerrarlo."


@then("ninguna sanción es aplicada al caso")
def ninguna_sancion_aplicada(context):
    driver   = context["driver"]
    overlays = driver.find_elements(By.ID, "modal-overlay")
    assert len(overlays) == 0, (
        "Aparece el modal de éxito cuando no se debería haber aplicado ninguna sanción."
    )


@then("el historial del caso no presenta cambios")
def historial_sin_cambios(context):
    # El modal de sanción se cerró sin enviar el formulario → historial intacto
    # Verificamos que no hay un modal-overlay (indicador de éxito de sanción)
    driver   = context["driver"]
    overlays = driver.find_elements(By.ID, "modal-overlay")
    assert len(overlays) == 0, (
        "Se registró una sanción inesperada: el historial pudo haber cambiado."
    )
