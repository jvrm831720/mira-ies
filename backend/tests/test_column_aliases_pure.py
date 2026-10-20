"""Aliases canonicos usados na ingestao."""
COLUMN_ALIASES = {
    "matricula": ["matricula", "ra", "registro", "codigo_aluno", "student_id"],
    "nome": ["nome", "nome_aluno", "name", "student_name"],
    "dias_atraso_boleto": ["dias_atraso_boleto", "atraso_boleto", "dias_atraso"],
}


def normalize(cols: list[str]) -> dict[str, str]:
    cols = [c.strip().lower().replace(" ", "_") for c in cols]
    rename = {}
    used = set()
    for target, aliases in COLUMN_ALIASES.items():
        for col in cols:
            if col in aliases and target not in used:
                rename[col] = target
                used.add(target)
                break
    return rename


def test_ra_maps_to_matricula():
    r = normalize(["RA", "Nome Aluno", "Dias Atraso"])
    assert r.get("ra") == "matricula"
    assert r.get("nome_aluno") == "nome"
    assert r.get("dias_atraso") == "dias_atraso_boleto"
