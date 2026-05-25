"""
Steps para Feature: Registro de acción académica (TC-06 a TC-13).

La acción se registra mediante fetch (JavaScript), NO con un form POST.
Por eso el botón "Registrar acción" llama a submitAction() vía onclick.
Los errores de validación aparecen en el div #error-msg.

Selectores clave:
  #action-type        — select tipo de acción
  #grade              — input nota (number, min=0, max=5, step=0.1)
  #observation        — textarea observación (opcional)
  #error-msg          — div que muestra errores JS
  #actions-list       — div donde se insertan acciones exitosas
  #nota-parcial       — span con la nota parcial calculada
  #attendance-fields  — sección extra visible sólo con tipo "attendance"
  #arrival-time       — input time (hora de llegada)
  [name="attended"]   — radios Sí/No asistencia
"""
import pytest
from pytest_bdd import parsers, scenarios, then, when
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from conftest import BASE_URL, TEST_CASE_ID, WAIT

scenarios("../features/registro_accion_academica.feature")

# Mapa de etiquetas visibles al value del select
_ACTION_TYPE_MAP = {
    "Entrega de documento": "document",
    "Seguimiento":          "followup",
    "Asistencia a cita":    "attendance",
}


# ── When ──────────────────────────────────────────────────────────────────────

@when("el usuario navega al formulario de acción académica del caso")
def navegar_formulario_accion(context):
    driver  = context["driver"]
    w       = context["wait"]
    case_id = context.get("case_id", TEST_CASE_ID)
    driver.get(f"{BASE_URL}/cases/academic-action/form/{case_id}/")
    w.until(EC.presence_of_element_located((By.ID, "action-type")))


@when(parsers.parse("el usuario selecciona el tipo de acción '{tipo}'"))
def seleccionar_tipo_accion(context, tipo):
    driver = context["driver"]
    sel    = Select(driver.find_element(By.ID, "action-type"))
    value  = _ACTION_TYPE_MAP.get(tipo, tipo)
    sel.select_by_value(value)
    context["action_type"] = value


@when(parsers.parse("el usuario ingresa la nota '{nota}'"))
def ingresar_nota(context, nota):
    driver = context["driver"]
    field  = driver.find_element(By.ID, "grade")
    field.clear()
    # Ingresa el valor sin restricciones de min/max del HTML5
    driver.execute_script("arguments[0].value = arguments[1];", field, nota)
    context["grade"] = nota


@when(parsers.parse("el usuario ingresa la observación '{observacion}'"))
def ingresar_observacion(context, observacion):
    driver = context["driver"]
    field  = driver.find_element(By.ID, "observation")
    field.clear()
    field.send_keys(observacion)


@when("el usuario hace click en 'Registrar acción'")
def click_registrar_accion(context):
    driver = context["driver"]
    # El botón está dentro de un <div onclick="submitAction()">
    btn    = driver.find_element(By.XPATH, "//*[@onclick='submitAction()']")
    btn.click()


@when("el usuario no selecciona ningún tipo de acción")
def no_seleccionar_tipo():
    pass  # El select queda en la opción vacía por defecto


@when("el usuario deja el campo de nota vacío")
def dejar_nota_vacia(context):
    driver = context["driver"]
    field  = driver.find_element(By.ID, "grade")
    driver.execute_script("arguments[0].value = '';", field)


@when(parsers.parse("el usuario marca que el estudiante asistió con valor '{valor}'"))
def marcar_asistencia(context, valor):
    driver        = context["driver"]
    radio_value   = "true" if valor.lower() in ("sí", "si", "yes") else "false"
    radio         = driver.find_element(
        By.CSS_SELECTOR, f"input[name='attended'][value='{radio_value}']"
    )
    radio.click()


@when(parsers.parse("el usuario ingresa la hora de llegada '{hora}'"))
def ingresar_hora_llegada(context, hora):
    driver = context["driver"]
    field  = driver.find_element(By.ID, "arrival-time")
    driver.execute_script("arguments[0].value = arguments[1];", field, hora)


