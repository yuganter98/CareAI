PY ?= python

.PHONY: help corpus testsets eval eval-retrieval eval-full check-llm compare test clean-eval

help:
	@echo "corpus          generate the synthetic report corpus (eval/data, gitignored)"
	@echo "testsets        build extraction/risk/question/injection test sets"
	@echo "eval            index + retrieval scoring (no LLM needed)"
	@echo "eval-full       every stage, including the LLM ones (needs an endpoint)"
	@echo "check-llm       one test call to the configured LLM, then exit"
	@echo "compare         significance-test the retrieval paths in RESULTS=<file>"
	@echo "test            backend test suite"

corpus:
	$(PY) eval/generate_reports.py

testsets:
	$(PY) eval/build_testsets.py
	$(PY) eval/generate_injections.py

# The default run is the part that needs no LLM, so it works on a fresh clone.
eval: eval-retrieval

eval-retrieval:
	$(PY) eval/run_eval.py --stages index,retrieval --label baseline

eval-full: check-llm
	$(PY) eval/run_eval.py --stages all --label baseline

# Fails in one request rather than several hundred if the key or model is wrong.
check-llm:
	$(PY) eval/run_eval.py --check-llm

# A mean alone cannot say whether a change beat the noise of 80 questions.
RESULTS ?= eval/results/2026-11-27_week2.json
compare:
	$(PY) eval/compare.py $(RESULTS) --by-type

test:
	cd backend && $(PY) -m pytest -q

clean-eval:
	rm -rf eval/data eval/results
