# On part de l'image officielle Telegraf (basée sur Debian)
FROM telegraf:latest

USER root

# Installation de Python, pip, et des dépendances système pour ODBC
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    curl apt-transport-https gnupg2 unixodbc-dev

# Installation du driver Microsoft ODBC 17 pour SQL Server
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17

# Préparation de l'environnement Python dans le conteneur
RUN python3 -m venv /opt/venv
RUN /opt/venv/bin/pip install pyodbc

# Copie du script dans le conteneur
COPY telegraf/router.py /etc/telegraf/router.py

# On redonne les droits à l'utilisateur telegraf
RUN chown -R telegraf:telegraf /etc/telegraf /opt/venv

USER telegraf