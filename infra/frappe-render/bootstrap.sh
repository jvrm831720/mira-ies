#!/usr/bin/env bash
# Render private-service startup: do not launch without persistent sites disk,
# separate MariaDB, Key Value and uniquely configured site.
set -Eeuo pipefail
umask 0077

BENCH=/home/frappe/frappe-bench
SITE="${MIRA_EDUCATION_SITE_NAME:-}"
: "${MIRA_MARIADB_HOST:?MIRA_MARIADB_HOST required}"
: "${MIRA_MARIADB_ROOT_PASSWORD:?MIRA_MARIADB_ROOT_PASSWORD required}"
: "${MIRA_REDIS_CACHE:?MIRA_REDIS_CACHE required}"
: "${MIRA_REDIS_QUEUE:?MIRA_REDIS_QUEUE required}"
: "${MIRA_FRAPPE_ADMIN_PASSWORD:?MIRA_FRAPPE_ADMIN_PASSWORD required}"
: "${MIRA_PERSISTENT_SITES_PATH:?Persistent sites disk required}"

if [[ "$MIRA_PERSISTENT_SITES_PATH" != "$BENCH/sites" ]] || ! mountpoint -q "$BENCH/sites"; then
  echo "ERROR: persistent disk is not mounted at $BENCH/sites; refusing ephemeral site startup." >&2
  exit 1
fi
if [[ ! "$SITE" =~ ^[a-z0-9][a-z0-9.-]{1,198}[a-z0-9]$ ]] || [[ "$SITE" == *..* ]]; then
  echo "ERROR: invalid MIRA_EDUCATION_SITE_NAME" >&2
  exit 1
fi

# Mount directory ownership is configured only at startup, never reset all
# permissions of the site data on every deploy.
chown frappe:0 "$BENCH/sites"
chmod 0770 "$BENCH/sites"
cd "$BENCH"

as_frappe() { runuser -u frappe -- "$@"; }

# Recreate only non-secret links/config; Site data persists across deploys.
if [[ -L sites/assets ]]; then rm sites/assets; fi
if [[ ! -e sites/assets ]]; then ln -s ../assets sites/assets; fi
as_frappe bash -c 'printf "frappe\nerpnext\neducation\n" > sites/apps.txt'

echo "Setting common configuration for private MIRA Frappe site..."
as_frappe bench set-config -g db_host "$MIRA_MARIADB_HOST"
as_frappe bench set-config -gp db_port 3306
as_frappe bench set-config -g redis_cache "$MIRA_REDIS_CACHE"
as_frappe bench set-config -g redis_queue "$MIRA_REDIS_QUEUE"
as_frappe bench set-config -g redis_socketio "$MIRA_REDIS_QUEUE"
as_frappe bench set-config -gp socketio_port 9000
as_frappe bench set-config -g server_script_enabled 0
as_frappe bench set-config -g allow_cors '[]'

# This is a staging site ONLY. The app cannot infer which real tenant a
# student belongs to, and no real student imports are performed here.
if [[ ! -f "sites/$SITE/site_config.json" ]]; then
  echo "Creating isolated Education sandbox site (no customer data)."
  as_frappe bench new-site "$SITE" \
    --mariadb-user-host-login-scope='%' \
    --db-root-username=root \
    --db-root-password="$MIRA_MARIADB_ROOT_PASSWORD" \
    --admin-password="$MIRA_FRAPPE_ADMIN_PASSWORD" \
    --install-app erpnext
  as_frappe bench --site "$SITE" install-app education
else
  if ! as_frappe bench --site "$SITE" list-apps | grep -Eq '^education([[:space:]]|$)'; then
    echo "Existing site missing Education app; manual recovery required."
    exit 1
  fi
fi

# Fail closed if required apps were not installed. Avoid starting HTTP while
# schema/install is incomplete (migrations require separate reviewed rollout).
for app in frappe erpnext education; do
  if ! as_frappe bench --site "$SITE" list-apps | grep -Eq "^$app([[:space:]]|$)"; then
    echo "ERROR: missing installed app: $app" >&2
    exit 1
  fi
done

echo "MIRA Education Engine apps validated. Starting private HTTP + queues + scheduler."
exec /usr/bin/supervisord -n -c /opt/mira/supervisord.conf
