PY=.venv/bin/python

check:
	$(PY) manage.py check

test:
	$(PY) manage.py test --verbosity=1

migrate:
	$(PY) manage.py migrate

run:
	$(PY) manage.py runserver
