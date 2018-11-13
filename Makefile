default: check

lint:
	tox -e lint

test:
	tox

check: lint test


clean:
	rm -f *.pyc
	rm -rf .tox
	rm -rf *.egg-info
	rm -rf __pycache__
	rm -f pip-selfcheck.json

pypitestreg:
	python setup.py register -r pypitest

pypitest:
	python setup.py sdist upload -r pypitest

pypireg:
	python setup.py register -r pypi

pypi:
	python setup.py sdist
	twine upload dist/*.tar.gz

release:
	git diff-index --quiet HEAD -- && make check && bumpversion patch && git push --tags && make pypi
