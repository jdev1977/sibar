# Sourced by the hooks. find_python ROOT sets $python to a working Python 3.9+,
# or reports the problem and returns 1 so that the caller can block.

find_python() {
    # Skip candidates that exist but do not run (e.g. the Windows Store alias).
    for python in "$1/.venv/Scripts/python.exe" "$1/.venv/bin/python" python3 python py; do
        if "$python" -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
            return 0
        fi
    done
    echo "secret-scan: no usable Python (3.9+) found; blocked. See docs/secrets.md." >&2
    return 1
}
