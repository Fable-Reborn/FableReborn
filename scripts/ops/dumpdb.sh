#!/bin/bash
echo "Removing old schema..."
rm data/db/schema.sql
touch data/db/schema.sql
echo "Dumping database $1..."
podman exec $1 pg_dump -U postgres $2 --schema-only > data/db/schema.sql.tmp
echo "Adding license header..."
cat <(cat assets/licenses/agpl_header_sql.txt) data/db/schema.sql.tmp > data/db/schema.sql
rm data/db/schema.sql.tmp
