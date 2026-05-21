release: python manage.py migrate
web: gunicorn joyerias_inventario.wsgi --bind 0.0.0.0:$PORT
