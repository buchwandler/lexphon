from benchmarks.pronunciation_validation.model import BenchmarkSpec
from benchmarks.pronunciation_validation.runner import main_for

SPEC = BenchmarkSpec(lexicon_id='en-gb:gold')

if __name__ == '__main__':
    raise SystemExit(main_for(SPEC))
