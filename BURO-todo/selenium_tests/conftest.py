"""
conftest.py — configuración global y steps compartidos entre features.

Variables de entorno requeridas (ver .env.example):
  SELENIUM_BASE_URL, SECRETARY_USER, SECRETARY_PASS,
  PROFESSOR_USER, PROFESSOR_PASS, TEST_CASE_ID,
  EXISTING_CASE_NUMBER, SELENIUM_HEADLESS (default: true),
  SELENIUM_WAIT (default: 20)
"""
import os
import time

import pytest
from dotenv import load_dotenv
from pytest_bdd import given, parsers
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

# ── Parámetros de entorno ──────────────────────────────────────────────────────
BASE_URL             = os.environ.get("SELENIUM_BASE_URL", "https://desplieguedjango.onrender.com").rstrip("/")
SECRETARY_USER       = os.environ.get("SECRETARY_USER", "")
SECRETARY_PASS       = os.environ.get("SECRETARY_PASS", "")
PROFESSOR_USER       = os.environ.get("PROFESSOR_USER", "")
PROFESSOR_PASS       = os.environ.get("PROFESSOR_PASS", "")
WAIT                 = int(os.environ.get("SELENIUM_WAIT", "20"))
TEST_CASE_ID         = os.environ.get("TEST_CASE_ID", "1")
EXISTING_CASE_NUMBER = os.environ.get("EXISTING_CASE_NUMBER", "CASO-2026-001")


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def context():
    """
    Diccionario compartido entre steps del mismo escenario.
    Al finalizar, cierra el WebDriver si fue creado.
    Claves típicas: 'driver', 'wait', 'case_number', 'case_id'.
    """
    data: dict = {}
    yield data
    driver = data.get("driver")
    if driver:
        try:
            driver.quit()
        except Exception:
            pass


# ── Helpers internos ───────────────────────────────────────────────────────────

def _make_driver() -> webdriver.Chrome:
    options = Options()
    if os.environ.get("SELENIUM_HEADLESS", "true").lower() == "true":
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )


def _do_login(driver: webdriver.Chrome, username: str, password: str) -> None:
    """Navega a /accounts/login/ e ingresa credenciales."""
    driver.get(f"{BASE_URL}/accounts/login/")
    w = WebDriverWait(driver, WAIT)
    w.until(EC.presence_of_element_located((By.NAME, "username")))

    driver.find_element(By.NAME, "username").send_keys(username)
    driver.find_element(By.NAME, "password").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()

    # Espera a que el login sea exitoso (sale de /login/)
    w.until(lambda d: "/login/" not in d.current_url)


def _fill_valid_case_fields(driver: webdriver.Chrome, wait: WebDriverWait,
                             *, number: str, skip_room: bool = False) -> None:
    """
    Rellena los campos del formulario de creación de caso con valores válidos.
    Deja la sala vacía si skip_room=True (usado en TC-05).
    """
    wait.until(EC.presence_of_element_located((By.ID, "id_number")))

    # Número de caso
    num_field = driver.find_element(By.ID, "id_number")
    num_field.clear()
    num_field.send_keys(number)

    # Beneficiario — selecciona la primera opción no vacía
    benef_select = Select(driver.find_element(By.ID, "id_beneficiary"))
    _select_first_valid(benef_select)

    # Descripción
    driver.find_element(By.ID, "id_description").send_keys("Caso de arrendamiento vivienda")

    # Sala jurídica
    if not skip_room:
        room_select = Select(driver.find_element(By.ID, "id_room"))
        _select_first_valid(room_select)

    # Fecha límite — se establece después para poder sobreescribirla en cada test
    deadline_field = driver.find_element(By.ID, "id_legal_deadline")
    driver.execute_script(
        "arguments[0].value = arguments[1];", deadline_field, "2026-12-31"
    )


def _select_first_valid(select_widget: Select) -> None:
    """Selecciona la primera opción que no sea la opción vacía ('-- ...')."""
    for opt in select_widget.options:
        if opt.get_attribute("value"):
            opt.click()
            return
    raise AssertionError("No hay opciones válidas disponibles en el select.")


# ── Steps de Given compartidos entre features ──────────────────────────────────

@given("el usuario está autenticado como Secretaria")
def autenticado_secretaria(context):
    driver = _make_driver()
    _do_login(driver, SECRETARY_USER, SECRETARY_PASS)
    context["driver"] = driver
    context["wait"]   = WebDriverWait(driver, WAIT)


@given("el usuario está autenticado como Profesor")
def autenticado_profesor(context):
    driver = _make_driver()
    _do_login(driver, PROFESSOR_USER, PROFESSOR_PASS)
    context["driver"] = driver
    context["wait"]   = WebDriverWait(driver, WAIT)


@given("existe al menos un beneficiario registrado en el sistema")
def existe_beneficiario():
    pass  # Precondición de datos — debe cumplirse en el servidor desplegado


@given("existe al menos una sala jurídica registrada en el sistema")
def existe_sala():
    pass  # Precondición de datos — debe cumplirse en el servidor desplegado


@given(parsers.parse("existe un caso con número '{numero}' en el sistema"))
def existe_caso_con_numero(context, numero):
    context["existing_case_number"] = numero


@given("existe un caso activo con un estudiante asignado al profesor")
def existe_caso_con_estudiante(context):
    context["case_id"] = TEST_CASE_ID


@given("existe un caso activo disponible")
def existe_caso_activo(context):
    context["case_id"] = TEST_CASE_ID


@given("existe un caso activo con estudiantes disponibles para sancionar")
def existe_caso_con_estudiantes_disponibles(context):
    context["case_id"] = TEST_CASE_ID


@given("el modal de sanción académica está abierto")
def modal_sancion_abierto(context):
    """Navega al formulario del caso y abre el modal de sanción."""
    driver = context["driver"]
    w      = context["wait"]
    case_id = context.get("case_id", TEST_CASE_ID)

    driver.get(f"{BASE_URL}/cases/academic-action/form/{case_id}/")
    w.until(EC.presence_of_element_located((By.ID, "modal-aplicar-sancion")))

    # Abrir modal haciendo click en el botón de sanción
    btn = driver.find_element(
        By.XPATH,
        "//*[contains(normalize-space(text()), 'Reasignar como sanci')]"
    )
    btn.click()
    w.until(EC.visibility_of_element_located((By.ID, "modal-aplicar-sancion")))


@given("el usuario está en el formulario de acción académica de un caso")
def en_formulario_accion_academica(context):
    driver  = context["driver"]
    w       = context["wait"]
    case_id = context.get("case_id", TEST_CASE_ID)
    driver.get(f"{BASE_URL}/cases/academic-action/form/{case_id}/")
    w.until(EC.presence_of_element_located((By.ID, "action-type")))
