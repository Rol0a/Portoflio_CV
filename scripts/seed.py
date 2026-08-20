"""Populate the database with the portfolio's real skills, projects, and credentials (EN/ES).

Run inside the backend container (where this file is mounted alongside the `app`
package at /app): `python -m scripts.seed`, or via `make db-seed`.
Safe to re-run: existing rows (matched by unique slug/name) are left alone.
"""

import asyncio
import random
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config import settings
from app.database import async_session_factory
from app.models.admin import AdminUser
from app.models.analytics import AnalyticsEvent, AnalyticsEventType
from app.models.certification import Certification, CertificationTranslation
from app.models.project import Locale, Project, ProjectImage, ProjectTranslation, Technology, TechCategory
from app.models.skill import Skill, SkillCategory
from app.services.auth_service import hash_password

CERTIFICATIONS = [
    {
        "slug": "fortinet-network-security",
        "issuer": "Fortinet",
        "issue_date": "2026-06-01",
        "expiry_date": None,
        "credential_url": None,
        "featured": True,
        "sort_order": 1,
        "translations": {
            Locale.en: {
                "title": "Network Security Specialization",
                "description": "Training in network-security concepts and technologies — segmentation, secure access, and network defence — complementing hands-on Linux, networking, and infrastructure work.",
            },
            Locale.es: {
                "title": "Especialización en Seguridad de Redes",
                "description": "Formación en conceptos y tecnologías de seguridad de redes —segmentación, acceso seguro y defensa de red— que complementa el trabajo práctico en Linux, redes e infraestructura.",
            },
        },
    },
    {
        "slug": "sgac-ncac-space-leader-award",
        "issuer": "Space Generation Advisory Council",
        "issue_date": "2025-05-01",
        "expiry_date": None,
        "credential_url": "https://spacegeneration.org/sgac-2025-ncac-sla-winners",
        "featured": True,
        "sort_order": 2,
        "translations": {
            Locale.en: {
                "title": "North, Central American and Caribbean Space Leader Award",
                "description": "Regional recognition from SGAC for leadership and contribution to the space community across North America, Central America, and the Caribbean.",
            },
            Locale.es: {
                "title": "Premio Líder Espacial de Norteamérica, Centroamérica y el Caribe",
                "description": "Reconocimiento regional de SGAC por liderazgo y contribución a la comunidad espacial en Norteamérica, Centroamérica y el Caribe.",
            },
        },
    },
    {
        # NOTE: issue date is a placeholder — the bio source gives no date for
        # this credential. Replace with the real NetAcad completion date (and
        # add credential_url) before this goes public.
        "slug": "cisco-ccna-introduction-to-networks",
        "issuer": "Cisco Networking Academy",
        "issue_date": "2025-01-01",
        "expiry_date": None,
        "credential_url": None,
        "featured": True,
        "sort_order": 3,
        "translations": {
            Locale.en: {
                "title": "Introduction to Networks (CCNA 1)",
                "description": "Foundational networking: TCP/IP, IPv4/IPv6, subnetting, Ethernet, network devices, routing and switching fundamentals, and common network services.",
            },
            Locale.es: {
                "title": "Introducción a Redes (CCNA 1)",
                "description": "Fundamentos de redes: TCP/IP, IPv4/IPv6, subredes, Ethernet, dispositivos de red, fundamentos de enrutamiento y conmutación, y servicios de red comunes.",
            },
        },
    },
    {
        "slug": "jaguar-space-fellowship",
        "issuer": "Jaguar Space LLC.",
        "issue_date": "2024-06-01",
        "expiry_date": None,
        "credential_url": None,
        "featured": True,
        "sort_order": 4,
        "translations": {
            Locale.en: {
                "title": "Jaguar Space Fellowship",
                "description": "Selective fellowship that led to aerospace R&D work in Boulder, Colorado spanning research, engineering, and space-sector development.",
            },
            Locale.es: {
                "title": "Beca Jaguar Space",
                "description": "Beca selectiva que dio lugar a trabajo de I+D aeroespacial en Boulder, Colorado, abarcando investigación, ingeniería y desarrollo del sector espacial.",
            },
        },
    },
    {
        "slug": "microsoft-office-specialist",
        "issuer": "Certiport",
        "issue_date": "2022-10-01",
        "expiry_date": None,
        "credential_url": None,
        "featured": False,
        "sort_order": 5,
        "translations": {
            Locale.en: {
                "title": "Microsoft Office Specialist",
                "description": "Formal Microsoft Office certification covering structured document, spreadsheet, and presentation workflows.",
            },
            Locale.es: {
                "title": "Especialista en Microsoft Office",
                "description": "Certificación formal en Microsoft Office sobre flujos de trabajo estructurados de documentos, hojas de cálculo y presentaciones.",
            },
        },
    },
]

TECHNOLOGIES = [
    # programming
    ("Python", TechCategory.programming),
    ("C/C++", TechCategory.programming),
    ("TypeScript", TechCategory.programming),
    ("Bash", TechCategory.programming),
    # embedded systems
    ("ESP32", TechCategory.embedded_systems),
    ("Arduino", TechCategory.embedded_systems),
    ("ATmega328P", TechCategory.embedded_systems),
    ("Bluetooth", TechCategory.embedded_systems),
    ("PWM", TechCategory.embedded_systems),
    ("UART / I2C / SPI", TechCategory.embedded_systems),
    # electronics
    ("PCB Design", TechCategory.electronics),
    ("H-Bridge Motor Driver", TechCategory.electronics),
    ("DC-DC Buck Conversion", TechCategory.electronics),
    ("Li-ion Power", TechCategory.electronics),
    # web / infrastructure
    ("React", TechCategory.web_dev),
    ("FastAPI", TechCategory.web_dev),
    ("PostgreSQL", TechCategory.web_dev),
    ("SQLAlchemy", TechCategory.web_dev),
    ("Caddy", TechCategory.web_dev),
    ("Docker Compose", TechCategory.linux_devops),
    ("Docker", TechCategory.linux_devops),
    ("Fedora Linux", TechCategory.linux_devops),
    ("Git", TechCategory.linux_devops),
    ("SSH", TechCategory.linux_devops),
    ("KVM / Virtual Machines", TechCategory.linux_devops),
    # engineering tools
    ("Fusion 360", TechCategory.engineering_tools),
    ("FDM 3D Printing", TechCategory.engineering_tools),
    ("ROS 2", TechCategory.engineering_tools),
    ("Gazebo", TechCategory.engineering_tools),
    ("Numerical Modeling", TechCategory.engineering_tools),
    ("Orbital Mechanics", TechCategory.engineering_tools),
]

