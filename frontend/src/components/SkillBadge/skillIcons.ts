/**
 * Skill name → icon key. Keys are the exact `skills.name` values seeded by
 * `scripts/seed.py`, because that is what the API returns.
 *
 * Coupling display to a data value is a real tradeoff, and it is the right one
 * here: the alternative is an `icon` column, which makes renaming a skill a
 * migration instead of a one-line edit, for a mapping that is purely
 * presentational. A name with no entry falls back to the neutral `dot` mark, so
 * the failure mode of a rename is a plain badge, never a crash or a gap.
 *
 * Several engineering concepts intentionally share a glyph (SPI and I2C are both
 * `bus`; FDM and SLA are both `printer3d`) — inventing a distinct pictogram for
 * every serial protocol would produce icons nobody can read at 14px.
 */
export const SKILL_ICONS: Record<string, string> = {
  // Programming
  Python: "python",
  C: "c",
  "C++": "cplusplus",
  "Embedded C": "chip",
  Bash: "gnubash",
  TypeScript: "typescript",
  SQL: "database",

  // Embedded Systems
  ESP32: "espressif",
  Arduino: "arduino",
  ATmega328P: "chip",
  UART: "terminal",
  SPI: "bus",
  I2C: "bus",
  PWM: "wave",
  Bluetooth: "bluetooth",
  "Serial Communication": "terminal",
  "Sensor Acquisition": "sensor",
  Telemetry: "wave",
  "Motor Control": "cog",

  // Hardware Design — Altium has no Simple Icons mark, so it takes the
  // circuit-board concept glyph rather than a look-alike brand logo.
  "Altium Designer": "board",
  "PCB Design": "board",
  "PCB Bring-up": "wrench",
  "Autodesk Fusion 360": "autodesk",
  SolidWorks: "dassaultsystemes",
  "Autodesk Inventor": "autodesk",
  "FDM Printing": "printer3d",
  "SLA Printing": "printer3d",
  "Laser Cutting": "laser",
  Soldering: "wrench",
  "DFM / DFA": "checklist",
  "Rapid Prototyping": "cube",

  // Robotics — MATLAB, Simulink and Gazebo have no Simple Icons marks either.
  "ROS 2": "ros",
  Gazebo: "cube",
  MATLAB: "curve",
  Simulink: "blocks",
  "Robot Simulation": "cube",
  "Sensor Integration": "sensor",
  Kinematics: "joint",
  "Control Systems": "sliders",

  // Networks
  IPv4: "network",
  IPv6: "network",
  "TCP/IP": "network",
  DNS: "globe",
  DHCP: "server",
  SSH: "terminal",
  "LAN / WAN": "network",
  Routing: "route",
  Switching: "switching",
  VLANs: "layers",
  "Linux Networking": "linux",
  "Network Security": "shield",
  Cisco: "cisco",
  Fortinet: "fortinet",

  // Web & Backend
  React: "react",
  FastAPI: "fastapi",
  "REST APIs": "braces",
  PostgreSQL: "postgresql",
  SQLite: "sqlite",
  JSON: "json",
  HTML: "html5",
  CSS: "css",

  // Linux & DevOps
  Linux: "linux",
  Fedora: "fedora",
  Git: "git",
  GitHub: "github",
  Docker: "docker",
  "Docker Compose": "docker",
  Nginx: "nginx",
  "Reverse Proxy": "route",
  "Virtual Machines": "server",

  // Data & ML
  Pandas: "pandas",
  NumPy: "numpy",
  Matplotlib: "curve",
  "Data Processing": "blocks",
  "Predictive Analytics": "trending",
  "Digital Twins": "twin",
  "Data Acquisition": "sensor",
};

export const FALLBACK_ICON = "dot";
