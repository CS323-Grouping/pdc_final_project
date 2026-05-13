"""
Release and build versioning (single source of truth).

WHERE TO BUMP THE BUILD
-----------------------
Edit the numeric constants in the **CONFIG** section below:

- ``VERSION_MAJOR`` / ``VERSION_MINOR`` / ``VERSION_PATCH`` — semantic version
  shown to players (e.g. 0.2.0 for a feature release).

- ``BUILD_NUMBER`` — increment for **every** new packaged build (PyInstaller EXE,
  zip you hand to testers), even if the semver triple is unchanged (e.g. rebuild,
  hotfix asset, config change).

Optional: ``VERSION_SUFFIX`` for non-release strings like ``dev`` or ``rc1``
(appended to semver in ``semver_string()``).

Do not edit version numbers elsewhere; import from this module if you need them.
"""

# =============================================================================
#  CONFIG — change version / build for each release or packaged EXE
# =============================================================================

VERSION_MAJOR = 0
VERSION_MINOR = 4
VERSION_PATCH = 8

# Increment for each new build you distribute (EXE / zip). Independent of semver.
BUILD_NUMBER = 14

# Empty string for releases. Otherwise e.g. "dev", "rc1" (shown after semver).
VERSION_SUFFIX = ""

APP_NAME = "Skyward Race LAN Multiplayer"

# =============================================================================


def version_tuple() -> tuple[int, int, int]:
    return (VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH)


def semver_string() -> str:
    base = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"
    if VERSION_SUFFIX:
        return f"{base}-{VERSION_SUFFIX}"
    return base


def display_version() -> str:
    """Semver + build number (window title, logs)."""
    return f"{semver_string()} build {BUILD_NUMBER}"


def window_title() -> str:
    return f"{APP_NAME} — v{display_version()}"


def cli_version_string() -> str:
    """Single line for ``--version``."""
    return f"{APP_NAME} {display_version()}"


def log_startup_line() -> str:
    """Line for logging after log file is configured."""
    return f"{APP_NAME} client {display_version()}"


def windows_file_version_quad() -> tuple[int, int, int, int]:
    """
    Four nonnegative ints for Windows FILEVERSION / PRODUCTVERSION (16 bits each).

    Maps (major, minor, patch, build). If BUILD_NUMBER ever exceeds 65535,
    clamp or remap in SkywardRaceLAN.spec when generating a VSVersionInfo file.
    """

    return (VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH, min(BUILD_NUMBER, 65535))
