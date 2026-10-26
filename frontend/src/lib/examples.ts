// Field shapes shown next to each endpoint. Values are type names, not observed data.

export const RESOURCE_SHAPE = `{
  "id": "string",
  "title": "string",
  "url": "string",
  "kind": "string",
  "categoryIds": ["string"],
  "audiences": ["string"],
  "tags": ["string"],
  "summary": "string | null",
  "level": "string | null",
  "duration": {
    "courseMinutes": "number | null",
    "pathMinutes": "number | null",
    "videoSeconds": "number | null"
  },
  "detail": {
    "audience": "string | null",
    "prerequisites": ["string"],
    "objectives": ["string"],
    "sections": ["…"]
  },
  "media": "…",
  "provenance": {
    "sourceUrls": ["string"],
    "fetchedAt": "string | null",
    "contentHash": "string | null",
    "method": "string"
  }
}`

export const LIST_SHAPE = `{
  "items": ["Resource"],
  "nextCursor": "string | null",
  "total": "number",
  "snapshotId": "string"
}`

export const CATEGORIES_SHAPE = `{
  "items": [
    { "id": "string", "label": "string", "count": "number" }
  ],
  "snapshotId": "string"
}`
