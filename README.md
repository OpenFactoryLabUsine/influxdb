
# Installation

1) `cp .env.dev .env`
2) Compléter `EXPLORER_SESSION_SECRET_KEY` par n'importe quelle chaine de charactères.
3) Compléter `INFLUXDB3_LICENSE_EMAIL` par un email. Au lancement du container, une clé pour la license `Home` sera associé à cet email
4) Ne pas toucher à `INFLUXDB3_LICENSE_TYPE`
5) Compléter `KAFKA_BROKER` par l'IP de la machine hebergeant le topic suivi du port `:9094`
5) Lancer une première fois le projet avec : `docker compose up --build -d`
6) Générer un token d'InfluxDB3 qui sera utilisé par telegraf avec : `docker exec -it openfactory-influxdb-influxdb3-enterprise-1 influxdb3 create token --admin`
7) Copier ce token dans le `.env` -> `INFLUXDB3_TOKEN`
8) Supprimer le container telegraf : `docker rm -f telegraf`
9) Redéployer le compose : `docker compose up --build -d`
10) Aller sur l'interface d'admin d'Influxdb3 : `http://IP:8888`
11) Dans `Configure` -> `Servers` -> Appuyer sur `Add Server` -> 
    - Ce que vous voulez dans `Server Name`, 
    - `influxdb-influxdb3-enterprise-1:8181` dans `Server URL`, 
    - Le token que vous avez précédemment généré dans `Token`
12) Dans `Manage Databases` -> `Create New`
    - Une `ephemeral`
    - Une `lifetime`
13) Vérifier les logs de telegraf avec `docker logs -f telegraf` pour vérifier que les données sont biens écrites et qu'une table `AssetsMetrics` a bien été créée dans la DB `ephemeral`