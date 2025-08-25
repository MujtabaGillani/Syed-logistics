#!/bin/bash

echo "Starting development mode..."

# Run migrations
python manage.py migrate

# Collect static files in Frontend directory
python manage.py collectstatic --noinput --clear

# Start development server
python manage.py runserver 0.0.0.0:8000
