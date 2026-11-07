Fable k3s bundle
================

Generated for primary node fablenode01 (192.168.160.121).

What is in here
  manifests/     Kubernetes objects. 10-secrets.yaml is private.
  config/        The bot config with cluster addresses filled in.
  docker/        Image definitions.
  build-images.sh
  apply.sh
  restore-databases.sh
  JOIN-NODES.txt

Order on fablenode01
  1. Confirm the database disk is mounted at /mnt/postgres.
  2. ./build-images.sh
  3. ./apply.sh
  4. ./restore-databases.sh     only if you chose to load dumps
  5. sudo kubectl -n fable logs deploy/fable-bot -c fable -f

PostgreSQL data directory: /mnt/postgres/data
That directory is kept across redeploys. Delete it only when you intend to
wipe the game databases.

The bot pod is a single copy. Do not raise replicas above 1. Two copies would
both log in as the same Discord bot.

config.toml changes made for the cluster
  postgres_host = "postgres"
  redis_host = "redis"
  okapi_url = "http://127.0.0.1:3010"    only if OkAPI was selected
  is_beta = true
  additional_shards = 1
  shards_per_cluster = 2

Everything else was copied from the existing config.toml.

Dev bot (fable-bot-dev)
  Separate deployment in namespace fable. The live bot is fable-bot.
  Scaling the dev deployment does not affect the live one.
  It uses its own Discord token and the FableDev and IdleRPGDev databases.
  Those two were refreshed from the live databases on 2026-11-07. They are
  not empty.
  Replicas must be 0 or 1. Never higher.

  On fablenode01:
    Start: sudo k3s kubectl -n fable scale deploy/fable-bot-dev --replicas=1
    Stop:  sudo k3s kubectl -n fable scale deploy/fable-bot-dev --replicas=0
