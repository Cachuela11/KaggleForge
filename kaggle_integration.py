from __future__ import annotations

import csv
import os
import re
import time
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

    return _call_kaggle(
        lambda: _fetch_competition_once(competition_id, data_dir),
        "Kaggle fetch competition",
    )


def _fetch_competition_once(competition_id: str, data_dir: Path) -> dict:
    """Fetch Kaggle competition metadata and download competition files once."""

    _configure_kaggle_credentials()
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    _call_kaggle(api.authenticate, "Kaggle authentication")

    response = _call_kaggle(
        lambda: api.competitions_list(search=competition_id),
        "Kaggle competition search",
    )
    competitions = getattr(response, "competitions", response)
    competition = None
    for candidate in competitions:
        ref = str(getattr(candidate, "ref", "") or "")
        if ref.endswith(f"/{competition_id}") or competition_id in ref:
            competition = candidate
            break

    if competition is None:
        raise RuntimeError(f"没有找到 Kaggle competition: {competition_id}")

    has_entered = getattr(competition, "userHasEntered", None)
    has_accepted = getattr(competition, "hasAcceptedRules", None)
    if has_entered is False and has_accepted is False:
        raise RuntimeError(
            "你需要先加入该 Kaggle competition 并接受规则："
            f"https://www.kaggle.com/competitions/{competition_id}/rules"
        )

    competition_dir = data_dir / competition_id
    competition_dir.mkdir(parents=True, exist_ok=True)

    files_response = _call_kaggle(
        lambda: api.competition_list_files(competition_id),
        "Kaggle file listing",
    )
    files = getattr(files_response, "files", [])
    file_names = [str(getattr(file_info, "name", "")) for file_info in files]
    file_names = [name for name in file_names if name]

    existing_files = {path.name for path in competition_dir.iterdir() if path.is_file()}
    missing_files = [name for name in file_names if name not in existing_files]
    if missing_files:
        _call_kaggle(
            lambda: api.competition_download_files(competition_id, path=str(competition_dir)),
            "Kaggle file download",
        )
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


def build_kaggle_task(info: dict) -> str:
    """Build task.md content from Kaggle metadata and local files."""

    data_dir = Path(info["data_dir"])
    files = ", ".join(info.get("files", [])) or "Kaggle API 未返回文件列表"
    parts = [
        f"# Kaggle 任务：{info['title']}",
        "",
        f"- **竞赛 ID**：`{info['id']}`",
        f"- **评估指标**：{info.get('metric') or '未说明'}",
        f"- **本地数据目录**：`{data_dir}`",
        f"- **数据文件**：{files}",
        "- **预期提交**：按照 sample submission 的格式生成 `submission.csv`。",
        "",
    ]

    description = str(info.get("description") or "").strip()
    if description:
        parts.extend(["## 竞赛说明", "", description, ""])

    data_description = data_dir / "data_description.txt"
    if data_description.exists():
        parts.extend(
            [
                "## 数据字段说明",
                "",
                data_description.read_text(encoding="utf-8", errors="replace").strip(),
                "",
            ]
        )

    sample_submission = data_dir / "sample_submission.csv"
    if sample_submission.exists():
        header, first_row = _read_csv_header_and_first_row(sample_submission)
        if header:
            parts.extend(["## 提交格式", "", f"- **列名**：{', '.join(header)}"])
            if first_row:
                parts.append(f"- **示例行**：{', '.join(first_row)}")
            parts.append("")

    train_csv = data_dir / "train.csv"
    if train_csv.exists():
        header, row_count = _read_csv_shape(train_csv)
        if header:
            parts.extend(
                [
                    "## 训练数据概览",
                    "",
                    f"- **行数**：{row_count}",
                    f"- **列数**：{len(header)}",
                    f"- **字段名**：{', '.join(header)}",
                    "",
                ]
            )

    parts.extend(
        [
            "## 初始目标",
            "",
            "为该 Kaggle 竞赛构建一个可复现的机器学习解决方案。后续流程应包括数据理解、"
            "baseline 建立、验证方案设计、模型迭代、误差分析，并最终产出有效的 `submission.csv`。",
            "",
        ]
    )
    return "\n".join(parts).strip() + "\n"


def _configure_kaggle_credentials() -> None:
    """Expose MLforge .env credentials in the format Kaggle SDK expects."""

    if settings.kaggle_api_token:
        os.environ.setdefault("KAGGLE_API_TOKEN", settings.kaggle_api_token)
    if settings.kaggle_username:
        os.environ.setdefault("KAGGLE_USERNAME", settings.kaggle_username)
    if settings.kaggle_key:
        os.environ.setdefault("KAGGLE_KEY", settings.kaggle_key)


def _call_kaggle(operation, label: str, attempts: int = 3):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if _is_forbidden_error(exc):
                raise RuntimeError(
                    f"{label} failed with 403 Forbidden. "
                    "Your Kaggle account can see this competition, but cannot download its files yet. "
                    "Open the competition page in your browser, join the competition, accept the rules, "
                    "then run MLforge again."
                ) from exc
            if attempt == attempts:
                break
            print(
                f"[kaggle] Temporary connection issue during {label}; "
                f"retrying {attempt}/{attempts - 1}...",
                flush=True,
            )
            time.sleep(2 * attempt)

    raise RuntimeError(
        f"{label} failed after {attempts} attempts. "
        "This is usually a Kaggle/network/proxy connection problem. "
        f"Last error: {last_error}"
    ) from last_error


def _is_forbidden_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code == 403 or "403" in str(exc) and "Forbidden" in str(exc)


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