# (name, category, proficiency 1-5). Order within a category is the display
# order — the skills endpoint sorts by (category, sort_order), which is
# assigned from this list's index in seed().
# (name, category, featured_rank). `featured_rank` is None for everything that
# isn't in the page's opening Featured row; where it's set, the number is that
# badge's position in that row.
#
# Deliberate omissions, so a future session doesn't "restore" them:
# - No proficiency values. The badges show no numbers; the projects are the
#   evidence of depth (see the migration that dropped the column).
# - Names are short and single-concept. "PWM & Motor Control" became `PWM` and
#   `Motor Control`; "Bluetooth & Serial Links" became `Bluetooth` and
#   `Serial Communication`.
# - `skills.name` is UNIQUE, so a skill that fits two categories is filed under
#   one. Motor Control -> Embedded Systems (it's the ESP32/H-bridge work),
#   SSH -> Networks, TypeScript and Bash -> Programming, PostgreSQL and SQLite
#   -> Web & Backend.
# - Ubuntu is dropped: Fedora is the actual daily environment, and listing three
#   distributions at equal weight overstates the other two.
# - Component-level parts (H-bridges, DC-DC converters, motor drivers) are not
#   skills here. They belong in the project write-ups that demonstrate them.
SKILLS = [
    ("Python", SkillCategory.programming, 1),
    ("C", SkillCategory.programming, None),
    ("C++", SkillCategory.programming, 2),
    ("Embedded C", SkillCategory.programming, None),
    ("Bash", SkillCategory.programming, None),
    ("TypeScript", SkillCategory.programming, None),
    ("SQL", SkillCategory.programming, None),

    ("ESP32", SkillCategory.embedded_systems, 3),
    ("Arduino", SkillCategory.embedded_systems, None),
    ("ATmega328P", SkillCategory.embedded_systems, None),
    ("UART", SkillCategory.embedded_systems, None),
    ("SPI", SkillCategory.embedded_systems, None),
    ("I2C", SkillCategory.embedded_systems, None),
    ("PWM", SkillCategory.embedded_systems, None),
    ("Bluetooth", SkillCategory.embedded_systems, None),
    ("Serial Communication", SkillCategory.embedded_systems, None),
    ("Sensor Acquisition", SkillCategory.embedded_systems, None),
    ("Telemetry", SkillCategory.embedded_systems, None),
    ("Motor Control", SkillCategory.embedded_systems, None),

    ("Altium Designer", SkillCategory.hardware_design, 9),
    ("PCB Design", SkillCategory.hardware_design, None),
    ("PCB Bring-up", SkillCategory.hardware_design, None),
    ("Autodesk Fusion 360", SkillCategory.hardware_design, 8),
    ("SolidWorks", SkillCategory.hardware_design, None),
    ("Autodesk Inventor", SkillCategory.hardware_design, None),
    ("FDM Printing", SkillCategory.hardware_design, None),
    ("SLA Printing", SkillCategory.hardware_design, None),
    ("Laser Cutting", SkillCategory.hardware_design, None),
    ("Soldering", SkillCategory.hardware_design, None),
    ("DFM / DFA", SkillCategory.hardware_design, None),
    ("Rapid Prototyping", SkillCategory.hardware_design, None),

    ("ROS 2", SkillCategory.robotics, 4),
    ("Gazebo", SkillCategory.robotics, None),
    ("MATLAB", SkillCategory.robotics, 10),
    ("Simulink", SkillCategory.robotics, None),
    ("Robot Simulation", SkillCategory.robotics, None),
    ("Sensor Integration", SkillCategory.robotics, None),
    ("Kinematics", SkillCategory.robotics, None),
    ("Control Systems", SkillCategory.robotics, None),

    ("IPv4", SkillCategory.networks, None),
    ("IPv6", SkillCategory.networks, None),
    ("TCP/IP", SkillCategory.networks, None),
    ("DNS", SkillCategory.networks, None),
    ("DHCP", SkillCategory.networks, None),
    ("SSH", SkillCategory.networks, None),
    ("LAN / WAN", SkillCategory.networks, None),
    ("Routing", SkillCategory.networks, None),
    ("Switching", SkillCategory.networks, None),
    ("VLANs", SkillCategory.networks, None),
    ("Linux Networking", SkillCategory.networks, None),
    ("Network Security", SkillCategory.networks, None),
    ("Cisco", SkillCategory.networks, None),
    ("Fortinet", SkillCategory.networks, None),

    ("React", SkillCategory.web_backend, None),
    ("FastAPI", SkillCategory.web_backend, None),
    ("REST APIs", SkillCategory.web_backend, None),
    ("PostgreSQL", SkillCategory.web_backend, None),
    ("SQLite", SkillCategory.web_backend, None),
    ("JSON", SkillCategory.web_backend, None),
    ("HTML", SkillCategory.web_backend, None),
    ("CSS", SkillCategory.web_backend, None),

    ("Linux", SkillCategory.linux_devops, 5),
    ("Fedora", SkillCategory.linux_devops, None),
    ("Git", SkillCategory.linux_devops, 7),
    ("GitHub", SkillCategory.linux_devops, None),
    ("Docker", SkillCategory.linux_devops, 6),
    ("Docker Compose", SkillCategory.linux_devops, None),
    ("Nginx", SkillCategory.linux_devops, None),
    ("Reverse Proxy", SkillCategory.linux_devops, None),
    ("Virtual Machines", SkillCategory.linux_devops, None),

    ("Pandas", SkillCategory.data_ml, None),
    ("NumPy", SkillCategory.data_ml, None),
    ("Matplotlib", SkillCategory.data_ml, None),
    ("Data Processing", SkillCategory.data_ml, None),
    ("Predictive Analytics", SkillCategory.data_ml, None),
    ("Digital Twins", SkillCategory.data_ml, None),
    ("Data Acquisition", SkillCategory.data_ml, None),
]

