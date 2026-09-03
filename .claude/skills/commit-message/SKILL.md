---
name: commit-message
description: Writes a Git commit message for the staged changes, for a given commit, or for a commit range. Use when the user asks to commit, to draft a commit message, or to reword an existing commit.
argument-hint: [commit-hash or range, optional]
allowed-tools: Bash(git diff *), Bash(git log *), Bash(git show *), Bash(git branch *), Bash(git status *), Read, Grep, Glob
---

Write a Git commit message for the target described below. You run in
the main conversation, so the conversation history is your primary
source for why the change exists. Use the repository only to confirm
what changed and to fill gaps the conversation leaves open.

<definitions>
- "Subject line": the first line of the commit message.
- "Body": every line after the blank line that follows the subject line.
- "Target": the change you describe. When "$ARGUMENTS" names a commit
  hash or a commit range, the target is that commit or that range.
  Otherwise the target is the staged diff.
</definitions>

<workflow>
1. Collect the "why" from the conversation.
   Reread the conversation for the motivation behind the change: the bug
   report, the feature request, the design decision, the alternatives
   the user rejected, and any issue number, paper, or upstream source
   the user mentioned. These facts belong in the body.
2. Confirm the "what" from the repository.
   - Staged target: run "git diff --staged --stat". Run
     "git diff --staged" only when the conversation does not already
     show the changed code. If the staged diff is empty, run
     "git status --short", tell the user that nothing is staged, and
     stop.
   - Named target: run "git show <hash>" or "git log -p <range>".
3. Match the project's conventions.
   Run "git log --oneline -20" and note any subject-line prefix the
   project uses consistently, such as "net:" or "docs:", and any
   trailer style such as "Fixes: #123" or "Closes #123".
4. Resolve gaps by asking.
   When the conversation and the repository together leave the "why"
   unclear, ask the user one specific question before you write the
   message. A question costs one turn; an invented motivation costs the
   reader's trust in the history.
5. Write the commit message according to the rules below.
6. Verify line lengths before you present the message. Count the
   characters of the subject line and of every body line yourself, and
   fix every line that exceeds the limit.
7. Present the message. Then commit only in one of these two cases:
   the user's request already included committing, or the user
   confirms after seeing the message. Commit with
   "git commit -F -" and a heredoc so the message reaches git exactly
   as written.
</workflow>

<rules>
Formatting rules (from Chris Beams, "How to Write a Git Commit Message"):
1. A single blank line separates the subject line from the body.
2. The subject line contains at most 50 characters.
3. The subject line begins with a capital letter. When the project
   consistently uses a lowercase prefix such as "mm:", keep that prefix
   and capitalize the first word after the prefix.
4. The subject line ends without a period.
5. The subject line uses the imperative mood, so that the subject line
   completes the sentence "If applied, this commit will ...".
6. Each line of the body contains at most 72 characters.
7. The body states why the change is needed. The body does not repeat
   the "what" that the subject line already states. The body describes
   how the change works only when the mechanism had more than one
   option and the selected option is not obvious.

Content rules:
8. The commit message uses American English spelling and vocabulary
   (for example "behavior", "optimize", "color").
9. The subject line describes the change with a verb and an object, in
   enough detail that a reader understands the change without opening
   the diff. A subject line that names only a file, such as
   "Update queue.c", fails this rule, and a subject line that consists
   of a single word fails this rule.
10. The body cites every important source that motivated or informed
    the change: papers, upstream source code, documentation, benchmark
    results, and related GitHub issues or pull requests, in the
    project's existing trailer style when "git log" shows one.
11. The commit message uses neutral, professional vocabulary.
12. The commit message marks identifiers, file names, and commands with
    single quotes or double quotes. Backtick characters render
    incorrectly in some terminals, so the commit message contains no
    backtick characters.
13. The subject line expresses every qualifier in words. The subject
    line contains no parentheses.
14. Every statement in the commit message is supported by the
    conversation, the diff, or the repository history.
</rules>

<output_format>
Show the complete commit message as plain text: the subject line, the
blank line, the body, and any trailers. Follow the message with one
sentence that states the target you described and, when you did not
commit, asks whether to commit.
</output_format>
