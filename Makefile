.PHONY: test install install-shims clean

test:
	python3 -m unittest discover -s tests -p "test_*.py" -v

install:
	./bin/agy-profile install

install-shims:
	./bin/agy-profile install-shims

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build dist *.egg-info .pytest_cache
