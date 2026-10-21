# SPDX-FileCopyrightText: 2026 Ricky Wanga <dev@rickywanga.com>
#
# SPDX-License-Identifier: AGPL-3.0-only

"""Exercise the AsciiDoc step and statik publication, not the other converters.

Run with python3 inside build-image, with TMPDIR on a writable scratch mount.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


workflow = (Path(__file__).parents[1] / ".github/workflows/statik.yaml").read_text()
compile_steps = re.findall(
    r"      - name: (Recursively compile .+)\n        run: (.+)", workflow
)
assert compile_steps, "No conversion steps found in statik.yaml"
compile_steps = [(name, command) for name, command in compile_steps if "AsciiDoc" in name]
rename_step = re.search(
    r"      - name: Rename multifile projects output\n        run: (.+)", workflow
)
assert rename_step, "No multifile rename step found in statik.yaml"
rename = rename_step.group(1)
listing_step = re.search(
    r"      - name: Generate static directory listing\n        run: >\n"
    r"((?:          .+\n)+)",
    workflow,
)
assert listing_step, "No statik listing step found in statik.yaml"
listing = listing_step.group(1)
listing = " ".join(line.strip() for line in listing.splitlines())
listing = listing.replace("${{ github.event.repository.name }}", "fixture")

with tempfile.TemporaryDirectory(prefix="statik-asciidoc-", dir=os.environ["TMPDIR"]) as tmp:
    source = Path(tmp) / "source"
    source.mkdir()
    originals = {
        "notes/chapter/lesson.adoc": "= AsciiDoc fixture\n\nA *bold* line and caffè.\n",
        "notes/legacy.asciidoc": "= Legacy extension\n\nA *bold* line and caffè.\n",
        "README.adoc": "= Excluded README\n\nNot published.\n",
        ".github/hidden.adoc": "= Excluded directory\n\nNot published.\n",
        "control.txt": "Unchanged plain text.\n",
        "almost.adoc.bak": "Not an AsciiDoc source.\n",
    }
    for name, content in originals.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    for name, command in compile_steps:
        print(name, flush=True)
        subprocess.run(["/bin/sh", "-ec", command], cwd=source, check=True)

    for name in originals:
        assert (source / name).read_text() == originals[name], name
    for name in ("notes/chapter/lesson.html", "notes/legacy.html"):
        path = source / name
        assert path.is_file(), f"Missing HTML output: {name}"
        html = path.read_text()
        assert "<!DOCTYPE html>" in html and "<html" in html, name
        assert "<strong>bold</strong>" in html and "caffè" in html, name
    assert not list(source.rglob("*.pdf")), "AsciiDoc must produce HTML, not PDF"
    assert not (source / "almost.adoc.html").exists()

    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=source, check=True)
    subprocess.run(["git", "add", "--", *originals], cwd=source, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
         "commit", "-qm", "Add fixture"],
        cwd=source, check=True,
    )
    # Current caller filters: algoritmi-e-strutture-di-dati and sistemi-operativi.
    for include, publish_html in (
        (r"\.(pdf|link|txt|html|css|js|ts|ico|env|zip|vim|md)$", True),
        (r"\.(pdf|link|txt|c|sh|py|gz|apkg)$", False),
    ):
        subprocess.run(
            ["/bin/sh", "-ec", rename.replace("${{inputs.regex_include}}", include)],
            cwd=source, check=True,
        )
        if publish_html:
            assert not (source / "notes/chapter/lesson.html").exists()
            assert (source / "notes/chapter.html").is_file()
        command = listing.replace("${{inputs.regex_include}}", include)
        subprocess.run(["/bin/sh", "-ec", command], cwd=source, check=True)
        site = source / "site"
        metadata = json.loads((site / "fuzzy.json").read_text())
        published = {entry["path"]: entry for entry in metadata}
        assert (site / "control.txt").read_text() == originals["control.txt"]
        for name in ("notes/chapter.html", "notes/legacy.html"):
            assert (site / name).is_file() == publish_html, name
            assert (name in published) == publish_html, name
            if publish_html:
                assert "<strong>bold</strong>" in (site / name).read_text(), name
                url = "https://risorse.vercel.app/fixture/" + name
                assert published[name]["url"] == url, name
                assert published[name]["mime"].split(";")[0] == "text/html", name
                assert url in (site / "notes/index.html").read_text(), name
        assert not any(name.endswith((".adoc", ".asciidoc")) for name in published)
        assert not (site / "README.html").exists()
        assert not (site / ".github").exists()
        print(f"PASS: statik publication with HTML allowed={publish_html}", flush=True)

    empty = Path(tmp) / "without-asciidoc"
    empty.mkdir()
    (empty / "control.txt").write_text("Unchanged.\n")
    for name, command in compile_steps:
        subprocess.run(["/bin/sh", "-ec", command], cwd=empty, check=True)
    assert sorted(path.name for path in empty.iterdir()) == ["control.txt"]
    print("PASS: no matching sources is a successful no-op", flush=True)
