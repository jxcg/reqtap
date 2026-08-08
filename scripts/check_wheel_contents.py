"""Assert the built wheel carries the files reqtap needs at runtime.

Run after `python -m build --wheel`. Kept out of the test suite on purpose:
tests run against an editable install, which reads the source tree and so can
never see a packaging mistake.
"""

import sys
import zipfile
from pathlib import Path

# Files that are not Python modules, so nothing imports them and no test
# notices when packaging drops them. The dashboard 500s without this one.
REQUIRED_MEMBERS = ["reqtap/dashboard/index.html"]


def find_wheel(dist_directory: Path) -> Path:
    """Return the single wheel in dist/, or exit with a readable message."""
    wheels = sorted(dist_directory.glob("*.whl"))
    if len(wheels) != 1:
        sys.exit(f"expected exactly one wheel in {dist_directory}, found {len(wheels)}")
    return wheels[0]


def main() -> None:
    wheel = find_wheel(Path("dist"))
    members = set(zipfile.ZipFile(wheel).namelist())

    missing = [name for name in REQUIRED_MEMBERS if name not in members]
    if missing:
        sys.exit(f"{wheel.name} is missing {missing}")

    print(f"ok: {wheel.name} contains {REQUIRED_MEMBERS}")


if __name__ == "__main__":
    main()
