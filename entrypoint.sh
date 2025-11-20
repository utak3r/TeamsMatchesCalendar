#!/bin/sh

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Execute the CMD passed to the container (the Gunicorn command)
exec "$@"
