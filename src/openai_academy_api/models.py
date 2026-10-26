"""Strict public metadata and collection artifact contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    model_validator,
)

from .security import (
    ARTWORK_HOSTS,
    MEDIA_HOSTS,
    checked_https_url,
    public_academy_url,
    source_url,
    stable_id,
)


def camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(x.capitalize() for x in tail)


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        alias_generator=camel,
        populate_by_name=True,
        strict=True,
    )

    @field_serializer("*", when_used="json", check_fields=False)
    def utc_dates(self, value: object) -> object:
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return value


Title = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=300,
        pattern=r"^[^\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]+$",
    ),
]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)]
Hash = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
OfficialUrl = Annotated[str, AfterValidator(public_academy_url)]
SourceUrl = Annotated[str, AfterValidator(source_url)]
Count = Annotated[int, Field(ge=0, le=10000)]
Kind = Literal["course", "learning-path", "article", "video", "event", "collection", "external"]
Audience = Literal[
    "general",
    "knowledge-workers",
    "developers",
    "leaders",
    "educators",
    "students",
    "admins",
    "other",
]


class Duration(Model):
    course_minutes: Count | None = None
    path_minutes: Count | None = None
    video_seconds: Annotated[int, Field(ge=0, le=604800)] | None = None


class Unit(Model):
    title: Title
    url: OfficialUrl
    kind: Literal["lesson", "quiz", "course"]
    context: ShortText | None = None
    video_count: Count | None = None


class Section(Model):
    title: Title | None = None
    context: ShortText | None = None
    units: list[Unit] = Field(default_factory=list, max_length=200)


class Detail(Model):
    audience: ShortText | None = None
    prerequisites: list[ShortText] = Field(default_factory=list, max_length=20)
    objectives: list[ShortText] = Field(default_factory=list, max_length=20)
    sections: list[Section] = Field(default_factory=list, max_length=50)


class MediaReference(Model):
    kind: Literal["video", "audio", "image", "document"]
    url: Annotated[str, AfterValidator(lambda v: checked_https_url(v, MEDIA_HOSTS))]
    permission: Literal["permitted"]
    permission_evidence_url: SourceUrl
    title: Title | None = None


class Category(Model):
    id: Slug
    label: Title


class CategoryCount(Category):
    count: Count


class Coverage(Model):
    category_id: Slug
    state: Literal["complete", "partial", "not-collected"]
    discovered: Count | None = None
    collected: Count

    @model_validator(mode="after")
    def consistent_counts(self) -> Self:
        if self.discovered is not None and self.discovered < self.collected:
            raise ValueError("Collected count exceeds discovery count")
        if self.state == "complete" and self.discovered != self.collected:
            raise ValueError("Complete coverage requires matching known counts")
        if self.state == "not-collected" and self.collected:
            raise ValueError("Not-collected coverage must have zero collected resources")
        return self


class InputProvenance(Model):
    source_urls: list[SourceUrl] = Field(min_length=1, max_length=16)
    fetched_at: AwareDatetime

    @model_validator(mode="after")
    def plausible_time(self) -> Self:
        if self.fetched_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Fetched time is implausibly in the future")
        return self


class Provenance(InputProvenance):
    content_hash: Hash
    method: Literal["managed-agent", "manual", "fixture"]


class ArtworkReference(Model):
    url: Annotated[str, AfterValidator(lambda value: checked_https_url(value, ARTWORK_HOSTS))]
    alt: ShortText | None = None
    source_url: OfficialUrl


class Metadata(Model):
    title: Title
    url: OfficialUrl
    kind: Kind
    category_ids: list[Slug] = Field(default_factory=list, max_length=50)
    audiences: list[Audience] = Field(default_factory=list, max_length=8)
    tags: list[Title] = Field(default_factory=list, max_length=50)
    summary: Annotated[str, Field(min_length=1, max_length=1200)] | None = None
    level: Literal["beginner", "intermediate", "advanced"] | None = None
    duration: Duration = Field(default_factory=Duration)
    detail: Detail = Field(default_factory=Detail)
    media: list[MediaReference] = Field(default_factory=list, max_length=20)
    artwork: ArtworkReference | None = None

    @model_validator(mode="after")
    def unique_values(self) -> Self:
        for values in (self.category_ids, self.audiences, self.tags):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate resource category, audience or tag")
        if sum(len(x.units) for x in self.detail.sections) > 200:
            raise ValueError("Too many ordered units")
        return self


class InputResource(Metadata):
    provenance: InputProvenance

    @model_validator(mode="after")
    def primary_source(self) -> Self:
        if self.url not in self.provenance.source_urls:
            raise ValueError("Provenance must include the resource URL")
        if self.artwork and self.artwork.source_url not in self.provenance.source_urls:
            raise ValueError("Artwork source must be present in resource provenance")
        return self


class Resource(Metadata):
    id: Annotated[str, StringConstraints(pattern=r"^oa_[a-f0-9]{24}$")]
    provenance: Provenance

    @model_validator(mode="after")
    def verify_identity(self) -> Self:
        if self.id != stable_id(self.url):
            raise ValueError("Resource ID does not match its canonical URL")
        if self.provenance.content_hash != metadata_hash(self):
            raise ValueError("Resource content hash does not match its metadata")
        if self.url not in self.provenance.source_urls:
            raise ValueError("Provenance must include the resource URL")
        if self.artwork and self.artwork.source_url not in self.provenance.source_urls:
            raise ValueError("Artwork source must be present in resource provenance")
        return self


class FetchReport(Model):
    requests: Count
    robots_checked: Literal[True]
    completed_within_limits: Literal[True]


class CollectionArtifact(Model):
    schema_version: Literal[1]
    generated_at: AwareDatetime
    categories: list[Category] = Field(max_length=200)
    resources: list[InputResource] = Field(max_length=5000)
    coverage: list[Coverage] = Field(max_length=200)
    fetch_report: FetchReport

    @model_validator(mode="after")
    def consistent_inventory(self) -> Self:
        validate_inventory(self.categories, self.resources, self.coverage)
        if self.generated_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Generation time is implausibly in the future")
        if any(r.provenance.fetched_at > self.generated_at for r in self.resources):
            raise ValueError("Fetched time is later than snapshot generation")
        return self


class Snapshot(Model):
    schema_version: Literal[1]
    snapshot_id: Hash
    generated_at: AwareDatetime
    categories: list[Category] = Field(max_length=200)
    resources: list[Resource] = Field(max_length=5000)
    coverage: list[Coverage] = Field(max_length=200)

    @model_validator(mode="after")
    def consistent_snapshot(self) -> Self:
        validate_inventory(self.categories, self.resources, self.coverage)
        if self.generated_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Generation time is implausibly in the future")
        if any(r.provenance.fetched_at > self.generated_at for r in self.resources):
            raise ValueError("Fetched time is later than snapshot generation")
        if self.snapshot_id != snapshot_hash(self):
            raise ValueError("Snapshot hash does not match its contents")
        return self


class ResourcePage(Model):
    items: list[Resource]
    next_cursor: str | None
    total: int
    snapshot_id: Hash


class CategoryPage(Model):
    items: list[CategoryCount]
    snapshot_id: Hash


class Status(Model):
    state: Literal["fresh", "stale", "unavailable"]
    snapshot_id: Hash | None
    generated_at: AwareDatetime | None
    last_attempt_at: AwareDatetime | None
    last_success_at: AwareDatetime | None
    resource_count: int
    coverage: list[Coverage]


def json_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def metadata_hash(resource: Metadata) -> str:
    data = resource.model_dump(mode="json", by_alias=True, exclude={"id", "provenance"})
    if data.get("artwork") is None:
        data.pop("artwork", None)  # Preserve hashes of snapshots predating this additive field.
    return json_hash(data)


def snapshot_hash(snapshot: Snapshot) -> str:
    data = snapshot.model_dump(mode="json", by_alias=True, exclude={"snapshot_id"})
    for resource in data["resources"]:
        if resource.get("artwork") is None:
            resource.pop("artwork", None)
    return json_hash(data)


def validate_inventory(categories: list, resources: list, coverage: list[Coverage]) -> None:
    ids = [x.id for x in categories]
    urls = [x.url for x in resources]
    if len(ids) != len(set(ids)) or len(urls) != len(set(urls)):
        raise ValueError("Duplicate category ID or resource URL")
    if {x.category_id for x in coverage} != set(ids) or len(coverage) != len(ids):
        raise ValueError("Coverage must contain exactly one row per category")
    for resource in resources:
        if set(resource.category_ids) - set(ids):
            raise ValueError("Resource refers to an unknown category")
    for item in coverage:
        count = sum(item.category_id in r.category_ids for r in resources)
        if count != item.collected:
            raise ValueError("Coverage count does not match category membership")


def build_snapshot(
    artifact: CollectionArtifact, method: Literal["managed-agent", "manual", "fixture"]
) -> Snapshot:
    resources = []
    for source in artifact.resources:
        data = source.model_dump()
        data["id"] = stable_id(source.url)
        data["provenance"].update(content_hash=metadata_hash(source), method=method)
        resources.append(Resource.model_validate(data))
    return assemble_snapshot(
        artifact.generated_at, artifact.categories, resources, artifact.coverage
    )


def assemble_snapshot(
    generated_at: datetime,
    categories: list[Category],
    resources: list[Resource],
    coverage: list[Coverage],
) -> Snapshot:
    data = {
        "schema_version": 1,
        "generated_at": generated_at,
        "categories": sorted(categories, key=lambda x: x.id),
        "resources": sorted(resources, key=lambda x: x.id),
        "coverage": sorted(coverage, key=lambda x: x.category_id),
    }
    normalized = {
        camel(k): [x.model_dump(mode="json", by_alias=True) for x in v]
        if isinstance(v, list)
        else v.astimezone(UTC).isoformat().replace("+00:00", "Z")
        if isinstance(v, datetime)
        else v
        for k, v in data.items()
    }
    for resource in normalized["resources"]:
        if resource.get("artwork") is None:
            resource.pop("artwork", None)
    return Snapshot.model_validate(dict(data, snapshot_id=json_hash(normalized)))
