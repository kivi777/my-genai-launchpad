from collections.abc import Iterator
from contextlib import contextmanager
from fcntl import LOCK_EX, flock
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import NAMESPACE_URL, UUID, uuid5

import frontmatter
from yaml import YAMLError

from . import config
from .schema import MeetingSkill, PresentationTheme

MAX_SKILL_BYTES = 64 * 1024
THEME_KEYS = {
    "background": "launchpad-background",
    "text": "launchpad-text",
    "accent": "launchpad-accent",
    "font": "launchpad-font",
    "chart": "launchpad-chart",
}


class SkillVersionConflict(Exception):
    pass


def _directory() -> Path:
    return config.UPLOAD_DIR / "ppt-skills"


@contextmanager
def _write_lock() -> Iterator[None]:
    directory = _directory()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a") as lock:
        flock(lock, LOCK_EX)
        yield


def _write_skill(skill: MeetingSkill) -> None:
    directory = _directory()
    with NamedTemporaryFile(
        dir=directory, mode="w", encoding="utf-8", delete=False
    ) as file:
        temporary = Path(file.name)
        try:
            file.write(skill.model_dump_json())
            file.close()
            temporary.replace(directory / f"{skill.id}.json")
        finally:
            temporary.unlink(missing_ok=True)


def skill_etag(skill: MeetingSkill) -> str:
    digest = sha256(skill.model_dump_json().encode()).hexdigest()
    return f'"{digest}"'


def save_skill(content: bytes) -> MeetingSkill:
    try:
        post = frontmatter.loads(content.decode("utf-8-sig"))
    except (UnicodeError, YAMLError, TypeError, RecursionError) as exc:
        raise ValueError("请上传 UTF-8 编码且 YAML 格式正确的 SKILL.md。") from exc
    metadata = post.get("metadata")
    theme_values = {
        field: metadata[key]
        for field, key in THEME_KEYS.items()
        if isinstance(metadata, dict) and key in metadata
    }
    skill = MeetingSkill(
        id=uuid5(NAMESPACE_URL, content.hex()),
        name=post.get("name"),
        description=post.get("description"),
        instructions=post.content,
        renderer="research-ppt-skill"
        if post.get("name") == "research-ppt-skill"
        else None,
        theme=PresentationTheme.model_validate(theme_values) if theme_values else None,
    )
    with _write_lock():
        try:
            return get_skill(skill.id)
        except FileNotFoundError:
            _write_skill(skill)
    return skill


def get_skill(skill_id: UUID) -> MeetingSkill:
    path = _directory() / f"{skill_id}.json"
    return MeetingSkill.model_validate_json(path.read_bytes())


def list_skills() -> list[MeetingSkill]:
    skills = []
    for path in _directory().glob("*.json"):
        try:
            skills.append(MeetingSkill.model_validate_json(path.read_bytes()))
        except FileNotFoundError:
            continue
    return sorted(skills, key=lambda skill: (skill.name, skill.id))


def update_skill(skill: MeetingSkill, if_match: str | None = None) -> MeetingSkill:
    with _write_lock():
        current = get_skill(skill.id)
        if (
            if_match
            and if_match.strip() != "*"
            and skill_etag(current) not in {tag.strip() for tag in if_match.split(",")}
        ):
            raise SkillVersionConflict
        skill = skill.model_copy(
            update={
                "renderer": "research-ppt-skill"
                if current.uses_academic_layout
                else None
            }
        )
        _write_skill(skill)
    return skill


def delete_skill(skill_id: UUID) -> None:
    with _write_lock():
        (_directory() / f"{skill_id}.json").unlink()
