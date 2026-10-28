"""Assemble retention agents routes from body parts (temporary restore mechanism)."""
from pathlib import Path

_dir = Path(__file__).resolve().parent
_body = "".join((_dir / f"_agents_body_part{i}.py").read_text(encoding="utf-8") for i in range(3))
_globals = globals()
exec(compile(_body, str(_dir / "agents_body.py"), "exec"), _globals)
