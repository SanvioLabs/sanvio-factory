# Grafana with the DuckDB data source and the usage store's provisioning (SPEC-004 REQ-022), for the local
# compose file and the cloud task alike. Both the image and the plugin are pinned: the image by digest, the
# plugin by version and the SHA-256 of its release zip. Neither is vendored in this repo.
# The Ubuntu image, not the default Alpine one: the plugin's backend is built against glibc and won't start on musl.
FROM grafana/grafana-oss:13.0.2-ubuntu@sha256:06d0bf32de77a7cf32eb8c705332c8f573fc07441d95f29f26f39e4deb98e48f

ARG PLUGIN_VERSION=0.4.6
ARG PLUGIN_SHA256=3464c8ee0a60eb49bdbd778caf103112dd710a234aa26e429faf813f449a8a57

USER root
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends unzip wget ca-certificates >/dev/null \
 && rm -rf /var/lib/apt/lists/* \
 && wget -q -O /tmp/plugin.zip \
      "https://github.com/motherduckdb/grafana-duckdb-datasource/releases/download/v${PLUGIN_VERSION}/motherduck-duckdb-datasource-${PLUGIN_VERSION}.zip" \
 && echo "${PLUGIN_SHA256}  /tmp/plugin.zip" | sha256sum -c - \
 && mkdir -p /opt/grafana-plugins \
 && unzip -q /tmp/plugin.zip -d /opt/grafana-plugins \
 && rm /tmp/plugin.zip \
 && chown -R grafana /opt/grafana-plugins
USER grafana

# /var/lib/grafana is a volume in the base image, so a plugin unpacked there at build time is lost. Grafana's
# own default plugins are left uninstalled, so it makes no calls out to fetch them.

ENV GF_PATHS_PLUGINS=/opt/grafana-plugins \
    GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS=motherduck-duckdb-datasource \
    GF_PLUGINS_PREINSTALL_DISABLED=true \
    GF_ANALYTICS_REPORTING_ENABLED=false \
    GF_ANALYTICS_CHECK_FOR_UPDATES=false \
    GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false \
    GF_NEWS_NEWS_FEED_ENABLED=false \
    USAGE_INIT=""

COPY grafana/provisioning /etc/grafana/provisioning
COPY grafana/dashboards /etc/grafana/dashboards
