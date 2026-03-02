import json
import re
from typing import Any, Iterable, Literal, TypedDict, cast


StepKind = Literal["llm_prompt", "summary", "list"]

PromptLanguage = Literal["it", "en"]

AVAILABLE_LANGS: dict[str, PromptLanguage] = {
    "it": "it",
    "en": "en",
    "es": "en",
    "fr": "en",
    "de": "en",
    "pt": "en",
    "nl": "en",
}

DEFAULT_PROMPT_LANGUAGE: PromptLanguage = "it"


class PostprocessStep(TypedDict):
    section: str
    status_key: str
    kind: StepKind
    prompt_name: str
    list_kind: str
    target: int


def normalize_current_language(current_language: str) -> PromptLanguage:
    normalized = (current_language or "").strip().lower()
    return AVAILABLE_LANGS.get(normalized, DEFAULT_PROMPT_LANGUAGE)


def normalize_choice(value: str, valid: set[str], default: str) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in valid else default


def split_text_chunks(text: str, chunk_chars: int) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    return [compact[i:i + chunk_chars] for i in range(0, len(compact), chunk_chars)]


def count_words(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def to_any_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        cast(dict[str, Any], item)
        for item in cast(list[Any], value)
        if isinstance(item, dict)
    ]


def to_str_dict_list(value: Any) -> list[dict[str, str]]:
    return [
        {str(k): str(v) if v is not None else "" for k, v in item.items()}
        for item in to_any_dict_list(value)
    ]


def debug_preview(text: Any, limit: int = 120) -> str:
    if text is None:
        return "<None>"
    compact = re.sub(r"\s+", " ", str(text)).strip()
    return compact if len(compact) <= limit else compact[:limit] + "…"


def extract_json_candidate(text: str) -> Any | None:
    if not text:
        return None

    normalized = text.strip()
    if len(normalized) >= 2 and (
        (normalized[0] == '"' and normalized[-1] == '"')
        or (normalized[0] == "'" and normalized[-1] == "'")
    ):
        normalized = normalized[1:-1].strip()
    if normalized.lower().startswith("value="):
        normalized = normalized.split("=", 1)[1].strip()
    normalized = normalized.replace("\\'", "'")

    try:
        return json.loads(normalized)
    except Exception:
        pass

    markdown_match = re.search(
        r"```json\s*([\{\[][^`]*?[\}\]])\s*```", normalized, re.IGNORECASE
    )
    if markdown_match:
        try:
            return json.loads(markdown_match.group(1))
        except Exception:
            pass

    start_arr = normalized.find("[")
    end_arr = normalized.rfind("]")
    if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
        try:
            return json.loads(normalized[start_arr:end_arr + 1])
        except Exception:
            pass

    start_obj = normalized.find("{")
    end_obj = normalized.rfind("}")
    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
        try:
            return json.loads(normalized[start_obj:end_obj + 1])
        except Exception:
            pass

    object_sequence = extract_top_level_json_objects(normalized)
    if object_sequence:
        if len(object_sequence) == 1:
            return object_sequence[0]
        return object_sequence

    return None


def extract_top_level_json_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    in_string = False
    escape = False
    depth = 0
    start = -1

    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
            continue

        if ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start:idx + 1]
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict):
                        objects.append(cast(dict[str, Any], parsed))
                except Exception:
                    pass
                start = -1

    return objects


def dedupe_dict_items(items: Iterable[dict[str, str]], key_fields: tuple[str, ...]) -> list[dict[str, str]]:
    seen: set[tuple[str, ...]] = set()
    result: list[dict[str, str]] = []
    for item in items:
        item_key = tuple(str(item.get(field, "")).strip().lower()
                         for field in key_fields)
        if not any(item_key):
            continue
        if item_key in seen:
            continue
        seen.add(item_key)
        result.append(item)
    return result


def notes_label(current_language: str) -> str:
    return "COMPLETE NOTES" if normalize_current_language(current_language) == "en" else "NOTE COMPLETE"


