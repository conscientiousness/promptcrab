import textwrap

from promptcrab.constants import LANGUAGE_LABELS


def combine_system_user(system_prompt: str, user_prompt: str) -> str:
    return f"[SYSTEM INSTRUCTION]\n{system_prompt.strip()}\n\n[TASK]\n{user_prompt.strip()}\n"


def build_rewrite_user_prompt(
    original_prompt: str,
    lang: str,
    *,
    conservative: bool = False,
    risk_tags: tuple[str, ...] = (),
) -> str:
    language = LANGUAGE_LABELS[lang]
    conservative_block = ""
    if conservative:
        tags = ", ".join(risk_tags) if risk_tags else "literal_sensitive"
        conservative_block = textwrap.dedent(
            f"""

            Conservative preflight mode:
            - triggered tags: {tags}
            - do not translate the prompt
            - do not normalize symbols or punctuation such as ^2, *, ***, P.P.S, >=, <=, or brackets
            - preserve format examples, separators, bullet scaffolds, quoted text, and
              verbatim text exactly
            - preserve exact wording around repeat/copy/quote instructions
            - prefer returning the original prompt unchanged over an aggressive rewrite
            - only remove obvious filler when doing so cannot affect literal or format behavior
            """
        ).rstrip()
    return textwrap.dedent(
        f"""
        Rewrite the ORIGINAL_PROMPT into {language}.

        Primary goal:
        - improve prompt effectiveness for the downstream LLM
        - fix obvious prose-level typos, grammar issues, awkward sentence structure,
          unclear sequencing, and weak task framing when the fix preserves intent
        - make tasks, constraints, context, and expected output easier to execute

        Secondary goal:
        - reduce tokens only after clarity, fidelity, and actionability are preserved
        - prefer concise wording, but do not make the prompt harder to follow

        Hard requirements:
        - preserve the exact meaning, intent, and expected action
        - preserve every task, constraint, comparison target, condition, and question
        - preserve whether the original is phrased as a question, instruction,
          checklist, or mixed request; do not turn a user question into an
          imperative check unless the original already did that
        - preserve the number of tasks and their order
        - preserve every URL, ID, node-id, query parameter, field name, key, number,
          code identifier, and literal that affects execution
        - preserve image/reference tags and mixed-language technical tokens exactly when
          they are used as anchors, labels, or comparison handles, for example [Image #1]
        - preserve UI/layout/property/component terms exactly when they are implementation
          relevant, including directional terms or mixed-language tokens such as
          left/right/bottom, screen, scroll list, and card
        - do not translate, normalize, or paraphrase technical literals or UI terms if
          another LLM or agent may need the original spelling to act correctly
        - preserve intentional misspellings and exact wording inside literals, quoted
          text, examples, code, field names, UI labels, URLs, IDs, and user-provided
          data even if they look like typos
        - do not add any new information
        - do not remove required context that another LLM would need in order to act
          correctly
        - for copied logs, query inspectors, state dumps, JSON, stack traces, or other
          diagnostic blocks, prefer minimal edits; do not summarize, normalize into a new
          schema, or drop labels/counts if another agent may need the original layout
        - JSON or data samples may be minimized, but any kept structure must remain correct
        - do not break relationships between fields and values
        - if the prompt is already dense and operational, prefer light copy-editing over
          aggressive rewriting
        - remove politeness, repetition, and filler wording
        - return only the rewritten prompt

        Language-specific rule:
        - for Wenyan, use actual Classical Chinese; do not label a modern Chinese rewrite
          as Wenyan
        {conservative_block}

        ORIGINAL_PROMPT:
        <<<PROMPT
        {original_prompt}
        PROMPT
        >>>
        """
    ).strip()


def build_verifier_user_prompt(original_prompt: str, candidate_prompt: str) -> str:
    return textwrap.dedent(
        f"""
        Compare ORIGINAL_PROMPT against CANDIDATE_PROMPT.

        Evaluate strictly:
        1. same number of tasks
        2. same task order
        3. same interaction mode and response expectation; a question should not become
           a directive check unless the original already implied that shift
        4. candidate is at least as clear and actionable as the original; typo or sentence
           fixes are allowed only for ordinary prose, not protected literals
        5. no missing constraints
        6. no missing literal data that affects execution, including URLs, IDs,
           field names, keys, and numbers
        7. no translated or normalized technical/UI terms when the original literal form
           matters for implementation, including directional tokens such as
           left/right/bottom and reference tags such as [Image #1]
        8. structured diagnostic blocks are not summarized or reformatted in a way that
           drops labels, counts, ordering cues, or field/value relationships
        9. no added information
        10. no ambiguity that would make another LLM guess

        Return JSON only using this exact shape:
        {{
          "faithful": true,
          "same_task_count": true,
          "same_order": true,
          "missing_literals": [],
          "missing_constraints": [],
          "added_info": [],
          "ambiguities": [],
          "notes": []
        }}

        ORIGINAL_PROMPT:
        <<<ORIGINAL
        {original_prompt}
        ORIGINAL
        >>>

        CANDIDATE_PROMPT:
        <<<CANDIDATE
        {candidate_prompt}
        CANDIDATE
        >>>
        """
    ).strip()
