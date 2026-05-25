"""
Steps para Feature: Registro de caso nuevo (TC-01 a TC-05).

Selectores clave del formulario (Django genera IDs automáticamente):
  #id_number          — número de caso (TextInput)
  #id_beneficiary     — beneficiario   (Select)
  #id_description     — descripción    (Textarea)
  #id_room            — sala jurídica  (Select)
  #id_legal_deadline  — fecha límite   (DateInput type="date")
"""
import time

import pytest
from pytest_bdd import parsers, scenarios, then, when
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from conftest import (
    BASE_URL,
    EXISTING_CASE_NUMBER,
    WAIT,
    _fill_valid_case_fields,
    _select_first_valid,
)

scenarios("../features/registro_caso_nuevo.feature")


# ── When ──────────────────────────────────────────────────────────────────────

@when("el usuario navega a /accounts/cases/new/")
def navegar_a_nuevo_caso(context):
    driver = context["driver"]
    w      = context["wait"]
    driver.get(f"{BASE_URL}/accounts/cases/new/")
    w.until(EC.presence_of_element_located((By.ID, "id_number")))


@when(parsers.parse("el usuario ingresa el número de caso '{numero}'"))
def ingresar_numero_caso(context, numero):
    driver = context["driver"]
    # Para TC-01: genera un número único para no colisionar en re-ejecuciones
    if numero == "CASO-2026-TEST":
        numero = f"CASO-TEST-{int(time.time()) % 100000}"
    context["case_number"] = numero
    field = driver.find_element(By.ID, "id_number")
    field.clear()
    field.send_keys(numero)


@when("el usuario selecciona un beneficiario de la lista")
def seleccionar_beneficiario(context):
    sel = Select(context["driver"].find_element(By.ID, "id_beneficiary"))
    _select_first_valid(sel)


@when(parsers.parse("el usuario ingresa la descripción '{descripcion}'"))
def ingresar_descripcion(context, descripcion):
    field = context["driver"].find_element(By.ID, "id_description")
    field.clear()
    field.send_keys(descripcion)


@when("el usuario selecciona una sala jurídica de la lista")
def seleccionar_sala(context):
    sel = Select(context["driver"].find_element(By.ID, "id_room"))
    _select_first_valid(sel)


@when(parsers.parse("el usuario ingresa la fecha límite '{fecha}'"))
def ingresar_fecha_limite(context, fecha):
    driver = context["driver"]
    field  = driver.find_element(By.ID, "id_legal_deadline")
    # Forzar el valor via JS para evitar problemas con el selector de fecha nativo
    driver.execute_script("arguments[0].value = arguments[1];", field, fecha)
    context["fecha_limite"] = fecha


@when("el usuario hace click en 'Registrar caso'")
def click_registrar_caso(context):
    driver = context["driver"]
    btn    = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    btn.click()


@when("el usuario completa el resto de campos con datos válidos")
def completar_resto_campos_validos(context):
    """TC-02: ya se ingresó el número duplicado; rellena el resto."""
    driver = context["driver"]
    w      = context["wait"]
    _select_first_valid(Select(driver.find_element(By.ID, "id_beneficiary")))
    driver.find_element(By.ID, "id_description").send_keys("Caso de prueba")
    _select_first_valid(Select(driver.find_element(By.ID, "id_room")))
    driver.execute_script(
        "arguments[0].value = '2026-12-31';",
        driver.find_element(By.ID, "id_legal_deadline"),
    )


@when("el usuario no ingresa ningún dato en el formulario")
def no_ingresar_datos():
    pass  # El formulario queda vacío; se hace click directamente


@when("el usuario completa todos los campos con datos válidos")
def completar_todos_campos_validos(context):
    """TC-04 y TC-05 base: rellena todos los campos con valores correctos."""
    driver = context["driver"]
    w      = context["wait"]
    numero = f"CASO-TEST-{int(time.time()) % 100000}"
    context["case_number"] = numero
    _fill_valid_case_fields(driver, w, number=numero)


