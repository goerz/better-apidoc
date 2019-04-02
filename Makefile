TESTPYPI = https://testpypi.python.org/pypi

install:
	pip install .

develop:
	pip install -e .[dev]

uninstall:
	pip uninstall better_apidoc

upload:
	python setup.py sdist
	twine upload dist/*

test-upload:
	python setup.py sdist
	twine upload --repository-url https://test.pypi.org/legacy/ dist/*

test-install:
	pip install -i $(TESTPYPI) better-apidoc

clean:
	@rm -rf __pycache__
	@rm -rf *.egg-info
	@rm -rf dist
	@rm -rf build

.PHONY: install develop uninstall upload test-upload test-install clean
