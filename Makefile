

test:
	python -m stpl2.tests

coverage:
	@(nosetests $(TEST_OPTIONS) --with-coverage --cover-package=stpl2 --cover-html --cover-html-dir=coverage_out $(TESTS))
