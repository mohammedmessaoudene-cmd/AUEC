#!/usr/bin/env python3
"""Deterministic, non-generative prose diagnostics for the public manuscript."""
from __future__ import annotations
import json, re, subprocess, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "docs" / "technical-report"
OUT_MD = PAPER / "editorial" / "LANGUAGE_STYLE_METRICS.md"
OUT_JSON = ROOT / "release" / "v0.36.0-prestandard" / "language-style-metrics.json"

PROMOTIONAL = {
    "groundbreaking", "revolutionary", "game-changing", "breakthrough", "unprecedented",
    "world-first", "first-ever", "paradigm-shifting", "transformative", "obviously",
    "clearly superior", "perfect", "guaranteed", "flawless", "brilliant", "ultimate",
}
PLACEHOLDER = {"todo", "tbd", "fixme", "xxx", "lorem ipsum", "citation needed"}
AI_TELLS = {
    "delve", "tapestry", "realm", "in today's rapidly evolving", "it is worth noting",
    "underscores the importance", "pivotal", "navigate the complexities", "multifaceted",
    "robust framework", "seamlessly", "leveraging", "unlock", "harness the power",
}
CHARGED = {"master/slave", "blacklist", "whitelist", "sanity check", "dummy value"}


def expand_inputs(path: Path, stack: tuple[Path, ...] = ()) -> str:
    r"""Expand local \input directives when latexpand/Perl is unavailable."""
    resolved = path.resolve()
    if resolved in stack:
        chain = " -> ".join(item.name for item in (*stack, resolved))
        raise RuntimeError(f"cyclic LaTeX input: {chain}")
    text = resolved.read_text(encoding="utf-8")
    pattern = re.compile(r"\\input\{([^}]+)\}")

    def replace(match: re.Match[str]) -> str:
        child = resolved.parent / match.group(1)
        if child.suffix == "":
            child = child.with_suffix(".tex")
        # TeX distributions can resolve system-level inputs such as
        # glyphtounicode.tex. They are not manuscript prose and may not exist
        # beside the source, so the portable fallback deliberately skips them.
        if not child.is_file():
            return ""
        return expand_inputs(child, (*stack, resolved))

    return pattern.sub(replace, text)


def latex_to_plain_fallback(text: str) -> str:
    """Produce bounded prose diagnostics without an external detex program."""
    text = re.sub(r"(?m)(?<!\\)%.*$", " ", text)
    text = re.sub(r"\\item(?:\[[^\]]*\])?", " 1. ", text)
    text = re.sub(
        r"\\(?:part|chapter|section|subsection|subsubsection)\*?\{([^{}]*)\}",
        r". \1. ",
        text,
    )
    text = re.sub(r"\\begin\{[^}]+\}|\\end\{[^}]+\}", " ", text)
    text = re.sub(r"\\Cref\{[^}]*\}", "Section", text)
    text = re.sub(r"\\(?:cref|ref|pageref)\{[^}]*\}", "section", text)
    text = re.sub(r"\\(?:cite|label|url|href)\*?(?:\[[^\]]*\])?\{[^}]*\}", " ", text)
    # Preserve the visible argument of common one-argument formatting commands.
    for _ in range(4):
        updated = re.sub(
            r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?\{([^{}]*)\}",
            r" \1 ",
            text,
        )
        if updated == text:
            break
        text = updated
    text = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^\]]*\])?", " ", text)
    text = text.replace("{", " ").replace("}", " ")
    return re.sub(r"\s+", " ", text).strip()


