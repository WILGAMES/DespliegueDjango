# BURO – Consultorio Jurídico ICESI

## Presentación del Repositorio

Este repositorio contiene la documentación y desarrollo del proyecto **BURO**, un sistema de información diseñado para optimizar la gestión del Consultorio Jurídico de la Universidad ICESI.

El sistema tiene como objetivo digitalizar y automatizar procesos clave como:

- Registro de beneficiarios.
- Gestión y asignación automática de casos jurídicos.
- Control de citas y atención.
- Gestión académica de estudiantes y profesores.
- Generación de reportes y métricas.
- Control de seguridad y privacidad de la información.

BURO busca mejorar la eficiencia operativa, garantizar trazabilidad en los procesos y asegurar el cumplimiento normativo en el tratamiento de datos personales.

---

## Integrantes del Proyecto

**Proyecto Integrador I – Grupo G03**

- Maria Juliana Marin Shek - A00405603
- Ivan Andres Quintero Sanchez A00406783
- Juan Andres Rios Mejia A00407953
- Wilder Garcia Muñoz A00405204



---

## Descripción General

El sistema permitirá gestionar el ciclo completo de un caso jurídico desde:

1. Registro del beneficiario.
2. Validación de identidad.
3. Creación y asignación automática del caso.
4. Seguimiento académico del estudiante.
5. Registro de actividades y comunicaciones.
6. Generación de reportes institucionales.

Todo bajo un esquema de roles y permisos (estudiante, profesor, secretaria, administrador), garantizando seguridad, trazabilidad y cumplimiento de la Ley 1581 de 2012.

---

## Contexto Académico

Proyecto desarrollado en el marco de la asignatura **Ingeniería de Proyecto Integrador I** para el Consultorio Jurídico ICESI.

---

## Cumplimiento Normativo

El sistema considera el cumplimiento de:

- Ley 1581 de 2012 (Protección de Datos Personales).
- Ley 2113 de 2021.
- Decreto 2069 de 2023.
- Políticas institucionales de la Universidad.

## Estructura del proyecto

BURO-todo/
├── .vscode/
├── BURO_app/
│   ├── __pycache__/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── docs/
│   ├── Diagrama de clases/
│   ├── Diagramas BD/
│   ├── Diagramas de sequencia/
│   └── PI_BURO.vpp
├── static/
├── accounts/
│   ├── migrations/
│   │   └── __init__.py
│   ├── templates/
│   │   ├── base.html
│   │   └── home.html
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py
├── cases/
│   ├── migrations/
│   │   ├── 0001_initial.py
│   │   ├── 0002_gradeweightconfig.py
│   │   ├── 0003_academicaction.py
│   │   ├── 0004_rename_legal_room_case_room_and_more.py
│   │   └── __init__.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── cases/
│   │   │   └── register_academic_action.html
│   │   └── components/
│   │       ├── breadcrumb.html
│   │       ├── button.html
│   │       ├── card.html
│   │       ├── checkbox.html
│   │       ├── dashboard_nav.html
│   │       ├── empty_state.html
│   │       ├── input.html
│   │       ├── loading_state.html
│   │       ├── note.html
│   │       ├── status_badge.html
│   │       ├── stepper.html
│   │       └── __init__.py
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── models.py
│   ├── services.py
│   ├── tests.py
│   ├── urls.py
│   └── views.py

├── venv/
│   ├── Include/
│   ├── Lib/
│   ├── Scripts/
│   └── pyvenv.cfg
├── .env
├── db.sqlite3
├── manage.py
├── requirements.txt
├── selenium_test.sh
└── unit_text.sh

##Instrucciones de ejecución del proyecto en local.
-pip install -r requirements.txt
-python manage.py runserver
