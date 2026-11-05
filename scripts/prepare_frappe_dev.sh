#!/usr/bin/env bash
# Prepare an isolated local Frappe/ERPNext/Education bench from MIRA-pinned sources.
# No sites/databases created, no remote sends/payments, no MIRA migrations.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH_DIR="${MIRA_FRAPPE_BENCH_DIR:-$ROOT/.local/frappe-bench}"

if [[ "${EUID}" -eq 0 ]]; then
  echo "Run Bench as an unprivileged Linux/WSL user, not root." >&2
  exit 2
fi
for bin in git python3 bench; do
  command -v "$bin" >/dev/null || {
    echo "Missing executable: $bin. Install Frappe Bench prerequisites inside Linux/WSL2." >&2
    exit 2
  }
done
if [[ -e "$BENCH_DIR" ]]; then
  echo "The target already exists; refusing to overwrite: $BENCH_DIR" >&2
  exit 2
fi

echo "1/4 Fetching pinned MIRA-owned source distribution..."
git -C "$ROOT" submodule update --init --recursive
python3 "$ROOT/scripts/verify_frappe_vendor.py" --require-checkout

echo "2/4 Bootstrapping separate Bench from locally pinned Frappe source..."
bench init --frappe-path "$ROOT/vendor/frappe/framework" --frappe-branch version-15 "$BENCH_DIR"

echo "3/4 Installing ERPNext and Education source into Bench (not site databases)..."
(
  cd "$BENCH_DIR"
  bench get-app --branch version-15 erpnext "$ROOT/vendor/frappe/erpnext"
  bench get-app --branch version-15.1 education "$ROOT/vendor/frappe/education"
  echo "4/4 Installed app versions:"
  bench version
)

cat <<'INSTRUCTIONS'

Bench source is prepared. Next steps are MANUAL and must use a new,
isolated development site and database (never MIRA's production database):

  cd <your bench dir>
  bench new-site ies-dev.localhost
  bench --site ies-dev.localhost install-app erpnext
  bench --site ies-dev.localhost install-app education

Review the pinned apps' required Python/Node/MariaDB/Redis versions before
running these commands. Do not enable Payments/Print Designer or contact
students. Do not expose Frappe's Administrator credentials to Next.js.
INSTRUCTIONS