def academic_system_prompt(current_language: str) -> str:
    if normalize_current_language(current_language) == "en":
        return "You are an academic assistant. Be faithful to the source and do not invent facts."
    return "Sei un assistente accademico. Sii fedele alla fonte e non inventare informazioni."


def build_map_chunk_prompt(*, current_language: str, idx: int, total: int, chunk_text: str) -> str:
    if normalize_current_language(current_language) == "en":
        return (
            f"This is transcript chunk {idx}/{total}.\n"
            "1) Extract numbered key concepts.\n"
            "2) List technical terms with short definitions.\n"
            "3) Propose a mini-outline (max 2 levels).\n\n"
            f"CHUNK:\n{chunk_text}"
        )
    return (
        f"Questo è il chunk {idx}/{total} della trascrizione.\n"
        "1) Estrai i concetti chiave numerati.\n"
        "2) Elenca termini tecnici con brevi definizioni.\n"
        "3) Proponi un mini-outline (max 2 livelli).\n\n"
        f"CHUNK:\n{chunk_text}"
    )


def build_reduce_prompt(*, current_language: str, partials: list[str]) -> str:
    notes_block = "\n\n---\n\n".join(partials)
    if normalize_current_language(current_language) == "en":
        return (
            "Merge the notes below into:\n"
            "A) A global OUTLINE (max 3 levels)\n"
            "B) KEY POINTS (concise bullets)\n"
            "C) GLOSSARY CANDIDATES (term: short definition)\n\n"
            "PARTIAL NOTES:\n" + notes_block
        )
    return (
        "Unisci le note qui sotto in:\n"
        "A) OUTLINE complessivo (max 3 livelli)\n"
        "B) KEY POINTS (bullet concisi)\n"
        "C) GLOSSARY CANDIDATES (termini: definizione breve)\n\n"
        "NOTE PARZIALI:\n" + notes_block
    )


def summary_system_prompt(current_language: str) -> str:
    if normalize_current_language(current_language) == "en":
        return "You are an academic assistant. Produce summaries in English, structured in Markdown."
    return "Sei un assistente accademico. Produci riassunti in italiano, strutturati in Markdown."


def build_summary_prompt(
    *,
    current_language: str,
    notes: str,
    notes_label_value: str,
    target_min: int,
    target_max: int,
) -> str:
    if normalize_current_language(current_language) == "en":
        return (
            f"Using the {notes_label_value} below, write a **substantial** Markdown summary "
            f"between {target_min}-{target_max} words, "
            "with headings (#, ##, ###), examples, and textual formulas. "
            "Write in English.\n"
            "Do not invent facts; if information is not in the notes, omit it.\n\n"
            "At the end, add one HTML comment line with exact syntax:\n"
            "<!-- WORDS: <number> -->\n\n"
            f"{notes_label_value}:\n{notes}"
        )
    return (
        "In base alle NOTE COMPLETE qui sotto, scrivi un **riassunto corposo** in Markdown "
        f"tra {target_min}-{target_max} parole, "
        "con titoli (#, ##, ###), esempi e formule testuali. "
        "Non inventare; se un’informazione non è nelle note, omettila.\n\n"
        "Al termine, aggiungi una riga HTML commentata con il conteggio parole con esatta sintassi:\n"
        "<!-- WORDS: <numero> -->\n\n"
        "NOTE COMPLETE:\n" + notes
    )


def summary_retry_note(current_language: str) -> str:
    if normalize_current_language(current_language) == "en":
        return "\n\n[NOTE: expand coverage of examples, practical applications, and edge cases.]"
    return "\n\n[NOTA: amplia copertura di esempi/applicazioni pratiche e casi limite.]"