PROJECTS = [
    {
        "slug": "pokebot",
        "category": "robotics",
        "github_url": "https://github.com/Rol0a/PokeBot",
        "demo_url": None,
        "featured": True,
        "sort_order": 1,
        # Real build photo, served from frontend/public/images/ (gitignored —
        # see .gitignore). Projects without a shipped asset omit `hero_image`
        # entirely and render the designed placeholder instead. Omission is the
        # supported state, not a gap to paper over with a guessed URL — see the
        # images block in seed().
        "hero_image": "/images/pokebot-hero.jpg",
        "technologies": [
            "ESP32",
            "C/C++",
            "Arduino",
            "Bluetooth",
            "PWM",
            "H-Bridge Motor Driver",
            "DC-DC Buck Conversion",
            "Li-ion Power",
            "PCB Design",
            "Fusion 360",
            "FDM 3D Printing",
        ],
        "translations": {
            Locale.en: {
                "title": "PokeBot — Bluetooth-Controlled Sumo Robot",
                "short_desc": "A fully 3D-printed sumo robot combining ESP32 firmware, Bluetooth smartphone control, a custom buck-converter PCB, and differential drive — validated in competition with two wins in three matches.",
                "overview": "PokeBot is a complete mechatronics build around a manually controlled sumo robot. The goal was not a motorised chassis but one integrated system: mechanical CAD, embedded firmware, Bluetooth communication, power conversion, a fabricated PCB, batteries, motors, and a usable smartphone interface. The robot uses a two-wheel differential drive controlled by an ESP32; a smartphone running the Dabble GamePad interface sends commands over Bluetooth, and the ESP32 translates them into GPIO and PWM signals for the motor driver. The chassis and enclosure were designed in Autodesk Fusion 360 and printed in PLA on FDM machines.",
                "problem": "Design and manufacture a compact sumo robot that survives real competition while staying controllable, manoeuvrable, electrically reliable, and serviceable. The design had to reconcile constraints from several domains at once — chassis dimensions, internal packaging, motor mounting, traction, impact resistance, battery capacity, voltage regulation, wireless control, firmware responsiveness, and manufacturability.",
                "requirements": "Fit an approximately 20 × 20 cm competition footprint. Drive two independently controlled DC gearmotors. Support differential steering with near-zero-radius turns. Accept wireless control from a smartphone. Use an ESP32 as the central embedded controller. Generate PWM and direction signals for motor control. Integrate rechargeable lithium-ion power and regulate it down for the control electronics. Use a custom mechanical structure suitable for FDM printing, and stay accessible for maintenance between matches.",
                "architecture": "Control path: smartphone → Bluetooth → ESP32 → GPIO/PWM → motor driver → DC motors → differential drive. Power path: two 3.7 V Li-ion cells → 7.4 V bus → motor system, plus a custom PCB stepping 7.4 V down to a 5 V control supply for the ESP32. The firmware is deliberately modular — communication handling, motor-control functions, and hardware-specific pin configuration are separated, so pin mappings or control behaviour can change without rewriting the application.",
                "implementation": "The ESP32 was programmed in C/C++ through the Arduino toolchain, with Bluetooth control built on the Dabble/DabbleESP32 library, mapping GamePad directional input to motor-control functions. Motor direction runs through H-bridge driver inputs while speed is set by PWM — a 1 kHz, 8-bit configuration with a 0–255 command range. The chassis, enclosure, motor mounts, battery bay, electronics packaging, and external geometry were designed from scratch in Fusion 360 and fabricated by FDM printing. A custom PCB replaced loose wiring and carried both the DC-DC conversion stage and the ESP32-side interconnects.",
                "decisions": "ESP32 rather than a separate wireless module, since Bluetooth is integrated into the controller. Differential drive to cut mechanical steering complexity and allow aggressive turning. A custom PCB to organise the electrical system and absorb power conversion. A 3D-printed chassis for fast iteration between CAD, fabrication, assembly, and testing. A smartphone interface instead of a dedicated physical remote. Hardware abstraction in the firmware, so the software could keep pace with a physically changing robot.",
                "challenges": "Every subsystem moved the others. Power architecture drove internal packaging; chassis geometry drove motor placement and traction; firmware timing showed up as handling. The build required repeated iteration between mechanical packaging, electrical requirements, firmware, battery integration, and measured physical performance.",
                "testing_desc": "Testing progressed from subsystem checks to full physical integration. Final validation was an actual sumo competition, exercising Bluetooth link stability, motor response, turning, traction, battery endurance, PCB operation, structural durability, and real-time human control all at once.",
                "results": "Roughly 20 × 20 × 15 cm and about 420 g. ESP32 with Bluetooth smartphone GamePad control, two-motor differential drive, 2 × 3.7 V Li-ion power, and a custom 7.4 V → 5 V buck-converter PCB. Competition record: two wins in three battles, a 66.7% win rate.",
                "lessons": "Successful mechatronics depends on integration, not isolated subsystem performance. Mechanical packaging, power distribution, firmware timing, wiring, user control, and manufacturability all shape how the machine actually behaves — and physical competition exposed issues that bench testing alone would not have found.",
            },
            Locale.es: {
                "title": "PokeBot — Robot de Sumo Controlado por Bluetooth",
                "short_desc": "Un robot de sumo totalmente impreso en 3D que combina firmware para ESP32, control por Bluetooth desde el celular, una PCB reductora de voltaje propia y tracción diferencial — validado en competencia con dos victorias en tres combates.",
                "overview": "PokeBot es un proyecto de mecatrónica completo construido alrededor de un robot de sumo de control manual. El objetivo no era un chasis motorizado sino un sistema integrado: diseño mecánico CAD, firmware embebido, comunicación Bluetooth, conversión de potencia, una PCB fabricada, baterías, motores y una interfaz usable desde el celular. El robot usa tracción diferencial de dos ruedas controlada por un ESP32; un celular con la interfaz Dabble GamePad envía comandos por Bluetooth y el ESP32 los traduce en señales GPIO y PWM para el driver de motores. El chasis y la carcasa se diseñaron en Autodesk Fusion 360 y se imprimieron en PLA por FDM.",
                "problem": "Diseñar y fabricar un robot de sumo compacto que sobreviva una competencia real y a la vez sea controlable, maniobrable, eléctricamente confiable y fácil de mantener. El diseño tuvo que conciliar restricciones de varios dominios a la vez: dimensiones del chasis, empaquetado interno, montaje de motores, tracción, resistencia a impactos, capacidad de batería, regulación de voltaje, control inalámbrico, respuesta del firmware y manufacturabilidad.",
                "requirements": "Caber en una base de competencia de aproximadamente 20 × 20 cm. Mover dos motorreductores DC controlados de forma independiente. Permitir dirección diferencial con giros de radio casi nulo. Aceptar control inalámbrico desde un celular. Usar un ESP32 como controlador embebido central. Generar señales de PWM y de dirección para el control de motores. Integrar alimentación recargable de iones de litio y regularla para la electrónica de control. Usar una estructura mecánica propia apta para impresión FDM y accesible para mantenimiento entre combates.",
                "architecture": "Ruta de control: celular → Bluetooth → ESP32 → GPIO/PWM → driver de motores → motores DC → tracción diferencial. Ruta de potencia: dos celdas Li-ion de 3.7 V → bus de 7.4 V → sistema de motores, más una PCB propia que reduce de 7.4 V a 5 V para alimentar el ESP32. El firmware es deliberadamente modular: el manejo de comunicación, las funciones de control de motores y la configuración de pines específica del hardware están separados, de modo que el mapeo de pines o el comportamiento de control pueden cambiar sin reescribir la aplicación.",
                "implementation": "El ESP32 se programó en C/C++ con el entorno de Arduino, y el control por Bluetooth se construyó sobre la librería Dabble/DabbleESP32, mapeando la entrada direccional del GamePad a funciones de control de motores. La dirección de los motores pasa por las entradas de un puente H mientras la velocidad se fija por PWM, con una configuración de 1 kHz y 8 bits en un rango de comando de 0–255. El chasis, la carcasa, los soportes de motor, el alojamiento de baterías, el empaquetado de electrónica y la geometría exterior se diseñaron desde cero en Fusion 360 y se fabricaron por impresión FDM. Una PCB propia reemplazó el cableado suelto y concentró tanto la etapa de conversión DC-DC como las interconexiones del lado del ESP32.",
                "decisions": "ESP32 en lugar de un módulo inalámbrico aparte, porque el Bluetooth ya está integrado en el controlador. Tracción diferencial para reducir la complejidad mecánica de la dirección y permitir giros agresivos. Una PCB propia para ordenar el sistema eléctrico e incorporar la conversión de potencia. Un chasis impreso en 3D para iterar rápido entre CAD, fabricación, ensamblaje y pruebas. Una interfaz en el celular en vez de un control físico dedicado. Abstracción de hardware en el firmware, para que el software pudiera seguir el ritmo de un robot que cambiaba físicamente.",
                "challenges": "Cada subsistema movía a los demás. La arquitectura de potencia condicionaba el empaquetado interno; la geometría del chasis condicionaba la posición de los motores y la tracción; los tiempos del firmware se notaban en el manejo. El proyecto exigió iteración repetida entre empaquetado mecánico, requisitos eléctricos, firmware, integración de baterías y desempeño físico medido.",
                "testing_desc": "Las pruebas avanzaron de verificaciones por subsistema a la integración física completa. La validación final fue una competencia de sumo real, que ejercitó a la vez la estabilidad del enlace Bluetooth, la respuesta de los motores, el giro, la tracción, la autonomía de la batería, el funcionamiento de la PCB, la durabilidad estructural y el control humano en tiempo real.",
                "results": "Aproximadamente 20 × 20 × 15 cm y unos 420 g. ESP32 con control por GamePad Bluetooth desde el celular, tracción diferencial de dos motores, alimentación 2 × 3.7 V Li-ion y una PCB reductora propia de 7.4 V → 5 V. Resultado en competencia: dos victorias en tres combates, una tasa de victoria del 66.7%.",
                "lessons": "La mecatrónica exitosa depende de la integración, no del desempeño aislado de cada subsistema. El empaquetado mecánico, la distribución de potencia, los tiempos del firmware, el cableado, el control del usuario y la manufacturabilidad determinan cómo se comporta realmente la máquina, y la competencia física expuso problemas que las pruebas de banco por sí solas no habrían encontrado.",
            },
        },
    },
    {
        "slug": "micro-programming-labs",
        "category": "embedded",
        "github_url": "https://github.com/Rol0a/PrograDeMicros_Lopez231928",
        "hero_image": "/images/Microcontroller.jpg",
        "demo_url": None,
        "featured": False,
        "sort_order": 2,
        "technologies": ["ATmega328P", "Arduino", "C/C++", "UART / I2C / SPI", "Git"],
        "translations": {
            Locale.en: {
                "title": "Microcontroller Programming Laboratories",
                "short_desc": "A semester-scale collection of embedded laboratories and projects on the Arduino Nano / ATmega328P, built around low-level peripheral control, hardware validation, and iterative firmware development.",
                "overview": "This repository documents my practical work for Programación de Microcontroladores (IE2023) during the first academic cycle of 2026. It holds a sequence of laboratories, two larger projects, testing material, configuration files, and reusable library work, with the Arduino Nano and its ATmega328P as the primary platform. Rather than one finished product, it shows progression through embedded-programming concepts and a repeatable laboratory workflow: implement a concept, compile and flash, interact with physical hardware, find the fault, revise, and preserve the work in version control.",
                "problem": "Build practical competence in microcontroller programming beyond high-level application logic, by working directly with constrained embedded hardware and progressively integrating peripherals and control functions.",
                "requirements": "Develop firmware for the ATmega328P / Arduino Nano platform. Organise the work into repeatable laboratory and project structures. Validate firmware against physical hardware rather than simulation alone. Build familiarity with embedded peripherals and timing. Factor out reusable code where it makes sense. Keep the full source history in Git.",
                "architecture": "The repository is organised as a sequence of laboratory folders and project folders — Labs 0 through 6, Project 1, Project 2, testing material, configuration files, and an XC8-related library directory. The structure reflects incremental development rather than a single monolithic firmware application.",
                "implementation": "The work centres on microcontroller programming and peripheral control on the Arduino Nano / ATmega328P, with the repository serving as the development, iteration, validation, and grading environment for the course. It complements my ESP32 work by putting me on a smaller platform where memory, peripherals, timing, and hardware behaviour all have to be reasoned about explicitly.",
                "decisions": "Keep each laboratory isolated so individual concepts can be tested independently. Use Git to preserve iterations and keep development traceable. Use the ATmega328P as a practical environment for embedded fundamentals before moving to larger architectures. Keep configuration and reusable code alongside the project implementations rather than in a separate tree.",
                "challenges": "Embedded coursework means debugging across software and hardware at the same time. A firmware defect, a wiring issue, a timing problem, a mis-set peripheral register, or a wrong assumption about the microcontroller can all produce the same symptom — which is exactly what forces disciplined testing and incremental integration.",
                "testing_desc": "Testing runs through compilation, flashing, physical hardware interaction, and dedicated test directories where appropriate. Each laboratory is a smaller validation target before concepts get combined into the larger projects.",
                "results": "21 commits covering laboratories 0 through 6, two larger project directories, testing material, configuration files, and reusable library work — a complete semester-scale progression in practical microcontroller programming.",
                "lessons": "The course sharpened my understanding of how source code maps to real microcontroller behaviour, and why embedded development benefits from modular code, controlled experiments, careful peripheral configuration, and repeatable validation.",
            },
            Locale.es: {
                "title": "Laboratorios de Programación de Microcontroladores",
                "short_desc": "Una colección de un semestre de laboratorios y proyectos embebidos sobre Arduino Nano / ATmega328P, centrada en control de periféricos de bajo nivel, validación con hardware y desarrollo iterativo de firmware.",
                "overview": "Este repositorio documenta mi trabajo práctico para Programación de Microcontroladores (IE2023) durante el primer ciclo académico de 2026. Contiene una secuencia de laboratorios, dos proyectos mayores, material de pruebas, archivos de configuración y trabajo de librerías reutilizables, con el Arduino Nano y su ATmega328P como plataforma principal. Más que un producto terminado, muestra la progresión por los conceptos de programación embebida y un flujo de laboratorio repetible: implementar un concepto, compilar y grabar, interactuar con el hardware físico, encontrar la falla, corregir y preservar el trabajo con control de versiones.",
                "problem": "Desarrollar competencia práctica en programación de microcontroladores más allá de la lógica de aplicación de alto nivel, trabajando directamente con hardware embebido limitado e integrando progresivamente periféricos y funciones de control.",
                "requirements": "Desarrollar firmware para la plataforma ATmega328P / Arduino Nano. Organizar el trabajo en estructuras repetibles de laboratorio y proyecto. Validar el firmware contra hardware físico y no solo en simulación. Adquirir familiaridad con periféricos embebidos y temporización. Extraer código reutilizable cuando tenga sentido. Mantener todo el historial de fuentes en Git.",
                "architecture": "El repositorio se organiza como una secuencia de carpetas de laboratorio y de proyecto: Labs 0 a 6, Proyecto 1, Proyecto 2, material de pruebas, archivos de configuración y un directorio de librerías relacionado con XC8. La estructura refleja desarrollo incremental y no una única aplicación de firmware monolítica.",
                "implementation": "El trabajo se centra en la programación de microcontroladores y el control de periféricos sobre Arduino Nano / ATmega328P, y el repositorio funciona como el entorno de desarrollo, iteración, validación y evaluación del curso. Complementa mi trabajo con ESP32 al ponerme en una plataforma más pequeña donde la memoria, los periféricos, la temporización y el comportamiento del hardware deben razonarse de forma explícita.",
                "decisions": "Mantener cada laboratorio aislado para poder probar los conceptos de forma independiente. Usar Git para preservar iteraciones y hacer trazable el desarrollo. Usar el ATmega328P como entorno práctico para los fundamentos embebidos antes de pasar a arquitecturas mayores. Conservar la configuración y el código reutilizable junto a las implementaciones y no en un árbol aparte.",
                "challenges": "El trabajo embebido implica depurar software y hardware al mismo tiempo. Un defecto de firmware, un problema de cableado, un error de temporización, un registro de periférico mal configurado o una suposición equivocada sobre el microcontrolador pueden producir el mismo síntoma, y eso es justamente lo que obliga a probar con disciplina e integrar de forma incremental.",
                "testing_desc": "Las pruebas se realizan mediante compilación, grabado, interacción con hardware físico y directorios de prueba dedicados cuando corresponde. Cada laboratorio es un objetivo de validación más pequeño antes de que los conceptos se combinen en los proyectos mayores.",
                "results": "21 commits que cubren los laboratorios 0 a 6, dos directorios de proyecto mayores, material de pruebas, archivos de configuración y trabajo de librerías reutilizables: una progresión completa a escala de semestre en programación práctica de microcontroladores.",
                "lessons": "El curso afinó mi comprensión de cómo el código fuente se traduce en comportamiento real del microcontrolador, y de por qué el desarrollo embebido se beneficia de código modular, experimentos controlados, configuración cuidadosa de periféricos y validación repetible.",
            },
        },
    },
    {
        "slug": "portfolio-platform",
        "category": "software",
        "github_url": "https://github.com/Rol0a/Portoflio_CV",
        # A screenshot of this platform's own NOC page. Self-referential on
        # purpose: the admin/monitoring surface is the part of this project that
        # a screenshot can actually show, in a way a landing page can't.
        # (The filename says "PersonalProfile" — it is not a portrait. Kept as
        # uploaded so the path matches the file that ships.)
        "hero_image": "/images/PersonalProfile.png",
        # `project_images.alt_text` is a single column, not a translated one, so
        # this is English-only by schema — not an oversight to "fix" by adding an
        # es key here that nothing would read.
        "hero_alt": "The platform's Network Health dashboard: service status pills, "
        "internet reachability, host CPU/memory/disk over time, and a "
        "requests-and-errors chart.",
        "demo_url": None,
        "featured": True,
        "sort_order": 3,
        "technologies": [
            "React",
            "TypeScript",
            "FastAPI",
            "Python",
            "PostgreSQL",
            "SQLAlchemy",
            "Docker",
            "Docker Compose",
            "Caddy",
        ],
        "translations": {
            Locale.en: {
                "title": "Full-Stack Engineering Portfolio Platform",
                "short_desc": "This site — a bilingual, self-hosted portfolio built as a multi-service application with a React frontend, FastAPI backend, PostgreSQL, a standalone NOC monitor, and Caddy behind a Cloudflare Tunnel.",
                "overview": "Instead of treating my portfolio as a static collection of HTML pages, I built it as a software-engineering project that demonstrates the same infrastructure and systems skills the site describes. The repository is divided into dedicated frontend, backend, infrastructure, NOC/network-health, documentation, and scripts areas, with Docker Compose configurations for development and production, environment templates, a Makefile, and GitHub workflow automation. The public application presents biography, skills, projects, certifications, and contact; the administrative side adds first-party analytics and network-health monitoring, so the portfolio doubles as an exercise in observability and deployment.",
                "problem": "A conventional static portfolio can display projects but does not itself demonstrate much software-engineering depth. The goal was to make the portfolio part of the technical evidence — a maintainable, deployable, monitored application — and to do it bilingually and self-hosted, without third-party site builders or third-party tracking scripts.",
                "requirements": "Provide Home, About, Skills, Projects, Certifications, and Contact views, with full project detail pages rather than only cards. Keep backend and frontend as separate concerns. Serve English and Spanish from the same content model. Support an administrative login with analytics views and service/network-health monitoring. Run containerised in development and production, with infrastructure configuration in version control and environment-based configuration throughout. Include automation scripts and maintained documentation.",
                "architecture": "A React/TypeScript SPA built with Vite and served by nginx, behind Caddy acting as reverse proxy. A FastAPI backend exposes a versioned REST API over PostgreSQL, using async SQLAlchemy 2.0 with asyncpg and Alembic migrations. Localised content lives in translation tables keyed by locale rather than suffixed columns, so adding a language needs no migration. A standalone NOC service samples service status, internet reachability, and host CPU/memory/disk on its own schedule. Caddy is split into two site blocks with deliberately different exposure: the public block is reachable only through a Cloudflare Tunnel, while the admin block is published on the host's Tailscale address alone.",
                "implementation": "SQLAlchemy 2.0 async models with Alembic migrations, locale-aware endpoints, session-based admin authentication with bcrypt hashing and rate-limited login, React Router for client-side navigation, react-i18next for translations, Recharts for the analytics dashboard, and Motion for scroll and reveal animation. Analytics are first-party and privacy-conscious — the contact form records that a submission happened, never the field values — with a retention purge job to bound how long anything is kept.",
                "decisions": "Translation tables over column-suffix i18n, for zero-migration language additions. A monolith over microservices, given a single developer and low traffic. A dedicated infrastructure directory, to separate proxy and deployment concerns from application code. A standalone NOC component, treating observability as its own engineering concern rather than a backend afterthought. Version-controlled configuration, so infrastructure changes are reviewable and reproducible. Public exposure via tunnel only, so nothing listens on the home IP.",
                "challenges": "Coordinating behaviour across frontend, backend, authentication, analytics, monitoring, networking, container orchestration, and deployment means reasoning about failure modes a static site simply does not have: unavailable services, bad configuration, unreachable networks, failed authentication, and degraded infrastructure. The other constant tension was scope — keeping production-grade practices like session auth, rate limiting, and Docker network isolation without over-engineering a personal site.",
                "testing_desc": "pytest with httpx for backend API, contact-form, retention, proxy-header, and analytics-privacy tests; Vitest and React Testing Library for frontend components and hooks. A preflight script validates environment and service configuration before deployment, and CI runs the suites on push.",
                "results": "A working multi-service system: bilingual public portfolio, REST API backed by PostgreSQL, admin analytics dashboard, network-health monitoring, and reverse-proxy infrastructure — all orchestrated through Docker Compose and deployable to a self-hosted server.",
                "lessons": "Building the full database schema up front rather than iterating column by column avoided migration churn once real endpoints were wired up. More broadly, a system is not complete when the application code runs locally; it also has to be deployable, monitorable, understandable, and recoverable.",
            },
            Locale.es: {
                "title": "Plataforma de Portafolio de Ingeniería Full-Stack",
                "short_desc": "Este sitio: un portafolio bilingüe y autoalojado construido como aplicación multiservicio con frontend en React, backend en FastAPI, PostgreSQL, un monitor NOC independiente y Caddy detrás de un túnel de Cloudflare.",
                "overview": "En vez de tratar mi portafolio como una colección estática de páginas HTML, lo construí como un proyecto de ingeniería de software que demuestra las mismas habilidades de infraestructura y sistemas que el sitio describe. El repositorio está dividido en áreas dedicadas de frontend, backend, infraestructura, NOC/salud de red, documentación y scripts, con configuraciones de Docker Compose para desarrollo y producción, plantillas de entorno, un Makefile y automatización con GitHub workflows. La aplicación pública presenta biografía, habilidades, proyectos, certificaciones y contacto; el lado administrativo agrega analíticas propias y monitoreo de salud de red, de modo que el portafolio funciona también como ejercicio de observabilidad y despliegue.",
                "problem": "Un portafolio estático convencional puede mostrar proyectos, pero por sí mismo no demuestra mucha profundidad de ingeniería de software. El objetivo era que el portafolio fuera parte de la evidencia técnica —una aplicación mantenible, desplegable y monitoreada— y hacerlo bilingüe y autoalojado, sin constructores de sitios ni scripts de rastreo de terceros.",
                "requirements": "Ofrecer vistas de Inicio, Sobre mí, Habilidades, Proyectos, Certificaciones y Contacto, con páginas de detalle completas y no solo tarjetas. Mantener backend y frontend como responsabilidades separadas. Servir inglés y español desde el mismo modelo de contenido. Soportar un acceso administrativo con vistas de analíticas y monitoreo de servicios y salud de red. Ejecutarse en contenedores en desarrollo y producción, con la configuración de infraestructura en control de versiones y configuración por entorno. Incluir scripts de automatización y documentación mantenida.",
                "architecture": "Una SPA de React/TypeScript construida con Vite y servida por nginx, detrás de Caddy como proxy inverso. Un backend FastAPI expone una API REST versionada sobre PostgreSQL, usando SQLAlchemy 2.0 asíncrono con asyncpg y migraciones de Alembic. El contenido localizado vive en tablas de traducción indexadas por idioma en vez de columnas con sufijo, de modo que agregar un idioma no requiere migración. Un servicio NOC independiente muestrea el estado de los servicios, la alcanzabilidad de internet y los recursos de CPU, memoria y disco del host en su propio ciclo. Caddy se divide en dos bloques con exposición deliberadamente distinta: el bloque público solo es alcanzable a través de un túnel de Cloudflare, mientras que el bloque administrativo se publica únicamente en la dirección Tailscale del host.",
                "implementation": "Modelos asíncronos de SQLAlchemy 2.0 con migraciones de Alembic, endpoints sensibles al idioma, autenticación administrativa por sesión con hashing bcrypt e inicio de sesión con límite de intentos, React Router para la navegación del lado del cliente, react-i18next para las traducciones, Recharts para el panel de analíticas y Motion para las animaciones de scroll y aparición. Las analíticas son propias y respetuosas de la privacidad —el formulario de contacto registra que hubo un envío, nunca el contenido de los campos— con una tarea de purga por retención que acota cuánto tiempo se conserva cualquier dato.",
                "decisions": "Tablas de traducción en lugar de sufijos de columna, para agregar idiomas sin migraciones. Un monolito en vez de microservicios, dado un solo desarrollador y tráfico bajo. Un directorio de infraestructura dedicado, para separar las preocupaciones de proxy y despliegue del código de aplicación. Un componente NOC independiente, tratando la observabilidad como una preocupación de ingeniería propia y no como un añadido del backend. Configuración bajo control de versiones, para que los cambios de infraestructura sean revisables y reproducibles. Exposición pública solo por túnel, de modo que nada escuche en la IP del hogar.",
                "challenges": "Coordinar el comportamiento entre frontend, backend, autenticación, analíticas, monitoreo, redes, orquestación de contenedores y despliegue obliga a razonar sobre modos de falla que un sitio estático simplemente no tiene: servicios no disponibles, configuración incorrecta, redes inalcanzables, fallos de autenticación e infraestructura degradada. La otra tensión constante fue el alcance: sostener prácticas de nivel producción como sesiones, límites de tasa y aislamiento de red en Docker sin sobrediseñar un sitio personal.",
                "testing_desc": "pytest con httpx para pruebas de la API, el formulario de contacto, la retención, las cabeceras de proxy y la privacidad de las analíticas; Vitest y React Testing Library para componentes y hooks del frontend. Un script de preflight valida el entorno y la configuración de servicios antes del despliegue, y CI ejecuta las suites en cada push.",
                "results": "Un sistema multiservicio funcionando: portafolio público bilingüe, API REST respaldada por PostgreSQL, panel administrativo de analíticas, monitoreo de salud de red e infraestructura de proxy inverso, todo orquestado con Docker Compose y desplegable en un servidor propio.",
                "lessons": "Construir el esquema completo de la base de datos desde el inicio, en vez de iterar columna por columna, evitó churn de migraciones al conectar los endpoints reales. En general, un sistema no está terminado cuando el código corre en local: también tiene que ser desplegable, monitoreable, comprensible y recuperable.",
            },
        },
    },
    {
        "slug": "quadruped-robot",
        "category": "robotics",
        "github_url": "https://github.com/Rol0a/QuadrupedBot",
        "hero_image": "/images/Quadrupedbot.jpeg",
        "demo_url": None,
        "featured": True,
        "sort_order": 4,
        "technologies": ["ROS 2", "Gazebo", "Python", "C/C++", "UART / I2C / SPI"],
        "translations": {
            Locale.en: {
                "title": "Autonomous Quadruped Robot",
                "short_desc": "An ongoing quadruped robotics project integrating mechanical design, embedded electronics, ROS 2, Gazebo simulation, and sensor interfaces, targeting stable locomotion at roughly 4 km/h.",
                "overview": "I am developing a quadruped robot intended to achieve stable locomotion at a target speed of around 4 km/h. The project integrates mechanical design, embedded electronics, robotics software, simulation, sensing, and control. The software architecture is built around ROS 2 nodes so that control, communication, and sensor acquisition stay modular, and Gazebo is used to validate kinematic models and locomotion concepts before anything is deployed to physical hardware.",
                "problem": "Quadruped locomotion requires coordinated control across multiple actuators while maintaining balance, state awareness, and reliable communication between software and hardware.",
                "architecture": "The planned system uses distributed ROS 2 nodes communicating through topics, services, and messages, with separate components for sensor acquisition, state estimation, motion control, and future navigation functions.",
                "implementation": "Current development covers kinematic simulation, the ROS 2 node architecture, sensor and feedback integration, real-time data interfaces, and evaluation of localization, navigation, and motion-planning frameworks.",
                "results": "Active development, not a completed autonomous platform — locomotion and simulation work are underway, and autonomous navigation remains a development goal rather than a demonstrated capability.",
                "lessons": "The project is extending my embedded background into distributed robotics software, and it keeps reinforcing how much simulation, modular interfaces, and state estimation need to be in place before complex autonomous behaviour is attempted on physical hardware.",
            },
            Locale.es: {
                "title": "Robot Cuadrúpedo Autónomo",
                "short_desc": "Un proyecto de robótica cuadrúpeda en curso que integra diseño mecánico, electrónica embebida, ROS 2, simulación en Gazebo e interfaces de sensores, con el objetivo de una locomoción estable de unos 4 km/h.",
                "overview": "Estoy desarrollando un robot cuadrúpedo pensado para lograr una locomoción estable a una velocidad objetivo de alrededor de 4 km/h. El proyecto integra diseño mecánico, electrónica embebida, software de robótica, simulación, sensado y control. La arquitectura de software se construye alrededor de nodos de ROS 2 para que el control, la comunicación y la adquisición de sensores permanezcan modulares, y se usa Gazebo para validar modelos cinemáticos y conceptos de locomoción antes de llevar nada al hardware físico.",
                "problem": "La locomoción cuadrúpeda exige control coordinado entre múltiples actuadores manteniendo equilibrio, conciencia del estado y comunicación confiable entre software y hardware.",
                "architecture": "El sistema planificado usa nodos distribuidos de ROS 2 que se comunican mediante tópicos, servicios y mensajes, con componentes separados para adquisición de sensores, estimación de estado, control de movimiento y futuras funciones de navegación.",
                "implementation": "El desarrollo actual abarca simulación cinemática, la arquitectura de nodos de ROS 2, la integración de sensores y realimentación, interfaces de datos en tiempo real y la evaluación de marcos de localización, navegación y planificación de movimiento.",
                "results": "Desarrollo activo, no una plataforma autónoma terminada: el trabajo de locomoción y simulación está en curso, y la navegación autónoma sigue siendo un objetivo de desarrollo y no una capacidad demostrada.",
                "lessons": "El proyecto está extendiendo mi base en sistemas embebidos hacia el software de robótica distribuida, y refuerza continuamente cuánta simulación, interfaces modulares y estimación de estado deben estar en su lugar antes de intentar comportamientos autónomos complejos sobre hardware físico.",
            },
        },
    },
    {
        "slug": "electrodynamic-tether-deorbit",
        "status": "in_development",
        "category": "academic_research",
        "github_url": None,
        "demo_url": None,
        "featured": True,
        "sort_order": 5,
        "technologies": ["Python", "Numerical Modeling", "Orbital Mechanics"],
        "translations": {
            Locale.en: {
                "title": "Bare Electrodynamic Tether De-Orbit System",
                "short_desc": "Research and mathematical modeling of a bare electrodynamic tether for de-orbiting small satellites from low Earth orbit without conventional propellant.",
                "overview": "This research investigates bare electrodynamic tethers as an active end-of-life de-orbit technology for small satellites and CubeSats. An electrodynamic tether is a long conductive structure deployed from a spacecraft; as it moves through Earth's magnetic field and interacts electrically with the surrounding plasma, current flowing through the tether produces a Lorentz force. Designed for de-orbiting, that force removes orbital energy and gradually lowers the spacecraft's altitude without consuming propellant. My work focuses on a generalized mathematical model connecting satellite properties and orbital conditions to tether design parameters — length, cross-sectional area, current, generated Lorentz force, and torque.",
                "problem": "Small satellites and large constellations sharpen the need for reliable end-of-life disposal. Conventional propulsion adds mass, complexity, propellant requirements, and failure modes. The research asks whether a lightweight conductive tether can generate enough electromagnetic drag to meaningfully reduce orbital lifetime.",
                "requirements": "Model Lorentz-force generation. Relate tether dimensions and current to de-orbit performance. Account for orbital and geomagnetic conditions. Evaluate mechanical and electrical tether constraints. Estimate orbital-decay time. Produce a model that scales to different small-satellite cases rather than a single point design.",
                "implementation": "A 2U CubeSat in an approximately 600 km circular polar low-Earth orbit serves as the representative validation case. In the modeled configuration, a tape-type bare electrodynamic tether roughly 200 m long is evaluated as a candidate system, with simulations indicating de-orbit on the order of several years.",
                "challenges": "The problem spans orbital mechanics, electromagnetics, materials, structural constraints, spacecraft systems, plasma interaction, and numerical modeling at once. Open design questions include allowable stress for extremely thin tape geometries, structural analysis of long flexible conductors, and the combined effect of Lorentz and aerodynamic forces.",
                "lessons": "The project shows why aerospace problems are inherently multidisciplinary: a tether that is electrically effective must also be mechanically survivable, deployable, manufacturable, compatible with the host spacecraft, and predictable across changing orbital conditions.",
            },
            Locale.es: {
                "title": "Sistema de Desorbitado por Amarra Electrodinámica Desnuda",
                "short_desc": "Investigación y modelado matemático de una amarra electrodinámica desnuda para desorbitar satélites pequeños desde órbita baja terrestre sin propelente convencional.",
                "overview": "Esta investigación estudia las amarras electrodinámicas desnudas como tecnología activa de desorbitado al final de la vida útil para satélites pequeños y CubeSats. Una amarra electrodinámica es una estructura conductora larga desplegada desde una nave; al moverse por el campo magnético terrestre e interactuar eléctricamente con el plasma circundante, la corriente que circula por la amarra produce una fuerza de Lorentz. Diseñada para desorbitar, esa fuerza extrae energía orbital y reduce gradualmente la altitud de la nave sin consumir propelente. Mi trabajo se centra en un modelo matemático generalizado que relaciona las propiedades del satélite y las condiciones orbitales con los parámetros de diseño de la amarra: longitud, área transversal, corriente, fuerza de Lorentz generada y torque.",
                "problem": "Los satélites pequeños y las grandes constelaciones agudizan la necesidad de métodos confiables de disposición al final de la vida útil. La propulsión convencional agrega masa, complejidad, requisitos de propelente y modos de falla. La investigación pregunta si una amarra conductora ligera puede generar suficiente arrastre electromagnético para reducir de forma significativa la vida orbital.",
                "requirements": "Modelar la generación de fuerza de Lorentz. Relacionar las dimensiones y la corriente de la amarra con el desempeño de desorbitado. Considerar las condiciones orbitales y geomagnéticas. Evaluar las restricciones mecánicas y eléctricas de la amarra. Estimar el tiempo de decaimiento orbital. Producir un modelo escalable a distintos casos de satélites pequeños y no un diseño puntual.",
                "implementation": "Un CubeSat 2U en una órbita polar circular baja de aproximadamente 600 km sirve como caso representativo de validación. En la configuración modelada se evalúa como sistema candidato una amarra electrodinámica desnuda tipo cinta de unos 200 m de longitud, con simulaciones que indican un desorbitado del orden de varios años.",
                "challenges": "El problema abarca a la vez mecánica orbital, electromagnetismo, materiales, restricciones estructurales, sistemas espaciales, interacción con el plasma y modelado numérico. Entre las preguntas de diseño abiertas están el esfuerzo admisible para geometrías de cinta extremadamente delgadas, el análisis estructural de conductores largos y flexibles, y el efecto combinado de las fuerzas de Lorentz y aerodinámicas.",
                "lessons": "El proyecto muestra por qué los problemas aeroespaciales son inherentemente multidisciplinarios: una amarra eléctricamente efectiva también debe ser mecánicamente resistente, desplegable, manufacturable, compatible con la nave anfitriona y predecible frente a condiciones orbitales cambiantes.",
            },
        },
    },
    {
        "slug": "fedora-linux-environment",
        "status": "in_development",
        "category": "devops_infra",
        "github_url": None,
        "demo_url": None,
        "featured": False,
        "sort_order": 6,
        "technologies": [
            "Fedora Linux",
            "Bash",
            "SSH",
            "Docker",
            "Docker Compose",
            "KVM / Virtual Machines",
            "Git",
        ],
        "translations": {
            Locale.en: {
                "title": "Fedora Linux Server and Development Environment",
                "short_desc": "A personally maintained Fedora Linux environment used for software, networking, embedded development, automation, virtual machines, and deployment experimentation.",
                "overview": "I maintain a Fedora-based Linux environment as a practical platform for learning system administration and supporting my engineering projects. I have written Bash scripts to automate maintenance, deployment, and virtual-machine tasks; configured networking services and development tooling; and used Linux as the host for software, embedded toolchains, containers, and infrastructure experiments — including this portfolio's own stack.",
                "problem": "Create a repeatable engineering environment that supports software development, embedded tooling, networking experiments, virtual machines, automation, and self-hosted services without depending entirely on managed platforms.",
                "implementation": "The environment combines Linux administration with Bash scripting, networking, development tooling, virtualization, and containerized services, and doubles as the test bed for my portfolio infrastructure and other projects.",
                "lessons": "Maintaining my own environment has made infrastructure failures and configuration issues tangible. It has sharpened my understanding of permissions, networking, processes, services, automation, deployment, and — most usefully — the difference between an application-level problem and an operating-system-level one.",
            },
            Locale.es: {
                "title": "Servidor y Entorno de Desarrollo en Fedora Linux",
                "short_desc": "Un entorno Fedora Linux mantenido de forma personal para software, redes, desarrollo embebido, automatización, máquinas virtuales y experimentación con despliegues.",
                "overview": "Mantengo un entorno Linux basado en Fedora como plataforma práctica para aprender administración de sistemas y sostener mis proyectos de ingeniería. He escrito scripts en Bash para automatizar tareas de mantenimiento, despliegue y máquinas virtuales; he configurado servicios de red y herramientas de desarrollo; y he usado Linux como anfitrión para software, cadenas de herramientas embebidas, contenedores y experimentos de infraestructura, incluida la propia pila de este portafolio.",
                "problem": "Crear un entorno de ingeniería repetible que soporte desarrollo de software, herramientas embebidas, experimentos de red, máquinas virtuales, automatización y servicios autoalojados sin depender por completo de plataformas gestionadas.",
                "implementation": "El entorno combina administración de Linux con scripting en Bash, redes, herramientas de desarrollo, virtualización y servicios en contenedores, y funciona además como banco de pruebas para la infraestructura de mi portafolio y otros proyectos.",
                "lessons": "Mantener mi propio entorno ha hecho tangibles las fallas de infraestructura y los problemas de configuración. Ha afinado mi comprensión de permisos, redes, procesos, servicios, automatización y despliegue y, sobre todo, de la diferencia entre un problema a nivel de aplicación y uno a nivel de sistema operativo.",
            },
        },
    },
]


