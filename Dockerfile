# syntax=docker/dockerfile:1
FROM odoo:19.0 AS addons

USER root
WORKDIR /mnt/extra-addons

# Baked config has no secrets. dbfilter and admin_passwd are set where the container runs.
COPY config/odoo.conf.example /etc/odoo/odoo.conf
COPY scripts/discover-addons.sh /usr/local/bin/discover-addons.sh
COPY scripts/check-addon-depends.py /usr/local/bin/check-addon-depends.py
RUN chmod 755 /usr/local/bin/discover-addons.sh /usr/local/bin/check-addon-depends.py

# Bind-mount custom_addons. This RUN commits the flattened modules and
# /opt/addon-reqs only; submodule wrappers are removed before the layer is saved.
# Base image VOLUME /mnt/extra-addons: after first run, renew anonymous volumes
# to pick up a rebuilt image:
#   docker compose up -d --force-recreate --renew-anon-volumes
RUN --mount=type=bind,source=custom_addons,target=/src,readonly \
    cp -a /src/. /mnt/extra-addons/ \
 && /usr/local/bin/discover-addons.sh stage-requirements /mnt/extra-addons /opt/addon-reqs \
 && /usr/local/bin/discover-addons.sh flatten /mnt/extra-addons \
 && /usr/local/bin/discover-addons.sh apply-config /mnt/extra-addons /etc/odoo/odoo.conf \
 && python3 /usr/local/bin/check-addon-depends.py

FROM odoo:19.0

USER root
RUN pip3 install --break-system-packages setuptools wheel

# System lib for reportlab QR/barcode rendering (rlPyCairo backend,
# required by ps_mfg production report). Needed at OS level, pip cannot provide it.
RUN apt-get update && apt-get install -y --no-install-recommends libcairo2 && rm -rf /var/lib/apt/lists/*

COPY scripts/discover-addons.sh /usr/local/bin/discover-addons.sh
RUN chmod 755 /usr/local/bin/discover-addons.sh

# Changes only when a submodule requirements.txt changes.
COPY --from=addons /opt/addon-reqs /opt/addon-reqs
RUN --mount=type=cache,target=/root/.cache/pip \
    /usr/local/bin/discover-addons.sh install-requirements /opt/addon-reqs

COPY --from=addons /etc/odoo/odoo.conf /etc/odoo/odoo.conf
COPY --from=addons --chown=odoo:odoo /mnt/extra-addons /mnt/extra-addons

WORKDIR /
USER odoo
