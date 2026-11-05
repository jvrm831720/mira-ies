# Self-operated MIRA Education Engine (staging): Frappe Framework + ERPNext + Education.
# Pinned upstream ERPNext v15 image, with Education pinned to audited source SHA.
# This image is only one part of the Render Blueprint. MariaDB, Redis and
# persistent sites storage MUST be provisioned before boot.
FROM frappe/erpnext:v15.124.3

USER root
RUN apt-get update \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends supervisor \
  && rm -rf /var/lib/apt/lists/*
RUN install -d -o frappe -g 0 /opt/mira

USER frappe
WORKDIR /home/frappe/frappe-bench

# The Education repo is the GPL-3.0 app pinned in vendor/frappe/vendor-lock.json.
# Do not let an unreviewed upstream branch update the deployed code.
RUN git clone --branch version-15.1 --depth 1 https://github.com/frappe/education.git /tmp/mira-education-source \
    && cd /tmp/mira-education-source \
    && git fetch --depth 1 origin 1f89e2e827d61f62f430a5343376837fdc43213f \
    && git checkout --detach 1f89e2e827d61f62f430a5343376837fdc43213f \
    && cd /home/frappe/frappe-bench \
    && ln -s ../assets sites/assets \
    && bench get-app --branch version-15.1 education /tmp/mira-education-source \
    && bench build --app education \
    && rm -rf /tmp/mira-education-source \
    && rm -f sites/assets

COPY --chown=frappe:0 infra/frappe-render/supervisord.conf /opt/mira/supervisord.conf
COPY --chown=frappe:0 infra/frappe-render/bootstrap.sh /opt/mira/bootstrap.sh

USER root
RUN chmod 0755 /opt/mira/bootstrap.sh
EXPOSE 10000
ENTRYPOINT ["/bin/bash", "/opt/mira/bootstrap.sh"]