def list_schema_examples(current_language: str) -> dict[str, str]:
    if normalize_current_language(current_language) == "en":
        return {
            "questions": 'Return **ONLY** JSON (array) in this form:[{"q":"...", "a":"...", "difficulty":"easy|medium|hard"}, ...]',
            "flashcards": 'Return **ONLY** JSON (array) in this form:[{"front":"...", "back":"..."}, ...]',
            "glossary": 'Return **ONLY** JSON (array) in this form:[{"term":"...", "definition":"..."}, ...]',
        }
    return {
        "questions": 'Restituisci **SOLO** JSON (lista) della forma:\n[{"q":"...", "a":"...", "difficulty":"facile|medio|difficile"}, ...]\n',
        "flashcards": 'Restituisci **SOLO** JSON (lista) della forma:\n[{"front":"...", "back":"..."}, ...]\n',
        "glossary": 'Restituisci **SOLO** JSON (lista) della forma:\n[{"term":"...", "definition":"..."}, ...]\n',
    }


def list_system_prompt(current_language: str) -> str:
    if normalize_current_language(current_language) == "en":
        return "You are an academic assistant. Strictly follow the required JSON schema."
    return "Sei un assistente accademico. Rispetta rigorosamente lo schema JSON richiesto."


def build_list_prompt(
    *,
    current_language: str,
    notes: str,
    notes_label_value: str,
    kind: str,
    remaining: int,
    schema_example: str,
) -> str:
    if normalize_current_language(current_language) == "en":
        return (
            f"From the {notes_label_value} below, generate **exactly {remaining}** {kind} items. "
            "Do not repeat concepts already used. Do not invent beyond the notes.\n\n"
            + schema_example + f"\n{notes_label_value}:\n" + notes
        )
    return (
        f"In base alle NOTE COMPLETE qui sotto, genera **esattamente {remaining}** elementi di tipo {kind}. "
        "Non ripetere concetti già usati. Non inventare oltre le note.\n\n"
        + schema_example + "\nNOTE COMPLETE:\n" + notes
    )


def build_abstract_prompt(*, current_language: str, notes_text: str, notes_label_value: str) -> str:
    if normalize_current_language(current_language) == "en":
        return (
            f"Write an abstract of 6-8 sentences, faithful to the {notes_label_value} below. "
            f"No bullet lists, prose only. {notes_label_value}:\n" + notes_text
        )
    return (
        "Scrivi un abstract di 6-8 frasi, fedele alle NOTE COMPLETE qui sotto. "
        "Niente liste, solo prosa. NOTE COMPLETE:\n" + notes_text
    )


def build_outline_prompt(*, current_language: str, notes_text: str, notes_label_value: str) -> str:
    lead = (
        f"From the {notes_label_value}, create a hierarchical outline (max 3 levels) in JSON with this shape "
        if normalize_current_language(current_language) == "en"
        else "Dalle NOTE COMPLETE crea un outline gerarchico (max 3 livelli) in JSON della forma "
    )
    tail = (
        "ONLY JSON.\n\n" + f"{notes_label_value}:\n"
        if normalize_current_language(current_language) == "en"
        else "SOLO JSON.\n\nNOTE COMPLETE:\n"
    )
    return lead + '[{"title":"...", "children":[...]}]. ' + tail + notes_text


def build_keypoints_prompt(*, current_language: str, notes_text: str, notes_label_value: str) -> str:
    if normalize_current_language(current_language) == "en":
        return (
            "Extract 10-16 concise key points (single-line bullets) from the "
            f"{notes_label_value}:\n" + notes_text
        )
    return (
        "Estrai 10-16 punti chiave sintetici (bullet singola riga) dalle NOTE COMPLETE:\n"
        + notes_text
    )