async def seed_admin_user(db) -> None:
    existing = (
        await db.execute(select(AdminUser).where(AdminUser.username == settings.admin_username))
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(AdminUser(username=settings.admin_username, password_hash=hash_password(settings.admin_password)))
    await db.flush()


async def seed_certifications(db) -> None:
    for entry in CERTIFICATIONS:
        existing = (
            await db.execute(select(Certification).where(Certification.slug == entry["slug"]))
        ).scalar_one_or_none()
        if existing is not None:
            continue

        certification = Certification(
            slug=entry["slug"],
            issuer=entry["issuer"],
            issue_date=date.fromisoformat(entry["issue_date"]),
            expiry_date=date.fromisoformat(entry["expiry_date"]) if entry["expiry_date"] else None,
            credential_url=entry["credential_url"],
            featured=entry["featured"],
            sort_order=entry["sort_order"],
        )
        certification.translations = [
            CertificationTranslation(locale=locale, **fields) for locale, fields in entry["translations"].items()
        ]
        db.add(certification)

    await db.flush()


async def seed_demo_analytics_events(db) -> None:
    """Synthetic traffic for the M10 admin dashboard.

    This is NOT the M8 event-recording pipeline — no such pipeline exists yet, so
    real visits aren't tracked. This just seeds plausible-looking history so the
    dashboard's aggregation queries and charts can actually be exercised. Skips
    entirely if the table already has rows, so re-running `seed.py` never piles
    up duplicate fake traffic.
    """
    existing_count = (await db.execute(select(func.count()).select_from(AnalyticsEvent))).scalar_one()
    if existing_count > 0:
        return

    project_slugs = [entry["slug"] for entry in PROJECTS]
    rng = random.Random(42)
    events: list[AnalyticsEvent] = []
    now = datetime.now(timezone.utc)

    for day_offset in range(30, -1, -1):
        day = now - timedelta(days=day_offset)
        sessions_today = [str(uuid.uuid4()) for _ in range(rng.randint(3, 14))]

        for session_id in sessions_today:
            locale = rng.choices([Locale.en, Locale.es], weights=[7, 3])[0]
            visit_start = day.replace(
                hour=rng.randint(0, 23), minute=rng.randint(0, 59), second=rng.randint(0, 59)
            )

            events.append(
                AnalyticsEvent(
                    event_type=AnalyticsEventType.page_view,
                    session_id=session_id,
                    locale=locale,
                    created_at=visit_start,
                )
            )

            if rng.random() < 0.55:
                slug = rng.choice(project_slugs)
                events.append(
                    AnalyticsEvent(
                        event_type=AnalyticsEventType.project_view,
                        session_id=session_id,
                        project_slug=slug,
                        locale=locale,
                        created_at=visit_start + timedelta(seconds=rng.randint(5, 120)),
                    )
                )
                if rng.random() < 0.4:
                    events.append(
                        AnalyticsEvent(
                            event_type=AnalyticsEventType.github_click,
                            session_id=session_id,
                            project_slug=slug,
                            locale=locale,
                            created_at=visit_start + timedelta(seconds=rng.randint(30, 180)),
                        )
                    )

            if rng.random() < 0.15:
                events.append(
                    AnalyticsEvent(
                        event_type=AnalyticsEventType.cv_download,
                        session_id=session_id,
                        locale=locale,
                        created_at=visit_start + timedelta(seconds=rng.randint(10, 200)),
                    )
                )

            if rng.random() < 0.08:
                events.append(
                    AnalyticsEvent(
                        event_type=AnalyticsEventType.contact_click,
                        session_id=session_id,
                        locale=locale,
                        created_at=visit_start + timedelta(seconds=rng.randint(10, 240)),
                    )
                )

    db.add_all(events)
    await db.flush()
    print(f"Seeded {len(events)} synthetic analytics events (demo data for M10 — not real traffic).")


async def seed() -> None:
    async with async_session_factory() as db:
        await seed_admin_user(db)
        await seed_certifications(db)

        tech_by_name: dict[str, Technology] = {}
        for name, category in TECHNOLOGIES:
            existing = (await db.execute(select(Technology).where(Technology.name == name))).scalar_one_or_none()
            if existing is None:
                existing = Technology(name=name, category=category)
                db.add(existing)
            tech_by_name[name] = existing

        # sort_order comes from list position: the skills endpoint sorts by
        # (category, sort_order), so SKILLS' order is the on-page order.
        for index, (name, category, featured_rank) in enumerate(SKILLS):
            existing = (await db.execute(select(Skill).where(Skill.name == name))).scalar_one_or_none()
            if existing is None:
                db.add(
                    Skill(name=name, category=category, featured_rank=featured_rank, sort_order=index)
                )

        await db.flush()

        for entry in PROJECTS:
            existing = (
                await db.execute(select(Project).where(Project.slug == entry["slug"]))
            ).scalar_one_or_none()
            if existing is not None:
                continue

            project = Project(
                slug=entry["slug"],
                category=entry["category"],
                # Defaults to complete — a project only declares a status when
                # it is *not* finished, so the common case stays uncluttered.
                status=entry.get("status", "complete"),
                github_url=entry["github_url"],
                demo_url=entry["demo_url"],
                featured=entry["featured"],
                sort_order=entry["sort_order"],
            )
            project.technologies = [tech_by_name[name] for name in entry["technologies"]]
            project.translations = [
                ProjectTranslation(locale=locale, **fields) for locale, fields in entry["translations"].items()
            ]
            # Only record an image row when a real asset exists. The old default
            # here fabricated `/uploads/images/<slug>-hero.webp` for every
            # project without one, so the API returned a non-null
            # hero_image_url, the browser fetched it, nginx 404'd, and the UI
            # recovered only through the <img> onError path — a runtime patch
            # for bad data. With no row, hero_image_url is null and both
            # ProjectShowcase and ProjectDetail render their placeholder
            # directly: no wasted request, no 404s in the access log.
            #
            # A project gains an image by being given a `hero_image` key
            # pointing at a file that actually ships, never by this seed
            # guessing a path for it.
            hero_image = entry.get("hero_image")
            # Defaults to the English title, which reads fine for a build photo;
            # a screenshot needs to say what it actually shows, so entries can
            # override it.
            hero_alt = entry.get("hero_alt") or entry["translations"][Locale.en]["title"]
            project.images = (
                [
                    ProjectImage(
                        url=hero_image,
                        alt_text=hero_alt,
                        is_hero=True,
                        sort_order=0,
                    )
                ]
                if hero_image
                else []
            )
            db.add(project)

        await db.flush()
        await seed_demo_analytics_events(db)

        await db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