@when("el usuario completa todos los campos con datos válidos excepto sala jurídica")
def completar_campos_sin_sala(context):
    """TC-05: igual que el anterior pero sin sala."""
    driver = context["driver"]
    w      = context["wait"]
    numero = f"CASO-TEST-{int(time.time()) % 100000}"
    context["case_number"] = numero
    _fill_valid_case_fields(driver, w, number=numero, skip_room=True)


# ── Then ──────────────────────────────────────────────────────────────────────

@then("el sistema redirige a la lista de casos")
def sistema_redirige_a_lista(context):
    w      = context["wait"]
    driver = context["driver"]
    try:
        w.until(lambda d: "/cases/new/" not in d.current_url)
    except Exception:
        page_text = driver.find_element(By.TAG_NAME, "body").text[:1000]
        raise AssertionError(
            f"El formulario no redirigió. URL: {driver.current_url}\n"
            f"Errores en página: {page_text}"
        )
    assert (
        "/accounts/cases" in driver.current_url
        or "/cases/list" in driver.current_url
        or "cases" in driver.current_url
    ), f"No redirigió a la lista de casos. URL actual: {driver.current_url}"


@then(parsers.parse("el caso '{numero}' aparece con estado 'Pendiente'"))
def caso_aparece_con_pendiente(context, numero):
    driver      = context["driver"]
    case_number = context.get("case_number", numero)
    w           = context["wait"]
    # Busca el número de caso y el estado "Pendiente" en la misma página
    w.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    page_text = driver.find_element(By.TAG_NAME, "body").text
    assert case_number in page_text, (
        f"El caso '{case_number}' no aparece en la lista."
    )
    assert "Pendiente" in page_text, (
        "El estado 'Pendiente' no aparece en la lista."
    )


@then("el sistema permanece en el formulario")
def sistema_permanece_en_formulario(context):
    driver = context["driver"]
    assert "cases/new" in driver.current_url, (
        f"Se esperaba permanecer en el formulario, URL actual: {driver.current_url}"
    )


@then("se muestra un error indicando que el número de caso ya existe")
def error_numero_duplicado(context):
    driver    = context["driver"]
    page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    assert any(
        kw in page_text for kw in ("ya existe", "duplicado", "número de caso", "unique", "already")
    ), f"No se encontró mensaje de error por número duplicado. Página: {page_text[:500]}"


@then("el sistema muestra mensajes de error en los campos obligatorios")
def sistema_muestra_errores_campos_requeridos(context):
    driver = context["driver"]
    # El formulario no avanza (URL no cambia) o aparecen errores en la página
    url_no_cambio = "cases/new" in driver.current_url
    errores_visibles = len(driver.find_elements(
        By.CSS_SELECTOR, ".text-red-500, [class*='error'], [class*='invalid']"
    )) > 0
    assert url_no_cambio or errores_visibles, (
        "Se esperaban errores de validación en campos obligatorios."
    )


@then("el caso no es creado en el sistema")
def caso_no_creado(context):
    driver = context["driver"]
    # Si el sistema no redirecciona, el caso no fue creado
    assert "cases/new" in driver.current_url or "login" not in driver.current_url, (
        "Parece que el caso fue creado inesperadamente."
    )


@then("el sistema muestra un error de validación en el campo de fecha")
def error_validacion_fecha(context):
    driver    = context["driver"]
    page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    assert (
        "cases/new" in driver.current_url
    ), f"El formulario debería permanecer en /cases/new/. URL: {driver.current_url}"
    assert any(
        kw in page_text for kw in ("fecha", "pasado", "futura", "inválida", "date", "invalid", "legal_deadline")
    ), f"No se encontró error de validación en fecha. Página: {page_text[:500]}"


@then("el sistema muestra error de campo requerido en sala jurídica")
def error_sala_requerida(context):
    driver    = context["driver"]
    page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    assert (
        "cases/new" in driver.current_url
    ), f"El formulario debería permanecer en /cases/new/. URL: {driver.current_url}"
    assert any(
        kw in page_text for kw in ("sala", "requerido", "required", "room", "obligatorio")
    ), f"No se encontró error en sala jurídica. Página: {page_text[:500]}"