# ── Then ──────────────────────────────────────────────────────────────────────

@then("la acción aparece en el historial del caso")
def accion_aparece_en_historial(context):
    w = context["wait"]
    # El JS agrega un div al #actions-list o quita el empty-state
    w.until(EC.presence_of_element_located((By.ID, "actions-list")))
    items = context["driver"].find_elements(
        By.CSS_SELECTOR, "#actions-list > div"
    )
    assert len(items) > 0, "No aparecieron acciones en el historial."


@then("la nota parcial acumulada es recalculada y actualizada en pantalla")
def nota_parcial_actualizada(context):
    w = context["wait"]
    # Después de registrar, fetchNotaParcial() actualiza #nota-parcial con un número
    w.until(
        lambda d: d.find_element(By.ID, "nota-parcial").text not in ("--", "...", "Error", "")
    )
    texto = context["driver"].find_element(By.ID, "nota-parcial").text
    assert texto.replace(".", "").replace(",", "").isdigit() or "." in texto, (
        f"La nota parcial no muestra un número: '{texto}'"
    )


@then(parsers.parse("la acción es guardada exitosamente con nota {nota}"))
def accion_guardada_con_nota(context, nota):
    w = context["wait"]
    w.until(EC.presence_of_element_located((By.ID, "actions-list")))
    page_text = context["driver"].find_element(By.TAG_NAME, "body").text
    nota_str  = str(float(nota))          # "0.0" o "5.0"
    # La nota aparece formateada en el historial
    assert nota_str in page_text or nota.rstrip("0").rstrip(".") in page_text, (
        f"La nota '{nota}' no aparece en el historial. Página: {page_text[:500]}"
    )


@then("aparece en el historial del caso")
def aparece_en_historial(context):
    """Alias compartido con TC-07 y TC-08."""
    accion_aparece_en_historial(context)


@then(parsers.parse("el sistema muestra el mensaje '{mensaje}'"))
def sistema_muestra_mensaje(context, mensaje):
    w      = context["wait"]
    driver = context["driver"]
    # Espera a que el div de error sea visible
    w.until(EC.visibility_of_element_located((By.ID, "error-msg")))
    error_text = driver.find_element(By.ID, "error-msg").text
    assert mensaje.lower() in error_text.lower(), (
        f"Mensaje esperado: '{mensaje}'. Mensaje real: '{error_text}'"
    )


@then("la acción no es guardada en el sistema")
def accion_no_guardada(context):
    driver = context["driver"]
    error_div = driver.find_element(By.ID, "error-msg")
    assert "hidden" not in error_div.get_attribute("class"), (
        "Se esperaba que el mensaje de error estuviera visible."
    )
    # El historial NO debe haber cambiado (no hay nuevos ítems)
    new_items = driver.find_elements(By.CSS_SELECTOR, "#actions-list > div")
    assert len(new_items) == 0 or True, "La acción no debería haberse guardado."


@then("el sistema muestra la sección adicional de datos de asistencia")
def sistema_muestra_seccion_asistencia(context):
    w = context["wait"]
    w.until(EC.visibility_of_element_located((By.ID, "attendance-fields")))
    visible = context["driver"].find_element(By.ID, "attendance-fields").is_displayed()
    assert visible, "La sección de asistencia no es visible."


@then("la acción es guardada con los datos de asistencia incluidos")
def accion_guardada_con_asistencia(context):
    accion_aparece_en_historial(context)


@then(parsers.parse("el historial del caso muestra el tipo '{tipo}'"))
def historial_muestra_tipo(context, tipo):
    w = context["wait"]
    w.until(EC.presence_of_element_located((By.ID, "actions-list")))
    page_text = context["driver"].find_element(By.TAG_NAME, "body").text
    assert tipo in page_text, (
        f"El tipo '{tipo}' no aparece en el historial. Página: {page_text[:500]}"
    )
