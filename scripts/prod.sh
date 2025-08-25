#!/bin/bash

echo "Starting production mode..."

# Run migrations
python manage.py migrate

# Collect static files in Frontend directory
python manage.py collectstatic --noinput --clear

# Start with Gunicorn
gunicorn --bind 0.0.0.0:8000 --workers 3 backend.wsgi:application
