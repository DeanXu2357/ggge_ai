---
name: ste-rewrite
description: Rewrites English into Simplified Technical English (ASD-STE100) — short sentences, active voice, simple tenses, one idea per sentence, no dropped words, American spelling. Use this skill whenever the user asks to simplify, clarify, tighten, or disambiguate English text, and whenever the user writes or edits doc comments, docstrings, API and tool descriptions, error and log messages, README steps, runbooks, install guides, agent instructions, or release notes. Trigger on phrases such as "simplify this", "make this clearer", "plain English", "unambiguous", "controlled language", "Simplified Technical English", "STE", or "ASD-STE100", and also when a draft reads as dense, hedged, or easy to misparse.
---

# STE Rewrite

Rewrite English text into Simplified Technical English (STE). STE is the
controlled language of the ASD-STE100 standard. Aerospace teams wrote it for a
reader who cannot ask a question. The same conditions apply to a non-native
reader, a translator, and an AI agent.

## When to use this skill

Use this skill for text that a machine or a non-native reader must parse:

- doc comments, docstrings, and API descriptions
- error messages and log messages
- tool descriptions and agent instructions
- install guides, runbooks, and procedure steps
- release notes and changelog entries

Do not use this skill for marketing copy, blog posts, or design rationale. STE
removes nuance. That result is correct in a procedure. It is a defect in an
argument.

## Procedure

1. Read the source text. Find the meaning before you change the words.
2. Classify each sentence. A procedural sentence tells the reader to do
   something. All other sentences are descriptive.
3. Apply the rules in the next section.
4. Count the items in the checklist.
5. Give the new text.

Meaning has more importance than vocabulary. If a simple word changes the
meaning, keep the necessary word. A simple sentence that is false is the worse
result.

## The rules

### 1. Words

- Give one meaning to one word. Do not use a word with two meanings.
- Use the same word for the same thing in all of the text.
- Use the short and common word. Delete slang and idioms.
- Write `do not`. Do not write `don't`.
- Use `can` for a possibility. Use `must` for a requirement. Do not use
  `should`.

### 2. Noun phrases

- Use a maximum of three words in a noun cluster.
- Break a longer cluster with a preposition. Write `the timeout of the
  connection pool`.
- Keep the articles `a`, `an`, and `the`.
- Prefer a verb to a noun that comes from a verb. Write `Install the module`.
  Do not write `Do the installation of the module`.

### 3. Verbs

- Use these forms only: infinitive, imperative, simple present, simple past,
  and simple future.
- Use a past participle as an adjective only.
- Do not use the perfect tenses or the progressive tenses. Write `we removed`.
  Do not write `we have removed`.
- Use an `-ing` word only as part of a technical name.
- Use the active voice in a procedure.
- Use the passive voice in description only, and only if the agent is unknown
  or is not important.

### 4. Sentences

- Put one idea in one sentence.
- Do not remove words to make a sentence short. A removed word causes
  ambiguity.
- Keep the relative pronouns `that`, `which`, and `who`.
- Change a list inside a sentence into a vertical list.

### 5. Procedures

- Put one instruction in one sentence.
- Start the sentence with the command verb.
- Put the condition before the command. Write `If the test fails, stop the
  job`.
- Do not put description inside a procedure step.

### 6. Descriptive writing

- Put one topic in one paragraph.
- Put the topic sentence first.
- Use a maximum of six sentences in a paragraph.
- Put the information in a logical sequence.

### 7. Safety information

- Put the warning before the applicable step.
- Write the command first. Then write the reason.
- A warning refers to injury to persons. A caution refers to damage to
  equipment or to data.

### 8. Punctuation and length

- Do not use a semicolon. Write two sentences.
- Use a maximum of 20 words in a procedural sentence.
- Use a maximum of 25 words in a descriptive sentence.
- Use American spelling and American punctuation.

### 9. Practice

- Do not replace words one by one. Write the sentence again.
- Keep code identifiers, file paths, flags, and command names unchanged.
- Keep a term that the domain needs. Examples: `goroutine`, `mutex`, `golden
  file`. These terms are technical names.
- Write for the reader who knows the least.

## Output format

Give the new text and nothing else. Keep the headings, the lists, and the code
of the source. Keep the comment markers of the source language.

If the user asks for the changes, add this table after the new text:

| Source | STE | Rule |
| --- | --- | --- |

If a sentence has two possible meanings, do not guess. Ask the user one
question.

## Checklist

Count these items before you give the new text:

- sentence length: 20 words or 25 words
- semicolons: 0
- contractions: 0
- words in a noun cluster: 3 or fewer
- passive verbs in a procedure: 0
- sentences in a paragraph: 6 or fewer
- perfect and progressive tenses: 0

## Limits

This skill is an approximation of ASD-STE100. It is not certified. ASD holds
the copyright of the standard and of its dictionary. The dictionary of
approved words is not part of this skill. Get the official document at no cost
from asd-ste100.org. A clean result from this skill is not a claim of
compliance.
