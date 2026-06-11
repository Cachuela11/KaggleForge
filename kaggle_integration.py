from __future__ import annotations

import csv
import os
import re
import zipfile
from pathlib import Path

from config import settings


KAGGLE_COMPETITION_RE = re.compile(
    r"(?:https?://)?(?:www\.)?kaggle\.com/competitions/([a-zA-Z0-9_-]+)"
)


def extract_competition_id(text: str) -> str | None:
    """Extract a Kaggle competition slug from a Kaggle competition URL."""

    match = KAGGLE_COMPETITION_RE.search(text.strip())
    return match.group(1) if match else None


def fetch_competition(competition_id: str, data_dir: Path) -> dict:
    """Fetch Kaggle competition metadata and download competition files."""

    _configure_kaggle_credentials()
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()

    response = api.competitions_list(search=competition_id)
    competitions = getattr(response, "competitions", response)
    competition = None
    for candidate in competitions:
        ref = str(getattr(candidate, "ref", "") or "")
        if ref.endswith(f"/{competition_id}") or competition_id in ref:
            competition = candidate
            break

    if competition is None:
        raise RuntimeError(f"Kaggle competition '{competition_id}' was not found.")

    has_entered = getattr(competition, "userHasEntered", None)
    has_accepted = getattr(competition, "hasAcceptedRules", None)
    if has_entered is False and has_accepted is False:
        raise RuntimeError(
            "You need to join the Kaggle competition and accept its rules first: "
            f"https://www.kaggle.com/competitions/{competition_id}/rules"
        )

    competition_dir = data_dir / competition_id
    competition_dir.mkdir(parents=True, exist_ok=True)

    files_response = api.competition_list_files(competition_id)
    files = getattr(files_response, "files", [])
    file_names = [str(getattr(file_info, "name", "")) for file_info in files]
    file_names = [name for name in file_names if name]

    existing_files = {path.name for path in competition_dir.iterdir() if path.is_file()}
    missing_files = [name for name in file_names if name not in existing_files]
    if missing_files:
        api.competition_download_files(competition_id, path=str(competition_dir))
        for archive_path in competition_dir.glob("*.zip"):
            with zipfile.ZipFile(archive_path, "r") as archive:
                archive.extractall(competition_dir)
            archive_path.unlink()

    return {
        "id": competition_id,
        "title": getattr(competition, "title", "") or competition_id,
        "description": getattr(competition, "description", "") or "",
        "metric": getattr(competition, "evaluation_metric", "") or "",
        "data_dir": str(competition_dir.resolve()),
        "files": file_names,
    }


def build_kaggle_refined_idea(info: dict) -> str:
    """Build refined_idea.md content from Kaggle metadata and local files."""

    data_dir = Path(info["data_dir"])
    files = ", ".join(info.get("files", [])) or "No file list returned by Kaggle API"
    parts = [
        f"# Kaggle Competition: {info['title']}",
        "",
        f"- **Competition ID**: `{info['id']}`",
        f"- **Evaluation Metric**: {info.get('metric') or 'Not specified'}",
        f"- **Local Data Directory**: `{data_dir}`",
        f"- **Dataset Files**: {files}",
        "- **Expected Submission**: create a `submission.csv` file following the sample submission format.",
        "",
    ]

    description = str(info.get("description") or "").strip()
    if description:
        parts.extend(["## Competition Description", "", description, ""])

    data_description = data_dir / "data_description.txt"
    if data_description.exists():
        parts.extend([
            "## Data Description",
            "",
            data_description.read_text(encoding="utf-8", errors="replace").strip(),
            "",
        ])

    sample_submission = data_dir / "sample_submission.csv"
    if sample_submission.exists():
        header, first_row = _read_csv_header_and_first_row(sample_submission)
        if header:
            parts.extend(["## Submission Format", "", f"- **Columns**: {', '.join(header)}"])
            if first_row:
                parts.append(f"- **Example Row**: {', '.join(first_row)}")
            parts.append("")

    train_csv = data_dir / "train.csv"
    if train_csv.exists():
        header, row_count = _read_csv_shape(train_csv)
        if header:
            parts.extend([
                "## Training Data Overview",
                "",
                f"- **Rows**: {row_count}",
                f"- **Columns**: {len(header)}",
                f"- **Column Names**: {', '.join(header)}",
                "",
            ])

    parts.extend([
        "## Refined Objective",
        "",
        "Build a reproducible machine learning solution for this Kaggle competition. "
        "The research workflow should inspect the dataset, establish a baseline, "
        "iterate on modeling and validation, and produce a valid submission file.",
        "",
    ])
    return "\n".join(parts).strip() + "\n"


def _configure_kaggle_credentials() -> None:
    """Expose MLforge .env credentials in the format Kaggle SDK expects."""

    if settings.kaggle_api_token:
        os.environ.setdefault("KAGGLE_API_TOKEN", settings.kaggle_api_token)
    if settings.kaggle_username:
        os.environ.setdefault("KAGGLE_USERNAME", settings.kaggle_username)
    if settings.kaggle_key:
        os.environ.setdefault("KAGGLE_KEY", settings.kaggle_key)


def _read_csv_header_and_first_row(path: Path) -> tuple[list[str], list[str]]:
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            first_row = next(reader, [])
            return header, first_row
    except OSError:
        return [], []


def _read_csv_shape(path: Path) -> tuple[list[str], int]:
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            row_count = sum(1 for _ in reader)
            return header, row_count
    except OSError:
        return [], 0