def normalize_outline_nodes(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [cast(dict[str, Any], value)]
    return to_any_dict_list(value)


def parse_key_points(text: str) -> list[str]:
    return [line.strip("-• ").strip() for line in text.splitlines() if line.strip()]


def render_outline_text(outline: Any) -> str:
    lines: list[str] = []

    def walk(nodes: Any, level: int = 0) -> None:
        for node in to_any_dict_list(nodes):
            title = str(node.get("title", "")).strip()
            lines.append("  " * level + ("- " + title if title else "-"))
            walk(node.get("children", []), level + 1)

    walk(outline)
    return "\n".join(lines)


def render_key_points_text(key_points: Any) -> str:
    if isinstance(key_points, list):
        return "\n".join(str(item) for item in cast(list[Any], key_points))
    return str(key_points or "")


def render_questions_text(questions: Any, *, answer_label: str, difficulty_label: str) -> str:
    lines: list[str] = []
    for i, qa in enumerate(to_any_dict_list(questions), 1):
        question_text = str(qa.get("q", "")).strip()
        answer_text = str(qa.get("a", "")).strip()
        difficulty_text = str(qa.get("difficulty", "")).strip()
        lines.append(
            f"{i:02d}) {question_text}\n"
            f"   {answer_label}: {answer_text}\n"
            f"   {difficulty_label}: {difficulty_text}\n"
        )
    return "\n".join(lines)


def render_flashcards_text(flashcards: Any) -> str:
    lines: list[str] = []
    for i, fc in enumerate(to_any_dict_list(flashcards), 1):
        lines.append(
            (
                f"{i:02d}) FRONT: {str(fc.get('front', '')).strip()}\n"
                f"    BACK: {str(fc.get('back', '')).strip()}\n"
            )
        )
    return "\n".join(lines)


def render_glossary_text(glossary: Any) -> str:
    lines: list[str] = []
    for term in to_any_dict_list(glossary):
        lines.append(
            (
                f"- {str(term.get('term', '')).strip()}: "
                f"{str(term.get('definition', '')).strip()}"
            )
        )
    return "\n".join(lines)


def parse_flashcards_from_text(text: str) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    current: dict[str, str] = {"front": "", "back": ""}
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("FRONT:"):
            current = {"front": stripped.split(
                "FRONT:", 1)[1].strip(), "back": ""}
        elif stripped.startswith("BACK:"):
            current["back"] = stripped.split("BACK:", 1)[1].strip()
            if current.get("front"):
                cards.append({"front": current.get("front", ""),
                             "back": current.get("back", "")})
    return cards


def build_flashcards_csv_rows(cards: Any) -> list[list[str]]:
    rows: list[list[str]] = [["Front", "Back"]]
    for card in to_any_dict_list(cards):
        rows.append([
            str(card.get("front", "")).strip(),
            str(card.get("back", "")).strip(),
        ])
    return rows


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_") or "output"


def build_postprocess_plan(*, target_questions: int, target_flashcards: int, target_glossary: int) -> list[PostprocessStep]:
    return [
        {
            "section": "abstract",
            "status_key": "status_llm_abstract",
            "kind": "llm_prompt",
            "prompt_name": "abstract",
            "list_kind": "",
            "target": 0,
        },
        {
            "section": "summary_markdown",
            "status_key": "status_llm_summary",
            "kind": "summary",
            "prompt_name": "",
            "list_kind": "",
            "target": 0,
        },
        {
            "section": "outline",
            "status_key": "status_llm_outline",
            "kind": "llm_prompt",
            "prompt_name": "outline",
            "list_kind": "",
            "target": 0,
        },
        {
            "section": "key_points",
            "status_key": "status_llm_keypoints",
            "kind": "llm_prompt",
            "prompt_name": "key_points",
            "list_kind": "",
            "target": 0,
        },
        {
            "section": "questions",
            "status_key": "status_llm_questions",
            "kind": "list",
            "prompt_name": "",
            "list_kind": "questions",
            "target": target_questions,
        },
        {
            "section": "flashcards",
            "status_key": "status_llm_flashcards",
            "kind": "list",
            "prompt_name": "",
            "list_kind": "flashcards",
            "target": target_flashcards,
        },
        {
            "section": "glossary",
            "status_key": "status_llm_glossary",
            "kind": "list",
            "prompt_name": "",
            "list_kind": "glossary",
            "target": target_glossary,
        },
    ]