def detex() -> str:
    try:
        proc = subprocess.run(
            ["latexpand", "main_public.tex"], cwd=PAPER,
            text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        proc = None
    expanded = (
        proc.stdout
        if proc is not None and proc.returncode == 0
        else expand_inputs(PAPER / "main_public.tex")
    )
    # Editorial metadata is audited separately and otherwise distorts sentence metrics.
    expanded = re.sub(r"\\begin\{CCSXML\}.*?\\end\{CCSXML\}", "", expanded, flags=re.S)
    expanded = re.sub(r"^\\ccsdesc.*$", "", expanded, flags=re.M)
    expanded = re.sub(r"^\\keywords.*$", "", expanded, flags=re.M)
    # Tables, figures, listings, and display equations have separate caption/layout audits.
    for env in ("table", "table*", "figure", "figure*", "lstlisting", "equation", "equation*", "align", "align*", "aligned"):
        expanded = re.sub(r"\\begin\{" + re.escape(env) + r"\}.*?\\end\{" + re.escape(env) + r"\}", " ", expanded, flags=re.S)
    expanded = re.sub(
        r"\A.*?(?=\\section\{Introduction\})",
        "",
        expanded,
        flags=re.S,
    )
    expanded = re.sub(r"\\bibliography\{[^}]*\}.*\Z", "", expanded, flags=re.S)
    try:
        pandoc = subprocess.run(
            ["pandoc", "-f", "latex", "-t", "plain", "--wrap=none"],
            input=expanded, cwd=PAPER, text=True, encoding="utf-8",
            errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        pandoc = None
    text = (
        pandoc.stdout
        if pandoc is not None and pandoc.returncode == 0
        else latex_to_plain_fallback(expanded)
    )
    # Remove title/front matter and bibliography tail from style statistics.
    marker = "Introduction\n"
    if marker in text:
        text = text.split(marker, 1)[1]
    text = text.split("References\n", 1)[0]
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sentences(text: str) -> list[str]:
    # Separate list items before ordinary sentence segmentation.
    text = re.sub(r"\s+(?=\d+\.\s+)", ". ", text)
    # Boundaries tuned for academic prose and deterministic output.
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    out=[]
    for s in raw:
        s=s.strip()
        if len(s.split()) >= 5:
            out.append(s)
    return out


def words(s: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", s.lower())


def findings(text: str, terms: set[str]) -> list[str]:
    low=text.lower()
    found=[]
    for term in sorted(terms):
        if re.search(r"(?<![a-z])" + re.escape(term) + r"(?![a-z])", low):
            found.append(term)
    return found


def main() -> int:
    text=detex()
    sents=sentences(text)
    lens=[len(words(s)) for s in sents]
    long=sorted(((len(words(s)),s) for s in sents if len(words(s)) >= 45), reverse=True)
    very_long=[(n,s) for n,s in long if n >= 60]
    all_words=words(text)
    ngrams=Counter(tuple(all_words[i:i+5]) for i in range(max(0,len(all_words)-4)))
    repeated=[(" ".join(k),v) for k,v in ngrams.items() if v >= 4]
    repeated.sort(key=lambda x:(-x[1],x[0]))
    semicolons=text.count(';')
    emdashes=text.count('---') + text.count('—')
    colon=text.count(':')
    metrics={
        "word_count":len(all_words),
        "sentence_count":len(sents),
        "mean_sentence_words": round(sum(lens)/len(lens),2) if lens else 0,
        "median_sentence_words": sorted(lens)[len(lens)//2] if lens else 0,
        "max_sentence_words":max(lens) if lens else 0,
        "sentences_ge_45_words":len(long),
        "sentences_ge_60_words":len(very_long),
        "semicolons":semicolons,
        "colons":colon,
        "emdash_like":emdashes,
        "promotional_terms":findings(text,PROMOTIONAL),
        "placeholder_terms":findings(text,PLACEHOLDER),
        "formulaic_ai_phrases":findings(text,AI_TELLS),
        "charged_terms":findings(text,CHARGED),
        "repeated_fivegrams_ge_4":repeated[:40],
        "long_sentences": [{"words":n,"text":s} for n,s in long[:30]],
    }
    OUT_JSON.parent.mkdir(parents=True,exist_ok=True)
    OUT_MD.parent.mkdir(parents=True,exist_ok=True)
    OUT_JSON.write_text(json.dumps(metrics,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    lines=[
        "# Deterministic language and style metrics", "",
        "This report is a mechanical diagnostic, not a detector of human or AI authorship. It checks readability risks, placeholders, promotional diction, selected formulaic phrases, charged terminology, and repeated five-word sequences. The manuscript retains a transparent AI-assistance disclosure.", "",
        "## Metrics", "",
        f"- Words (detex approximation): **{metrics['word_count']}**",
        f"- Sentences: **{metrics['sentence_count']}**",
        f"- Mean sentence length: **{metrics['mean_sentence_words']} words**",
        f"- Median sentence length: **{metrics['median_sentence_words']} words**",
        f"- Longest sentence: **{metrics['max_sentence_words']} words**",
        f"- Sentences at least 45 words: **{metrics['sentences_ge_45_words']}**",
        f"- Sentences at least 60 words: **{metrics['sentences_ge_60_words']}**", "",
        "## Lexical checks", "",
        f"- Promotional terms: `{metrics['promotional_terms']}`",
        f"- Placeholder terms: `{metrics['placeholder_terms']}`",
        f"- Selected formulaic AI-associated phrases: `{metrics['formulaic_ai_phrases']}`",
        f"- Selected charged terms: `{metrics['charged_terms']}`", "",
        "## Longest sentences for human review", "",
    ]
    for item in metrics['long_sentences'][:12]:
        lines.append(f"- **{item['words']} words:** {item['text']}")
    lines += ["", "## Repeated five-word sequences", ""]
    if repeated:
        for phrase,count in repeated[:15]: lines.append(f"- `{phrase}` — {count} occurrences")
    else:
        lines.append("- None occurring four or more times.")
    lines += ["", "## Gate", ""]
    hard = bool(metrics['placeholder_terms'] or metrics['promotional_terms'] or metrics['charged_terms'] or metrics['sentences_ge_60_words'] > 0)
    lines.append("**PASS**" if not hard else "**REVIEW REQUIRED**")
    OUT_MD.write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS" if not hard else "REVIEW_REQUIRED", **{k:v for k,v in metrics.items() if k not in {'long_sentences','repeated_fivegrams_ge_4'}}},indent=2))
    return 1 if hard else 0

if __name__ == "__main__":
    raise SystemExit(main())
