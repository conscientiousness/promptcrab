import textwrap

from promptcrab.constants import LANGUAGE_LABELS


def combine_system_user(system_prompt: str, user_prompt: str) -> str:
    return f"[SYSTEM INSTRUCTION]\n{system_prompt.strip()}\n\n[TASK]\n{user_prompt.strip()}\n"


def build_rewrite_user_prompt(original_prompt: str, lang: str) -> str:
    language = LANGUAGE_LABELS[lang]
    return textwrap.dedent(
        f"""
        Rewrite the ORIGINAL_PROMPT into {language}.

        Primary goal:
        - minimize tokens while preserving meaning and actionability

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
        - do not add any new information
        - do not remove required context that another LLM would need in order to act
          correctly
        - for copied logs, query inspectors, state dumps, JSON, stack traces, or other
          diagnostic blocks, prefer minimal edits; do not summarize, normalize into a new
          schema, or drop labels/counts if another agent may need the original layout
        - JSON or data samples may be minimized, but any kept structure must remain correct
        - do not break relationships between fields and values
        - if the prompt is already dense and operational, prefer light compression over
          aggressive rewriting
        - remove politeness, repetition, and filler wording
        - return only the rewritten prompt

        Language-specific rule:
        - for Wenyan, use it only when it does not reduce technical precision or
          implementation clarity

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
        4. no missing constraints
        5. no missing literal data that affects execution, including URLs, IDs,
           field names, keys, and numbers
        6. no translated or normalized technical/UI terms when the original literal form
           matters for implementation, including directional tokens such as
           left/right/bottom and reference tags such as [Image #1]
        7. structured diagnostic blocks are not summarized or reformatted in a way that
           drops labels, counts, ordering cues, or field/value relationships
        8. no added information
        9. no ambiguity that would make another LLM guess

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
