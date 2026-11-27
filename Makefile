PY ?= python

.PHONY: help corpus testsets eval eval-retrieval eval-full test clean-eval

help:
	@echo "corpus          generate the synthetic report corpus (eval/data, gitignored)"
	@echo "testsets        build extraction/risk/question/injection test sets"
	@echo "eval            index + retrieval scoring (no LLM needed)"
	@echo "eval-full       every stage, including the LLM ones (needs an endpoint)"
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

eval-full:
	$(PY) eval/run_eval.py --stages all --label baseline

test:
	cd backend && $(PY) -m pytest -q

clean-eval:
	rm -rf eval/data eval/results
