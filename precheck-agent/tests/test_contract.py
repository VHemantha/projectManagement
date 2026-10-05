"""The result the agent sends must keep the shape the PM application stores. The sample lives
with the PM application's tests; regenerate it with PRECHECK_WRITE_SAMPLE=1 when the shape
changes on purpose."""
import json
import os
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[2] / "backend" / "apps" / "precheck" / "tests" / "sample_result.json"


def shape(value, depth=0):
    if isinstance(value, dict) and value and all(str(k).startswith("E-") for k in value):
        return "evidence by id"  # ids depend on the folder, the shape does not
    if isinstance(value, dict) and depth < 2:
        return {k: shape(v, depth + 1) for k, v in sorted(value.items())}
    if isinstance(value, list) and value and isinstance(value[0], dict) and depth < 2:
        return [sorted(value[0])]
    return type(value).__name__


def test_result_matches_the_shape_the_pm_application_stores(env):
    from .test_precheck import ready_folder

    ready_folder(env)  # a full pre-check, not one stopped at the key documents
    env.pm.add_job("1", "client-s", "smith", direction=[{"id": "D1", "text": "Check the refinance documents"}])
    result = env.run("1")
    result = json.loads(json.dumps(result))
    if os.environ.get("PRECHECK_WRITE_SAMPLE"):
        result.update(run_id="SAMPLE", job_id="SAMPLE")
        SAMPLE.write_text(json.dumps(result, indent=1), encoding="utf-8")
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    for key in ("trail", "usage", "coverage", "counts", "models", "versions", "precheck"):
        assert shape(result[key]) == shape(sample[key]), key
    assert sorted(result) == sorted(sample)
    assert sorted(result["precheck"]["requests"][0]) == sorted(sample["precheck"]["requests"][0])
